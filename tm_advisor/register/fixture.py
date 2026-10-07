import json
from pathlib import Path

from ..mark_similarity import compare
from ..models import RegisterMark
from .terms import RegisterTerm, terms_from_marks


class FixtureRegisterClient:
    """A local stand-in for the register, used until IP Australia API access is approved."""

    def __init__(self, marks: list[RegisterMark]):
        self.marks = marks

    @classmethod
    def load(cls, path: str | Path) -> "FixtureRegisterClient":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([RegisterMark(**m) for m in data["marks"]])

    def search(self, mark: str, classes: list[int]) -> list[RegisterMark]:
        return [m for m in self.marks if compare(mark, m.words).score >= 0.5]

    def goods_terms(self, query: str, limit: int = 60) -> list[RegisterTerm]:
        return terms_from_marks(self.marks, query, limit)
