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


@dataclass(frozen=True)
class ClassInfo:
    class_number: int
    title: str
    kind: str  # "goods" (classes 1-34) or "services" (35-45)


def load_classes(path: str | Path) -> dict[int, ClassInfo]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {c["class_number"]: ClassInfo(c["class_number"], c["title"], c["kind"]) for c in data["classes"]}


class Picklist:
    def __init__(self, items: list[PicklistItem]):
        self.items = items
        self.is_sample = False
        self.updated = ""  # date the list was downloaded from IP Australia
        self._by_class: dict[int, list[PicklistItem]] = {}
        self._stems: dict[str, set[str]] = {}
        for item in items:
            self._by_class.setdefault(item.class_number, []).append(item)
            self._stems[item.id] = stems(item.description) - _FILLER

    @classmethod
    def load(cls, path: str | Path) -> "Picklist":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data["items"] if isinstance(data, dict) else data
        picklist = cls([PicklistItem(str(r["id"]), int(r["class_number"]), r["description"]) for r in rows])
        picklist.is_sample = isinstance(data, dict) and "SAMPLE" in data.get("_note", "")
        picklist.updated = data.get("updated", "") if isinstance(data, dict) else ""
        return picklist

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


    def find(self, query: str, mode: str = "similar", kinds: set[str] | None = None,
             classes: dict[int, ClassInfo] | None = None, per_class: int = 60) -> list[tuple[int, list[PicklistItem]]]:
        """Matches grouped by class, best class first, like IP Australia's picklist search.

        exact: every word of the query appears in the description (plurals ignored).
        similar: any word matches, including longer forms (sweater -> sweatshirts is not matched, knit -> knitted is).
        """
        wanted = stems(query) - _FILLER
        if not wanted:
            return []
        scored: dict[int, list[tuple[float, PicklistItem]]] = {}
        for item in self.items:
            if kinds and classes and classes.get(item.class_number) and classes[item.class_number].kind not in kinds:
                continue
            have = self._stems[item.id]
            if mode == "exact":
                if not wanted <= have:
                    continue
                score = 10.0 - len(have - wanted) * 0.1
            else:
                score = 0.0
                for w in wanted:
                    if w in have:
                        score += 1
                    elif len(w) >= 4 and any(h.startswith(w) or (len(h) >= 4 and w.startswith(h)) for h in have):
                        score += 0.6
                if not score:
                    continue
                score += 0.5 if wanted <= have else 0  # all words present
                score -= len(have - wanted) * 0.05     # prefer shorter, closer descriptions
            scored.setdefault(item.class_number, []).append((score, item))

        groups = []
        for cls, hits in scored.items():
            hits.sort(key=lambda h: (-h[0], len(h[1].description)))
            groups.append((hits[0][0], len(hits), cls, [i for _, i in hits[:per_class]]))
        groups.sort(key=lambda g: (-g[0], -g[1], g[2]))
        return [(cls, items) for _, _, cls, items in groups]


def _key(text: str) -> str:
    return " ".join(sorted(stems(normalise(text))))
