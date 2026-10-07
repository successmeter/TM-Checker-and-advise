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


class Application(BaseModel):
    mark: str = Field(min_length=1, max_length=200)  # for a logo: the words in the logo
    classes: list[ClassSpec] = Field(min_length=1)
    mark_kind: Literal["word", "logo"] = "word"

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


class Report(BaseModel):
    mark: str
    mark_kind: Literal["word", "logo"] = "word"
    overall_risk: Risk
    conflicts: list[Conflict]
    picklist: list[PicklistResult]
    picklist_only: bool
    distinctiveness: list[DistinctivenessFlag]
    escalate: bool
    escalation_reasons: list[str]
    notes: list[str] = []
    ai_distinctiveness: AiDistinctiveness | None = None
    ai_distinctiveness_unavailable: str | None = None  # why the AI assessment didn't run, if it didn't
    disclaimers: list[str]
