"""Check Claude's report narrative against the check's findings before it reaches a customer.

The check decides every review priority and conflict; Claude only writes the wording. Each written passage must:
- stay on the research side of the line: no recommendations, instructions or outcome promises;
- agree with the review priorities the check set;
- mention only trade mark numbers that are in the findings;
- not contradict the key findings (for example "no similar marks" when some were flagged).

A passage that fails is dropped and the report uses the tool's own wording for it; the reason is logged.
"""

import logging
import re

from ..explain import Explanation
from ..models import Report, Risk

log = logging.getLogger("uvicorn.error")

# Phrases that turn research into advice or a promise (risk assessment §4.1, legal-boundary controls).
BANNED = [
    "you should", "you must", "you need to", "we recommend", "i recommend", "recommend that you", "our recommendation",
    "the best option", "best choice", "option to consider first", "safe to", "is safe", "will be accepted",
    "will be registered", "will be refused", "will be rejected", "we guarantee", "guaranteed to", "no risk", "risk-free",
    "don't need a lawyer", "do not need a lawyer", "no need for a lawyer", "go ahead and file", "file as a",
    "file a word mark", "file a composite", "you can proceed", "proceed with filing", "change your name to",
]

_PRIORITY = re.compile(r"\b(high|medium|low)\b(?:\s+review)?\s+priority|priority(?:\s+of)?\s*:?\s+(high|medium|low)\b",
                       re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\d.,$])\b(\d{6,7})\b(?![\d,])")
_NONE_FOUND = re.compile(r"\bno (?:similar|earlier|conflicting|relevant) (?:trade )?marks?\b|"
                         r"\bnone of the (?:\d+ )?marks\b|\bno marks? (?:were|was) (?:flagged|found)\b", re.IGNORECASE)


def problems(text: str, report: Report, *, risk: Risk | None = None, attention: int | None = None) -> list[str]:
    """Why this passage can't be used as written (empty: it can)."""
    found: list[str] = []
    lower = text.lower()
    for phrase in BANNED:
        if phrase in lower:
            found.append(f"advice or promise: '{phrase}'")
    known = {c.cited_number for c in report.conflicts} | set(report.own_marks) | set(report.own_marks_assumed)
    for number in _NUMBER.findall(text):
        if number not in known:
            found.append(f"trade mark number not in the findings: {number}")
    if risk is not None:
        for m in _PRIORITY.finditer(text):
            said = (m.group(1) or m.group(2)).capitalize()
            if said != risk.value:
                found.append(f"says {said} priority, the check set {risk.value}")
    if attention is not None and attention > 0 and _NONE_FOUND.search(text):
        found.append(f"says no marks were flagged, but {attention} were")
    return found


def checked(explanation: Explanation | None, report: Report) -> Explanation | None:
    """The explanation with every passage that fails the checks removed (None if nothing usable is left)."""
    if explanation is None:
        return None
    by_number = {c.cited_number: c for c in report.conflicts}
    attention = sum(1 for c in report.conflicts if c.live and c.risk != Risk.LOW)

    def ok(where: str, text: str, **kw) -> bool:
        issues = problems(text, report, **kw)
        if issues:
            log.warning("Report narrative (%s) not used: %s", where, "; ".join(issues))
        return not issues

    # The overview may mention several marks at different priorities, so only the overall priority is checked when
    # it is named as such.
    overall_ok = ok("overview", explanation.overview, attention=attention) and not _wrong_overall(explanation.overview, report)
    conflicts = []
    for c in explanation.conflicts:
        if c.cited_number not in by_number:
            log.warning("Report narrative (mark %s) not used: that mark isn't in the findings", c.cited_number)
        elif ok(f"mark {c.cited_number}", c.explanation, risk=by_number[c.cited_number].risk):
            conflicts.append(c)
    distinct = explanation.distinctiveness
    if distinct is not None and not ok("distinctiveness", distinct.explanation):
        distinct = None
    steps = [s for i, s in enumerate(explanation.next_steps) if ok(f"open question {i + 1}", s, attention=attention)]
    return explanation.model_copy(update={"overview": explanation.overview if overall_ok else "",
                                          "conflicts": conflicts, "distinctiveness": distinct, "next_steps": steps})


def _wrong_overall(text: str, report: Report) -> bool:
    m = re.search(r"overall (?:review )?priority(?: of| is| was|:)?\s+(high|medium|low)\b", text, re.IGNORECASE)
    if m and m.group(1).capitalize() != report.overall_risk.value:
        log.warning("Report narrative (overview) not used: says overall %s, the check set %s",
                    m.group(1).capitalize(), report.overall_risk.value)
        return True
    return False
