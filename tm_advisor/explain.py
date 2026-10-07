"""Plain-English explanations of a report, grounded in Trade Marks Manual passages.

The deterministic checks decide the risk levels. Claude only explains them: it sees the findings and the
retrieved Manual excerpts, must cite excerpts by id, and any citation that wasn't retrieved is dropped.
"""

import json
import os
from typing import Any

import anthropic
from pydantic import BaseModel

from .manual import Chunk, ManualIndex
from .models import AiDistinctiveness, ClassSpec, Report, Risk

DEFAULT_MODEL = "claude-opus-5-5"
MAX_EXCERPTS = 8

SYSTEM_PROMPT = """You explain automated trade mark screening results to Australian founders who plan to file \
their own trade mark application with IP Australia. You are part of a software tool, not a lawyer or a trade \
marks attorney, and what you write is general information, not legal advice.

You receive two things: the tool's findings (risk levels, similar marks on the register, overlapping goods and \
services, distinctiveness flags, picklist results) and excerpts from IP Australia's Trade Marks Manual of \
Practice and Procedure, each with an id.

How to write:
- Plain English for someone who has never read trade mark law. Short sentences. Explain section numbers the \
first time you use them (section 44: conflict with earlier marks; section 41: the mark must be able to \
distinguish the goods).
- Explain why each finding matters, using the Manual excerpts. Cite the ids of the excerpts you relied on. \
Only cite excerpts you were given, and only for points they actually support. If no excerpt supports a point, \
say what the tool found without citing anything.
- Do not change, soften or upgrade any risk level, and do not add conflicts or flags that aren't in the findings.
- Never promise an outcome or give a probability. The examiner decides.
- Options must be things the founder can weigh themselves (for example: leave out goods they don't sell, \
choose a more distinctive name, gather evidence of use). When the findings say to escalate, say plainly that \
this is the point to pay for a registered trade marks attorney, and why."""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overview": {"type": "string", "description": "Two to four sentences: where the application stands overall."},
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cited_number": {"type": "string"},
                    "explanation": {"type": "string"},
                    "excerpt_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cited_number", "explanation", "excerpt_ids"],
                "additionalProperties": False,
            },
        },
        "distinctiveness": {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "excerpt_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["explanation", "excerpt_ids"],
            "additionalProperties": False,
        },
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["overview", "conflicts", "distinctiveness", "next_steps"],
    "additionalProperties": False,
}


KEYWORDS_PROMPT = """You turn a founder's plain-language description of their business into short search words \
for IP Australia's goods and services picklist (the pre-approved list of terms used in trade mark applications).

Return the goods they make or sell and the services they provide, as the nouns a picklist entry would use: \
"coffee", "cafe", "catering", "t-shirts", "online retail", "software", "mobile app", "yoga instruction". \
Include closely connected things they are likely to sell or offer (a cafe usually also sells coffee beans and \
takeaway food). One to three words each, singular or plural as natural, no class numbers, at most 12."""

_KEYWORDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["keywords"],
    "additionalProperties": False,
}


DISTINCTIVENESS_PROMPT = """You assess Australian trade mark applications the way an IP Australia examiner applies \
section 41 of the Trade Marks Act 1995: is the trade mark capable of distinguishing the applicant's goods or \
services from those of other traders? You are part of a screening tool that founders use before filing; what you \
write is general information, not legal advice.

The examiner's test, for the trade mark as a whole and for each of the applicant's goods or services:
1. Ordinary signification: does the mark, read as a whole, have a meaning to people in Australia who buy, use or \
trade in those goods or services? Meanings that count include describing the kind, quality, quantity, intended \
purpose, value, geographical origin or another characteristic of the goods or services, what they do, measure or \
deliver, the result or benefit they bring, or praise (laudatory words).
2. Other traders' need: would other traders, acting honestly, be likely to want to use the mark, or something \
very like it, for that ordinary meaning in connection with similar goods or services?
If both are true for a good or service, the examiner raises section 41 for it.

Judge the phrase as a whole, not only word by word. Two ordinary words joined together often keep a plain \
descriptive meaning (for example, PROFIT TRACKER for accounting software is a thing that tracks profit, so other \
traders need it), even when neither word alone describes the services and the exact phrase is not in a \
dictionary. A combination is distinctive when it is invented, unusual, or alludes to the goods only indirectly so \
that a real leap of imagination is needed to see a description. Misspellings and run-together words do not fix \
a descriptive phrase. For a composite mark (design plus words), plain styling of descriptive words does not \
usually overcome the objection; a substantial, distinctive design element can. For a logo with no words, judge \
whether the described design is more than a simple shape, a common symbol or a picture of the goods.

Calibrate likelihood: "likely" when an examiner would very probably raise section 41 for at least one listed \
good or service; "possible" when it is arguable either way; "unlikely" when the mark is invented, arbitrary for \
these goods or services, or only indirectly suggestive. List the affected goods and services exactly as the \
applicant wrote them. Options are things the applicant can weigh: add or substitute a distinctive element, drop \
goods or services the meaning describes if they don't need them, or (when they have used the mark for some \
time) gather evidence of use. Never promise an outcome."""

_DISTINCTIVENESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "likelihood": {"type": "string", "enum": ["likely", "possible", "unlikely"]},
        "meaning": {"type": "string", "description": "What the mark as a whole ordinarily means for these goods or "
                                                     "services; empty if it has no such meaning."},
        "reasoning": {"type": "string", "description": "Two to four plain-English sentences applying the test."},
        "affected_terms": {"type": "array", "items": {"type": "string"}},
        "options": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["likelihood", "meaning", "reasoning", "affected_terms", "options"],
    "additionalProperties": False,
}


class Citation(BaseModel):
    id: str
    title: str
    heading: str
    url: str
    published: str = ""


class ExplainedPart(BaseModel):
    explanation: str
    citations: list[Citation]


class ExplainedConflict(ExplainedPart):
    cited_number: str


class Explanation(BaseModel):
    overview: str
    conflicts: list[ExplainedConflict]
    distinctiveness: ExplainedPart | None
    next_steps: list[str]
    model: str


class ExplanationUnavailable(Exception):
    """Raised with a message that is safe to show the user."""


def retrieve(report: Report, index: ManualIndex, per_query: int = 3) -> list[Chunk]:
    """Manual excerpts relevant to the findings, most relevant first, without duplicates."""
    queries: list[str] = []
    for conflict in [c for c in report.conflicts if c.live and c.risk != Risk.LOW][:3]:
        query = "section 44 substantially identical deceptively similar trade marks"
        levels = {o.level.value for o in conflict.overlaps}
        if "same" in levels:
            query += " same goods services of the same description"
        if "related" in levels:
            query += " closely related goods and services"
        queries.append(query)
    if report.distinctiveness:
        reasons = " ".join({f.reason for f in report.distinctiveness})
        queries.append(f"section 41 inherently adapted to distinguish descriptive {reasons}")
    ai = report.ai_distinctiveness
    if ai and ai.likelihood != "unlikely":
        queries.append("section 41 ordinary signification other traders desire to use combination of descriptive words")
    if report.conflicts and any(not c.live for c in report.conflicts):
        queries.append("lapsed removed trade marks not cited section 44")

    found: dict[str, Chunk] = {}
    for query in queries:
        for chunk in index.search(query, per_query):
            found.setdefault(chunk.id, chunk)
    return list(found.values())[:MAX_EXCERPTS]


class Explainer:
    def __init__(self, client: Any | None = None, model: str | None = None, effort: str = "medium"):
        self._client = client
        self.model = model or os.environ.get("TM_LLM_MODEL", DEFAULT_MODEL)
        self.effort = effort
        self._assessed: dict[str, AiDistinctiveness] = {}

    @staticmethod
    def configured() -> bool:
        """Whether automatic AI checks should run (an API key is set and TM_AI_CHECKS isn't 0)."""
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()) and os.environ.get("TM_AI_CHECKS", "1") != "0"

    @property
    def client(self) -> Any:
        if self._client is None:
            # A key pasted with a trailing space is refused before it is sent, and the SDK reports that as a
            # connection error, so tidy it up here.
            key = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'").strip() or None
            self._client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        return self._client

    def explain(self, report: Report, excerpts: list[Chunk]) -> Explanation:
        response = self._call(SYSTEM_PROMPT, _user_message(report, excerpts), _SCHEMA, self.effort, 16000)
        if response.stop_reason == "refusal":
            raise ExplanationUnavailable("An explanation could not be generated for this check.")
        if response.stop_reason == "max_tokens":
            raise ExplanationUnavailable("The explanation was too long to complete. Please try again.")
        return _to_explanation(_json_text(response), report, excerpts, getattr(response, "model", self.model))

    def keywords(self, description: str) -> list[str]:
        """Picklist search words for a plain-language description of a business."""
        response = self._call(KEYWORDS_PROMPT, description, _KEYWORDS_SCHEMA, "low", 4000)
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ExplanationUnavailable("Couldn't work out search words for that description.")
        words = _json_text(response).get("keywords", [])
        return [w.strip() for w in dict.fromkeys(words) if w.strip()][:15]

    def assess_distinctiveness(self, mark: str, mark_kind: str, classes: list[ClassSpec]) -> AiDistinctiveness:
        """The section 41 view of the whole mark against the chosen goods and services."""
        listing = "\n".join(f"Class {c.class_number}: " + "; ".join(c.terms) for c in classes)
        kind = {"composite": "composite mark (a design together with these words)",
                "logo": "logo only, no words (the text is a description of the design)"}.get(mark_kind, "word mark")
        user = (f"Trade mark: {mark}\nKind: {kind}\n"
                f"Goods and services:\n{listing}\n\nApply the section 41 test.")
        if user in self._assessed:
            return self._assessed[user]
        response = self._call(DISTINCTIVENESS_PROMPT, user, _DISTINCTIVENESS_SCHEMA, "medium", 8000)
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ExplanationUnavailable("The AI distinctiveness check couldn't complete for this mark.")
        data = _json_text(response)
        result = AiDistinctiveness(likelihood=data["likelihood"], meaning=data["meaning"].strip(),
                                   reasoning=data["reasoning"].strip(), affected_terms=data["affected_terms"],
                                   options=data["options"], model=getattr(response, "model", self.model))
        if len(self._assessed) > 200:
            self._assessed.clear()
        self._assessed[user] = result
        return result

    def _call(self, system: str, user: str, schema: dict, effort: str, max_tokens: int) -> Any:
        try:
            return self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                cache_control={"type": "ephemeral"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError as e:
            raise ExplanationUnavailable("Explanations are not set up: the Anthropic API key is missing or invalid.") from e
        except anthropic.RateLimitError as e:
            raise ExplanationUnavailable("Explanations are busy right now. Please try again in a minute.") from e
        except anthropic.APIStatusError as e:
            raise ExplanationUnavailable(f"The explanation service returned an error ({e.status_code}).") from e
        except anthropic.APIConnectionError as e:
            raise ExplanationUnavailable("Could not reach the explanation service.") from e
        except TypeError as e:
            if "authentication" not in str(e):  # the SDK raises TypeError when no credentials are configured
                raise
            raise ExplanationUnavailable("Explanations are not set up: no Anthropic API key found.") from e


def _json_text(response: Any) -> dict:
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ExplanationUnavailable("The explanation service returned no text.")
    return json.loads(text)


def _user_message(report: Report, excerpts: list[Chunk]) -> str:
    findings = report.model_dump(mode="json", exclude={"disclaimers"})
    parts = ["<findings>", json.dumps(findings, indent=1), "</findings>", "", "<manual_excerpts>"]
    for chunk in excerpts:
        published = f' published="{chunk.published}"' if chunk.published else ""
        parts.append(f'<excerpt id="{chunk.id}" title="{chunk.title}" heading="{chunk.heading}"{published}>\n{chunk.text}\n</excerpt>')
    parts.append("</manual_excerpts>")
    if not excerpts:
        parts.append("(No Manual excerpts are available. Explain the findings without citations.)")
    parts.append("\nExplain these findings for the founder. Cover every conflict listed in the findings, by its "
                 "cited_number. If there are no distinctiveness flags, say so briefly.")
    return "\n".join(parts)


def _to_explanation(data: dict, report: Report, excerpts: list[Chunk], model: str) -> Explanation:
    by_id = {c.id: c for c in excerpts}
    known_numbers = {c.cited_number for c in report.conflicts}

    def cite(ids: list[str]) -> list[Citation]:
        return [Citation(id=c.id, title=c.title, heading=c.heading, url=c.url, published=c.published)
                for c in (by_id.get(i) for i in dict.fromkeys(ids)) if c]

    conflicts = [
        ExplainedConflict(cited_number=c["cited_number"], explanation=c["explanation"], citations=cite(c["excerpt_ids"]))
        for c in data.get("conflicts", []) if c["cited_number"] in known_numbers
    ]
    d = data.get("distinctiveness")
    distinctiveness = ExplainedPart(explanation=d["explanation"], citations=cite(d["excerpt_ids"])) if d else None
    return Explanation(overview=data["overview"], conflicts=conflicts, distinctiveness=distinctiveness,
                       next_steps=data.get("next_steps", []), model=model)
