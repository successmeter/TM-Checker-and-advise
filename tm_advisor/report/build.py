"""Turn a completed check into the paid report (design: docs/paid-report-design.md §4).

The check decides every risk level, conflict and route. Claude only writes the narrative (summary, next steps,
what to do about each mark) from those findings, with Trade Marks Manual citations it was given; if Claude isn't
available the report is still complete, with plainer wording.
"""

import logging
from collections.abc import Callable

from ..explain import Explainer, Explanation, ExplanationUnavailable, retrieve
from ..manual import ManualIndex
from ..models import Application, Conflict, GoodsLevel, Report, Risk
from ..picklist import ClassInfo
from .schema import (Citation, DistinctivenessSection, Filing, ReportDoc, SimilarMark, SpecClass, SpecTerm)

log = logging.getLogger("uvicorn.error")

MAX_MARKS = 40
REPORT_EFFORT = "high"

DESIGN_GUIDANCE = [
    "The design must be substantial and distinctive in its own right: a stylised font, colour or simple shape "
    "around the words is usually not enough.",
    "Make the design element prominent, not a small symbol beside large words.",
    "Avoid pictures of what your goods or services are (a coffee cup for a cafe, a chart for analytics): they add "
    "descriptive meaning instead of distinctiveness.",
    "Use the logo exactly as filed. The registration protects that combination of design and words.",
]

LIMITATIONS = [
    "This report is general information produced by software, not legal advice. It is not a clearance search for "
    "using the brand, and Trademark Advisor does not file applications for you.",
    "It is based on the register on the date above; marks filed later, or not yet published, are not included.",
    "Examiners decide each case on its facts, and other traders can oppose an application; no outcome is guaranteed.",
]

ADVERSE_HEADSTART = [
    "You have 5 working days to amend the request (changing the mark itself needs a new representation and an "
    "extra fee).",
    "Or pay Part 2 and respond to the formal examination report within 15 months, with amendments, arguments or "
    "evidence of use.",
    "Or start again with a different mark.",
]

KIND_STEP = {
    "word": "Start a TM Headstart request: choose a word mark, type the words exactly, and paste your goods and "
            "services from section 5.",
    "composite": "Start a TM Headstart request: choose a mark with a design (upload your logo), enter the words in "
                 "it, and paste your goods and services from section 5.",
    "logo": "Start a TM Headstart request: choose a mark with a design (upload your logo), and paste your goods "
            "and services from section 5.",
}


def build_report(application: Application, report: Report, *, classes: dict[int, ClassInfo], reference: str,
                 created: str, register_searched: str, sources: list[str], explainer: Explainer | None = None,
                 manual: ManualIndex | None = None, logo_image: str | None = None, industry: str = "",
                 sample: bool = False) -> ReportDoc:
    explanation = _explain(report, explainer, manual)
    by_number = {c.cited_number: c.explanation for c in explanation.conflicts} if explanation else {}
    route = report.route
    assert route is not None, "the check sets a route"

    marks = [_similar(c, by_number.get(c.cited_number)) for c in _relevant(report.conflicts)]
    attention = [m for m in marks if m.live and m.risk != Risk.LOW]
    summary = explanation.overview if explanation else _plain_summary(report, len(attention))
    actions = explanation.next_steps if explanation and explanation.next_steps else route.reasons[:3]

    return ReportDoc(
        reference=reference, created=created, register_searched=register_searched, sources=sources, sample=sample,
        prepared_for=application.applicant, mark=application.mark, mark_kind=application.mark_kind,
        logo_image=logo_image, classes=[c.class_number for c in application.classes],
        overall_risk=report.overall_risk, summary=summary, top_actions=actions[:5],
        route=route, route_detail=_route_detail(report),
        distinctiveness=_distinctiveness(report, explanation),
        similar_marks=marks, marks_reviewed=report.marks_screened,
        specification=_specification(application, report, classes),
        specification_notes=_spec_notes(industry),
        design_guidance=DESIGN_GUIDANCE if route.recommended == "composite" or application.mark_kind != "word" else [],
        filing=_filing(application, report),
        attorney_reasons=report.escalation_reasons,
        limitations=LIMITATIONS,
    )


def _explain(report: Report, explainer: Explainer | None, manual: ManualIndex | None) -> Explanation | None:
    if explainer is None:
        return None
    try:
        excerpts = retrieve(report, manual) if manual is not None else []
        return explainer.explain(report, excerpts, effort=REPORT_EFFORT)
    except ExplanationUnavailable as e:
        log.warning("Report narrative unavailable, using plain wording: %s", e)
        return None


def _relevant(conflicts: list[Conflict]) -> list[Conflict]:
    order = {Risk.HIGH: 0, Risk.MEDIUM: 1, Risk.LOW: 2}
    return sorted(conflicts, key=lambda c: (not c.live, order[c.risk], -c.mark_score))[:MAX_MARKS]


def _similar(c: Conflict, explained: str | None) -> SimilarMark:
    overlap = " ".join(
        f"Your class {o.user_class} vs their class {o.cited_class}: {o.note}"
        + (f" Overlapping: {', '.join(o.overlapping_terms)}." if o.overlapping_terms else "")
        for o in c.overlaps)
    return SimilarMark(number=c.cited_number, words=c.cited_words or "(no words)", logo=c.cited_logo,
                       image=c.cited_image, status=c.cited_status, owner=c.cited_owner,
                       classes=sorted({o.cited_class for o in c.overlaps}), live=c.live, risk=c.risk,
                       why_similar=c.mark_reasons, goods_overlap=overlap or "No overlapping goods or services.",
                       what_to_do=f"{explained} {c.option}" if explained else c.option)


def _plain_summary(report: Report, attention: int) -> str:
    parts = [f"Overall risk: {report.overall_risk.value}."]
    if report.route:
        parts.append(f"Recommended route: {report.route.headline.lower()}.")
    ai = report.ai_distinctiveness
    if ai and ai.likelihood != "unlikely":
        parts.append(f"The mark as a whole is {'likely' if ai.likelihood == 'likely' else 'possibly'} going to be "
                     "seen as describing your goods or services.")
    elif report.distinctiveness:
        parts.append("Some words in the mark describe or praise your goods or services.")
    parts.append(f"{attention} similar mark{'s' if attention != 1 else ''} on the register need{'s' if attention == 1 else ''} "
                 "your attention." if attention else "No similar mark on the register needs attention.")
    return " ".join(parts)


def _route_detail(report: Report) -> list[str]:
    route = report.route
    if route is None:
        return []
    if route.recommended == "composite":
        return ["The concern is that your words describe your goods or services, not an earlier trade mark. That is "
                "the situation where a design helps: the design, not the words, makes the mark distinctive.",
                "If owning the words themselves matters to you, the alternative is a different name with an invented "
                "or unusual element, filed as a word mark."]
    if route.recommended in ("new_name", "narrow_goods"):
        return ["The concern is an earlier similar mark (section 44). Adding a logo would not help: examiners compare "
                "the main feature of each mark, which is usually the words."]
    return []


def _distinctiveness(report: Report, explanation: Explanation | None) -> DistinctivenessSection:
    flags = [f"{f.word.upper()}: {f.reason}" for f in report.distinctiveness]
    citations = [Citation(title=c.title, heading=c.heading, url=c.url, published=c.published)
                 for c in (explanation.distinctiveness.citations if explanation and explanation.distinctiveness else [])]
    ai = report.ai_distinctiveness
    if ai:
        return DistinctivenessSection(likelihood=ai.likelihood, meaning=ai.meaning, reasoning=ai.reasoning,
                                      affected_terms=ai.affected_terms, word_flags=flags, options=ai.options,
                                      citations=citations)
    likelihood = "likely" if report.wholly_descriptive else "possible" if flags else "unlikely"
    reasoning = (explanation.distinctiveness.explanation if explanation and explanation.distinctiveness else
                 "Every word in the mark describes or praises your goods or services." if report.wholly_descriptive
                 else "Some words in the mark describe or praise your goods or services; the rest may carry the mark."
                 if flags else "No descriptive, praising or place-name words were found.")
    options = [] if likelihood == "unlikely" else [
        "Add or substitute an invented or unusual word.",
        "File as a composite mark with a substantial, distinctive design.",
        "If you have used the mark for some time, gather evidence of that use."]
    return DistinctivenessSection(likelihood=likelihood, reasoning=reasoning, word_flags=flags, options=options,
                                  citations=citations)


def _specification(application: Application, report: Report, classes: dict[int, ClassInfo]) -> list[SpecClass]:
    picklist = {(p.class_number, p.term): p for p in report.picklist}
    narrowable: dict[tuple[int, str], str] = {}
    for c in report.conflicts:
        if not c.live or c.risk == Risk.LOW:
            continue
        for o in c.overlaps:
            if o.level == GoodsLevel.SAME and o.narrowing_helps:
                for term in o.overlapping_terms:
                    narrowable.setdefault((o.user_class, term), c.cited_words)
    narrow_route = report.route is not None and report.route.recommended == "narrow_goods"

    out = []
    for spec in application.classes:
        kept, removed = [], []
        for term in spec.terms:
            p = picklist.get((spec.class_number, term))
            on = p.on_picklist if p else True
            note = "" if on else ("Not on the picklist (A$400 per class instead of A$250)."
                                  + (f" Closest picklist wording: {'; '.join(p.suggestions)}." if p and p.suggestions else ""))
            other = narrowable.get((spec.class_number, term))
            if other and narrow_route:
                removed.append(SpecTerm(text=term, on_picklist=on,
                                        note=f"Leave out unless you offer it: it overlaps {other}."))
            else:
                if other:
                    note = (note + f" Overlaps {other}: leave it out if you don't offer it.").strip()
                kept.append(SpecTerm(text=term, on_picklist=on, note=note))
        title = classes[spec.class_number].title if spec.class_number in classes else ""
        out.append(SpecClass(class_number=spec.class_number, title=title, terms=kept, removed=removed))
    return out


def _spec_notes(industry: str) -> list[str]:
    notes = ["Only claim what you offer or genuinely intend to offer. Fewer, specific terms mean fewer conflicts, and "
             "terms you never use can later be removed for non-use."]
    area = industry.strip().removeprefix("for ").removeprefix("the ").strip()
    if area:
        notes.append(f"Your industry or customers: “{industry.strip()}”. Where another mark's goods are for a "
                     f"different purpose, a limitation such as “…; all for use in {area}” may remove the overlap "
                     "(Trade Marks Manual, Part 27.3). It doesn't help against a mark that covers the broad term.")
    return notes


def _filing(application: Application, report: Report) -> Filing:
    n = len(application.classes)
    all_picklist = report.picklist_only
    return Filing(classes=n, headstart_part1=200 * n, headstart_part2=130 * n, standard=(250 if all_picklist else 400) * n,
                  all_picklist=all_picklist,
                  steps=["Create an IP Australia online services account (portal.ipaustralia.gov.au).",
                         KIND_STEP[application.mark_kind],
                         "Pay Part 1. The examiner's assessment usually arrives within about 5 business days.",
                         "If the assessment is favourable, pay Part 2 to convert it into an application. That date "
                         "is your filing date.",
                         "Watch for the examination report and respond by its deadline."],
                  adverse_headstart=ADVERSE_HEADSTART)


def make_report(application: Application, check: Callable[[Application], Report], **kwargs) -> ReportDoc:
    """Run the check and build the report in one go (used by the report worker)."""
    return build_report(application, check(application), **kwargs)
