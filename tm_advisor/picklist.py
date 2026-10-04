"""IP Australia's pre-approved goods and services picklist."""

import json
from dataclasses import dataclass
from pathlib import Path

from .text import normalise, stems

_FILLER = {"and", "of", "for", "in", "the", "to", "relation", "a", "being", "namely", "services"}


@dataclass(frozen=True)
class PicklistItem:
    id: str
    class_number: int
    description: str


class Picklist:
    def __init__(self, items: list[PicklistItem]):
        self.items = items
        self._by_class: dict[int, list[PicklistItem]] = {}
        for item in items:
            self._by_class.setdefault(item.class_number, []).append(item)

    @classmethod
    def load(cls, path: str | Path) -> "Picklist":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data["items"] if isinstance(data, dict) else data
        return cls([PicklistItem(str(r["id"]), int(r["class_number"]), r["description"]) for r in rows])

    def match(self, class_number: int, term: str) -> PicklistItem | None:
        """The picklist entry for this exact term (ignoring case, punctuation and plurals), if any."""
        wanted = _key(term)
        for item in self._by_class.get(class_number, []):
            if _key(item.description) == wanted:
                return item
        return None

    def suggest(self, class_number: int, term: str, limit: int = 3) -> list[str]:
        """Picklist entries in the class that share the most meaningful words with the term."""
        wanted = stems(term) - _FILLER
        scored = []
        for item in self._by_class.get(class_number, []):
            have = stems(item.description) - _FILLER
            common = len(wanted & have)
            if common:
                scored.append((-common, len(have), item.description))
        return [d for _, _, d in sorted(scored)[:limit]]

    def search(self, query: str, class_number: int | None = None, limit: int = 20) -> list[PicklistItem]:
        wanted = stems(query) - _FILLER
        if not wanted:
            return []
        pool = self._by_class.get(class_number, []) if class_number else self.items
        hits = [i for i in pool if wanted <= stems(i.description)]
        return sorted(hits, key=lambda i: (i.class_number, len(i.description)))[:limit]


def _key(text: str) -> str:
    return " ".join(sorted(stems(normalise(text))))
