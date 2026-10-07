"""Downloads the full goods & services picklist from IP Australia's TMGnS API into data/picklist.json.

GET /gsDescriptionsFull returns every description. IP Australia documents it as the one TMGnS endpoint that
does not answer in JSON, without saying which format it uses, so CSV, JSON and zipped files are all accepted
and the column names are matched loosely. Check the first real download and tighten this if needed.

Usage:  python -m tm_advisor.picklist_sync            (needs IPA_CLIENT_ID, IPA_CLIENT_SECRET, IPA_TOKEN_URL)
"""

import argparse
import csv
import io
import json
import os
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

from .ipa_auth import IpaToken

TMGNS_BASE = "https://production.api.ipaustralia.gov.au/public/tmgns-rest-api/v1"

_ID_KEYS = ("id", "descriptionid", "gsdescriptionid", "termid")
_CLASS_KEYS = ("classnumber", "class", "niceclass", "trademarkclass", "classid")
_TEXT_KEYS = ("description", "descriptiontext", "term", "text", "gsdescription", "name")
_STATUS_KEYS = ("status", "active", "isactive")


def fetch(token: IpaToken, http: httpx.Client, base_url: str = TMGNS_BASE) -> bytes:
    response = http.get(f"{base_url.rstrip('/')}/gsDescriptionsFull", headers=token.headers(accept="*/*"), timeout=300)
    response.raise_for_status()
    return response.content


def parse(content: bytes) -> list[dict]:
    """Picklist rows as {id, class_number, description}, skipping inactive and malformed rows."""
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            name = next(n for n in archive.namelist() if not n.endswith("/"))
            return parse(archive.read(name))

    text = content.decode("utf-8-sig")
    stripped = text.lstrip()
    if stripped.startswith(("[", "{")):
        data = json.loads(stripped)
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        rows = data
    else:
        rows = list(csv.DictReader(io.StringIO(text)))

    items: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for row in rows:
        flat = {_norm(k): v for k, v in row.items()}
        status = _first(flat, _STATUS_KEYS)
        if status is not None and str(status).strip().lower() in ("inactive", "false", "0", "deleted", "retired"):
            continue
        cls, description = _first(flat, _CLASS_KEYS), _first(flat, _TEXT_KEYS)
        try:
            cls = int(str(cls).strip())
        except (TypeError, ValueError):
            continue
        description = " ".join(str(description or "").split())
        if not (1 <= cls <= 45) or not description or (cls, description.lower()) in seen:
            continue
        seen.add((cls, description.lower()))
        items.append({"id": str(_first(flat, _ID_KEYS) or f"{cls}-{len(items) + 1}"), "class_number": cls,
                      "description": description})
    return items


MIN_RATIO = 0.7  # refuse a new list that is less than 70% the size of the current one


@dataclass
class PicklistChange:
    before: int
    after: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        text = f"{self.after} terms (was {self.before}): {len(self.added)} added, {len(self.removed)} removed."
        for label, terms in (("Added", self.added), ("Removed", self.removed)):
            if terms:
                text += f"\n  {label}: " + "; ".join(terms[:10]) + (f" … and {len(terms) - 10} more" if len(terms) > 10 else "")
        return text


def save(items: list[dict], path: str | Path, source: str = "IP Australia TMGnS API /gsDescriptionsFull",
         force: bool = False, extra: dict | None = None) -> PicklistChange:
    """Replace the picklist file, but only if the new list looks complete. Reports what changed."""
    path = Path(path)
    old = _load_items(path)
    change = _diff(old, items)
    if old and len(items) < len(old) * MIN_RATIO and not force:
        raise SystemExit(f"The new picklist has {len(items)} terms, far fewer than the current {len(old)}. "
                         "Keeping the current list; IP Australia's pages may have changed. "
                         "Use --force to replace it anyway.")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps({"source": source, "updated": date.today().isoformat(), **(extra or {}),
                                   "items": items}, indent=1),
                       encoding="utf-8")
    partial.replace(path)
    return change


def _load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    if isinstance(data, dict) and "SAMPLE" in data.get("_note", ""):
        return []
    return data.get("items", []) if isinstance(data, dict) else data


def _diff(old: list[dict], new: list[dict]) -> PicklistChange:
    def keys(rows):
        return {(int(r["class_number"]), r["description"].lower()): f"Class {r['class_number']}: {r['description']}" for r in rows}
    before, after = keys(old), keys(new)
    return PicklistChange(before=len(old), after=len(new),
                          added=sorted(after[k] for k in after.keys() - before.keys()),
                          removed=sorted(before[k] for k in before.keys() - after.keys()))


def _norm(key: str) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def _first(row: dict, keys: tuple[str, ...]):
    return next((row[k] for k in keys if row.get(k) not in (None, "")), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/picklist.json")
    parser.add_argument("--base-url", default=os.environ.get("TMGNS_BASE_URL", TMGNS_BASE))
    parser.add_argument("--from-file", help="parse a file you downloaded yourself instead of calling the API")
    parser.add_argument("--force", action="store_true", help="replace the list even if the new one is much smaller")
    args = parser.parse_args()

    if args.from_file:
        content = Path(args.from_file).read_bytes()
    else:
        with httpx.Client() as http:
            content = fetch(IpaToken.from_env(http), http, args.base_url)
    items = parse(content)
    if not items:
        raise SystemExit("No picklist rows recognised. Check the downloaded file's format and update picklist_sync.parse.")
    change = save(items, args.out, force=args.force)
    print(f"Saved the picklist to {args.out}. {change.summary()}")


if __name__ == "__main__":
    main()
