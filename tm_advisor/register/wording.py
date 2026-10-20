"""A saved list of goods & services wording from registered trade marks, so every search covers all 45 classes.

  py -m tm_advisor.register.wording            read registered marks class by class and save data/register_wording.json
  py -m tm_advisor.register.wording --pages 5  fewer marks per class (quicker); default 10 pages of 100 marks
  py -m tm_advisor.register.wording --force    replace the saved list even if the new one is much smaller

IP Australia's picklist pages (tmgns.search.ipaustralia.gov.au) are built by JavaScript from an API that isn't
offered to the public, so they can't be saved. This builds the next best thing with your own Trade Mark Search API
access: the wording in the specifications of recently registered marks, which an examiner has accepted. Wording
used by at least two marks is kept, with how many marks use it. Uses IPA_CLIENT_ID, IPA_CLIENT_SECRET and
IPA_BASE_URL, like the register search. It is refreshed automatically with the other data.
"""

import argparse
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path

from ..text import stems
from .terms import MAX_TERM_LENGTH, RegisterTerm, split_terms

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "register_wording.json"
MIN_RATIO = 0.7
_FILLER = {"and", "of", "for", "in", "the", "to", "a", "relation", "services", "service", "being", "namely"}


class WordingChange:
    def __init__(self, before: int, after: int, marks: int):
        self.before, self.after, self.marks = before, after, marks

    def summary(self) -> str:
        return f"{self.after} wordings from {self.marks} registered marks (was {self.before})."


def collect(pages_for_class: Callable[[int], Iterable[list[dict]]], classes: Iterable[int] = range(1, 46),
            min_uses: int = 2, per_class: int = 5000, log: Callable[[str], None] = print) -> tuple[list[dict], int]:
    """Count each wording within the class it was registered in. Returns the terms and how many marks were read."""
    terms: list[dict] = []
    marks_read = 0
    for class_number in classes:
        counts: Counter[str] = Counter()
        shown: dict[str, str] = {}
        seen_marks: set[str] = set()
        for records in pages_for_class(class_number):
            for record in records:
                number = str(record.get("number", ""))
                if number in seen_marks or record.get("statusGroup") not in (None, "REGISTERED"):
                    continue
                seen_marks.add(number)
                in_mark: set[str] = set()
                for gs in record.get("goodsAndServices") or []:
                    if str(gs.get("class") or gs.get("classNumber") or "") != str(class_number):
                        continue
                    raw = gs.get("descriptionText") or []
                    for text in split_terms([raw] if isinstance(raw, str) else raw):
                        key = text.lower()
                        if key not in in_mark:
                            in_mark.add(key)
                            counts[key] += 1
                            shown.setdefault(key, text)
        kept = [(k, n) for k, n in counts.most_common() if n >= min_uses][:per_class]
        terms += [{"class_number": class_number, "description": shown[k], "uses": n} for k, n in kept]
        marks_read += len(seen_marks)
        log(f"class {class_number}: {len(seen_marks)} marks, {len(kept)} wordings kept")
    return terms, marks_read


def save(terms: list[dict], marks: int, path: Path = OUT, source: str = "", force: bool = False) -> WordingChange:
    path = Path(path)
    before = len(_load(path).get("terms", []))
    if before and len(terms) < before * MIN_RATIO and not force:
        raise SystemExit(f"The new list has {len(terms)} wordings, far fewer than the current {before}. "
                         "Keeping the current list. Use --force to replace it anyway.")
    if not terms:
        raise SystemExit("No wording was found. Keeping the current list.")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps({"source": source, "updated": date.today().isoformat(), "marks_read": marks,
                                   "terms": terms}, indent=0), encoding="utf-8")
    partial.replace(path)
    return WordingChange(before, len(terms), marks)


def harvest(client=None, out: Path = OUT, pages: int = 10, page_size: int = 100, delay: float = 0.12,
            force: bool = False, log: Callable[[str], None] = print) -> WordingChange:
    from ..ipa_auth import has_credentials
    from .ipaustralia import IpAustraliaRegisterClient

    if client is None:
        if not has_credentials():
            raise SystemExit("Building the wording list needs IP Australia API access: set IPA_CLIENT_ID and "
                             "IPA_CLIENT_SECRET (and IPA_BASE_URL for the test environment).")
        client = IpAustraliaRegisterClient.from_env()

    def pages_for_class(class_number: int):
        for page in range(pages):
            records = client.registered_in_class(class_number, page, page_size)
            if delay:
                time.sleep(delay)  # stays well under the API's per-minute limit
            yield records
            if len(records) < page_size:
                return

    terms, marks = collect(pages_for_class, log=log)
    return save(terms, marks, out, source=f"Registered trade marks via IP Australia Trade Mark Search API "
                                          f"({client.base_url})", force=force)


class WordingIndex:
    """Searches the saved wording: every meaningful word of the query must appear, most used first."""

    def __init__(self, terms: list[dict], updated: str = "", marks_read: int = 0):
        self.updated, self.marks_read = updated, marks_read
        self.terms = [RegisterTerm(int(t["class_number"]), t["description"], int(t.get("uses", 1))) for t in terms]
        self._by_stem: dict[str, set[int]] = {}
        for i, term in enumerate(self.terms):
            for s in stems(term.description):
                self._by_stem.setdefault(s, set()).add(i)

    @classmethod
    def load(cls, path: Path = OUT) -> "WordingIndex":
        data = _load(Path(path))
        return cls(data.get("terms", []), data.get("updated", ""), data.get("marks_read", 0))

    def search(self, query: str, limit: int = 60, per_class: int = 15) -> list[RegisterTerm]:
        wanted = stems(query) - _FILLER
        if not wanted:
            return []
        hits = set.intersection(*(self._by_stem.get(s, set()) for s in wanted))
        ranked = sorted((self.terms[i] for i in hits), key=lambda t: (-t.uses, len(t.description)))
        shown: Counter[int] = Counter()
        result = []
        for term in ranked:
            if shown[term.class_number] < per_class:
                shown[term.class_number] += 1
                result.append(term)
            if len(result) >= limit:
                break
        return result


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(prog="py -m tm_advisor.register.wording", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, default=10, help="pages of 100 registered marks to read per class")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    change = harvest(pages=args.pages, force=args.force)
    print(f"Saved {OUT}. {change.summary()}")


if __name__ == "__main__":
    main()
