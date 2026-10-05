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


def save(items: list[dict], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"source": "IP Australia TMGnS API /gsDescriptionsFull", "items": items}, indent=1),
                          encoding="utf-8")


def _norm(key: str) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def _first(row: dict, keys: tuple[str, ...]):
    return next((row[k] for k in keys if row.get(k) not in (None, "")), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/picklist.json")
    parser.add_argument("--base-url", default=os.environ.get("TMGNS_BASE_URL", TMGNS_BASE))
    parser.add_argument("--from-file", help="parse a file you downloaded yourself instead of calling the API")
    args = parser.parse_args()

    if args.from_file:
        content = Path(args.from_file).read_bytes()
    else:
        with httpx.Client() as http:
            content = fetch(IpaToken.from_env(http), http, args.base_url)
    items = parse(content)
    if not items:
        raise SystemExit("No picklist rows recognised. Check the downloaded file's format and update picklist_sync.parse.")
    save(items, args.out)
    print(f"Saved {len(items)} picklist terms across {len({i['class_number'] for i in items})} classes to {args.out}")


if __name__ == "__main__":
    main()
