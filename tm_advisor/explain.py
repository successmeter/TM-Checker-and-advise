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
from .models import Report, Risk

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


class Citation(BaseModel):
    id: str
    title: str
    heading: str
    url: str


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
        parts.append(f'<excerpt id="{chunk.id}" title="{chunk.title}" heading="{chunk.heading}">\n{chunk.text}\n</excerpt>')
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
        return [Citation(id=c.id, title=c.title, heading=c.heading, url=c.url)
                for c in (by_id.get(i) for i in dict.fromkeys(ids)) if c]

    conflicts = [
        ExplainedConflict(cited_number=c["cited_number"], explanation=c["explanation"], citations=cite(c["excerpt_ids"]))
        for c in data.get("conflicts", []) if c["cited_number"] in known_numbers
    ]
    d = data.get("distinctiveness")
    distinctiveness = ExplainedPart(explanation=d["explanation"], citations=cite(d["excerpt_ids"])) if d else None
    return Explanation(overview=data["overview"], conflicts=conflicts, distinctiveness=distinctiveness,
                       next_steps=data.get("next_steps", []), model=model)
