"""Request and report shapes shared by the engine and the API."""

from enum import Enum

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
    mark: str = Field(min_length=1, max_length=200)
    classes: list[ClassSpec] = Field(min_length=1)

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

    @property
    def is_live(self) -> bool:
        """Registered, accepted or still pending: only these can be cited under s44."""
        status = self.status.lower()
        return not any(word in status for word in ("lapsed", "removed", "refused", "withdrawn", "expired", "never registered", "cancelled", "revoked"))


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


class PicklistResult(BaseModel):
    class_number: int
    term: str
    on_picklist: bool
    suggestions: list[str]


class DistinctivenessFlag(BaseModel):
    word: str
    reason: str


class Report(BaseModel):
    mark: str
    overall_risk: Risk
    conflicts: list[Conflict]
    picklist: list[PicklistResult]
    picklist_only: bool
    distinctiveness: list[DistinctivenessFlag]
    escalate: bool
    escalation_reasons: list[str]
    disclaimers: list[str]
