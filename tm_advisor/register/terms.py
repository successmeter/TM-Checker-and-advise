"""Goods & services wording taken from registered trade marks.

Registered marks have passed examination, so the wording in their specifications was accepted by an examiner.
When the full picklist isn't available, the most common accepted wordings that contain every word of a search
make good suggestions. They may or may not be picklist terms, so they are labelled with how often they're used.
"""

from collections import Counter
from dataclasses import dataclass

from ..models import RegisterMark
from ..text import stems

_FILLER = {"and", "of", "for", "in", "the", "to", "a", "relation", "services", "service", "being", "namely"}
MAX_TERM_LENGTH = 120


@dataclass(frozen=True)
class RegisterTerm:
    class_number: int
    description: str
    uses: int


def terms_from_marks(marks: list[RegisterMark], query: str, limit: int = 60) -> list[RegisterTerm]:
    """Wordings in the marks' goods & services that contain every meaningful word of the query, most used first."""
    wanted = stems(query) - _FILLER
    if not wanted:
        return []
    counts: Counter[tuple[int, str]] = Counter()
    shown: dict[tuple[int, str], str] = {}
    for mark in marks:
        if not mark.is_live:
            continue
        seen_in_mark: set[tuple[int, str]] = set()
        for cls in mark.classes:
            for raw in cls.terms:
                text = " ".join(raw.split()).strip(" ;,.")
                if not text or len(text) > MAX_TERM_LENGTH or not wanted <= stems(text):
                    continue
                key = (cls.class_number, text.lower())
                if key in seen_in_mark:
                    continue
                seen_in_mark.add(key)
                counts[key] += 1
                shown.setdefault(key, text)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0][1])))
    return [RegisterTerm(cls, shown[(cls, low)], uses) for (cls, low), uses in ranked[:limit]]
