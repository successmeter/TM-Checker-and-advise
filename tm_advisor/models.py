"""Request and report shapes shared by the engine and the API."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ClassSpec(BaseModel):
    class_number: int = Field(ge=1, le=45)
    terms: list[str] = Field(min_length=1)

    @field_validator("terms")
    @classmethod
    def clean_terms(cls, terms: list[str]) -> list[str]:
        cleaned: list[str] = []
        for term in terms:
            term = " ".join(term.split())
            if term and term.lower() not in (t.lower() for t in cleaned):
                cleaned.append(term)
        if not cleaned:
            raise ValueError("at least one goods or services term is required")
        return cleaned


# word: words only (any style); composite: a design together with words; logo: a design with no words.
MarkKind = Literal["word", "composite", "logo"]


class Application(BaseModel):
    # word: the words; composite: the words in the logo; logo: a short description of the design (no words)
    mark: str = Field(min_length=1, max_length=200)
    classes: list[ClassSpec] = Field(min_length=1)
    mark_kind: MarkKind = "word"
    applicant: str = Field("", max_length=200)  # optional: marks this person or company already owns are left out

    @field_validator("mark")
    @classmethod
    def clean_mark(cls, mark: str) -> str:
        mark = " ".join(mark.split())
        if not mark:
            raise ValueError("mark must not be blank")
        return mark

    @field_validator("classes")
    @classmethod
    def unique_classes(cls, classes: list[ClassSpec]) -> list[ClassSpec]:
        numbers = [c.class_number for c in classes]
        if len(numbers) != len(set(numbers)):
            raise ValueError("each class may appear only once")
        return classes


class RegisterClass(BaseModel):
    class_number: int
    terms: list[str]


class RegisterMark(BaseModel):
    number: str
    words: str
    status: str
    owner: str | None = None
    classes: list[RegisterClass]
    status_group: str | None = None  # IP Australia's statusGroup, e.g. REGISTERED, PENDING, NEVER_REGISTERED
    image: str | None = None         # picture of the mark (logos), from IP Australia's image server
    logo: bool = False               # a figurative (logo) mark rather than plain words

    @property
    def is_live(self) -> bool:
        """Registered, accepted or still pending: only these can be cited under s44."""
        if self.status_group:
            return self.status_group.upper() in ("REGISTERED", "PENDING")
        status = self.status.lower().replace("_", " ")
        return not any(word in status for word in ("lapsed", "removed", "refused", "withdrawn", "expired",
                                                   "never registered", "cancelled", "revoked", "discontinued"))


class Risk(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class GoodsLevel(str, Enum):
    SAME = "same"
    RELATED = "related"
    NONE = "none"


class ClassOverlap(BaseModel):
    user_class: int
    cited_class: int
    level: GoodsLevel
    overlapping_terms: list[str]
    narrowing_helps: bool
    note: str


class Conflict(BaseModel):
    cited_number: str
    cited_words: str
    cited_status: str
    cited_owner: str | None
    live: bool
    risk: Risk
    mark_score: float
    mark_reasons: list[str]
    overlaps: list[ClassOverlap]
    option: str
    cited_image: str | None = None
    cited_logo: bool = False


class PicklistResult(BaseModel):
    class_number: int
    term: str
    on_picklist: bool
    suggestions: list[str]


class DistinctivenessFlag(BaseModel):
    word: str
    reason: str


class AiDistinctiveness(BaseModel):
    """Claude's view of the section 41 test for the mark as a whole (word lists can't judge phrase meanings)."""
    likelihood: Literal["likely", "possible", "unlikely"]  # chance an examiner raises a section 41 objection
    meaning: str                  # what the mark as a whole would ordinarily mean in this trade ("" if nothing)
    reasoning: str
    affected_terms: list[str]     # the applicant's goods/services the meaning describes
    options: list[str]
    model: str = ""


class Route(BaseModel):
    """Which kind of application to make, judged from the kind of problem found."""
    recommended: Literal["word", "composite", "new_name", "narrow_goods", "logo"]
    headline: str
    reasons: list[str]


class Report(BaseModel):
    mark: str
    mark_kind: MarkKind = "word"
    overall_risk: Risk
    conflicts: list[Conflict]
    picklist: list[PicklistResult]
    picklist_only: bool
    distinctiveness: list[DistinctivenessFlag]
    wholly_descriptive: bool = False  # every word of the mark describes or praises the goods/services
    escalate: bool
    escalation_reasons: list[str]
    notes: list[str] = []
    own_marks: list[str] = []  # numbers of the applicant's own marks/applications, left out of the conflicts
    register_warning: str | None = None  # e.g. results came from IP Australia's test copy of the register
    ai_distinctiveness: AiDistinctiveness | None = None
    ai_distinctiveness_unavailable: str | None = None  # why the AI assessment didn't run, if it didn't
    route: Route | None = None
    disclaimers: list[str]
