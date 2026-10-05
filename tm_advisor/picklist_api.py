"""Downloads the full goods & services picklist from IP Australia's TMGnS search API.

These are the endpoints IP Australia's own classification search (tmgns.search.ipaustralia.gov.au) uses:
  GET {base}/tradeMarkClasses                    the 45 classes
  GET {base}/tradeMarkClasses/{id}/descriptions   every picklist term in a class
They need your own API access from the IP Australia API portal (IPA_CLIENT_ID and IPA_CLIENT_SECRET).

The response shapes aren't documented publicly, so field names are matched loosely and paging is followed when the
response says there is more. Check the first real download and tighten this if needed.

Usage:  python -m tm_advisor.picklist_api [--force]
"""

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from .ipa_auth import IpaToken, has_credentials
from .picklist_sync import PicklistChange, save

SEARCH_BASE = "https://production.api.ipaustralia.gov.au/public/tmgns-search-api/v1"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "picklist.json"

_LIST_KEYS = ("content", "items", "results", "data", "descriptions", "tradeMarkClasses", "goodsAndServicesDescriptions")
_TEXT_KEYS = ("description", "descriptionText", "text", "term", "name", "value")
_ID_KEYS = ("id", "descriptionId", "gsDescriptionId", "termId")
_CLASS_KEYS = ("classNumber", "number", "class", "niceClass", "tradeMarkClass", "id")


def _rows(body) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in _LIST_KEYS:
            if isinstance(body.get(key), list):
                return body[key]
        if isinstance(body.get("_embedded"), dict):
            return _rows(body["_embedded"])
        return next((v for v in body.values() if isinstance(v, list)), [])
    return []


def _first(row: dict, keys: tuple[str, ...]):
    lowered = {k.lower(): v for k, v in row.items()}
    return next((lowered[k.lower()] for k in keys if lowered.get(k.lower()) not in (None, "")), None)


def _has_more(body, page: int, got: int) -> bool:
    if not isinstance(body, dict) or not got:
        return False
    if body.get("last") is True:
        return False
    for key in ("totalPages", "pageCount"):
        if isinstance(body.get(key), int):
            return page + 1 < body[key]
    page_info = body.get("page")
    if isinstance(page_info, dict) and isinstance(page_info.get("totalPages"), int):
        return page_info.get("number", page) + 1 < page_info["totalPages"]
    return bool(body.get("next") or (isinstance(body.get("links"), dict) and body["links"].get("next")))


def classes(http: httpx.Client, token: IpaToken, base: str) -> list[tuple[str, int]]:
    """(id used in URLs, class number) for each class."""
    response = http.get(f"{base}/tradeMarkClasses", headers=token.headers())
    response.raise_for_status()
    found = []
    for row in _rows(response.json()):
        if isinstance(row, dict):
            number = _first(row, _CLASS_KEYS)
            ident = _first(row, ("id", "classId", "code")) or number
        else:
            number = ident = row
        try:
            n = int(str(number).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 45:
            found.append((str(ident), n))
    return sorted(set(found), key=lambda c: c[1]) or [(str(n), n) for n in range(1, 46)]


def descriptions(http: httpx.Client, token: IpaToken, base: str, class_id: str, page_size: int = 1000,
                 max_pages: int = 500, pause: Callable[[], None] = lambda: None) -> list[tuple[str, str]]:
    """(id, description) for every term in one class, following paging."""
    terms: dict[str, str] = {}
    for page in range(max_pages):
        response = http.get(f"{base}/tradeMarkClasses/{class_id}/descriptions",
                            params={"page": page, "size": page_size}, headers=token.headers())
        response.raise_for_status()
        body = response.json()
        rows = _rows(body)
        new = 0
        for row in rows:
            text = _first(row, _TEXT_KEYS) if isinstance(row, dict) else row
            text = " ".join(str(text or "").split())
            if not text:
                continue
            ident = str(_first(row, _ID_KEYS) or "") if isinstance(row, dict) else ""
            key = ident or text.lower()
            if key not in terms:
                terms[key] = text
                new += 1
        if not new or not _has_more(body, page, len(rows)):
            break
        pause()
    return [(k, v) for k, v in terms.items()]


def sync(out: Path = OUT, *, http: httpx.Client | None = None, base: str | None = None, force: bool = False,
         delay: float = 0.5, log: Callable[[str], None] = print) -> PicklistChange:
    if http is None and not has_credentials():
        raise SystemExit("The full picklist needs IP Australia API access. Register on the IP Australia API portal, "
                         "then set IPA_CLIENT_ID and IPA_CLIENT_SECRET.")
    http = http or httpx.Client(timeout=60)
    base = (base or os.environ.get("TMGNS_SEARCH_BASE") or SEARCH_BASE).rstrip("/")
    token = IpaToken.from_env(http)
    items: list[dict] = []
    for class_id, number in classes(http, token, base):
        time.sleep(delay) if delay else None
        terms = descriptions(http, token, base, class_id, pause=(lambda: time.sleep(delay)) if delay else (lambda: None))
        if not terms:
            raise SystemExit(f"No terms returned for class {number}. The API response may have changed; "
                             "keeping the current list.")
        seen = set()
        for n, (ident, text) in enumerate(terms, 1):
            if text.lower() in seen:
                continue
            seen.add(text.lower())
            items.append({"id": ident if ident and not ident.lower() == text.lower() else f"{number}-{n}",
                          "class_number": number, "description": text})
        log(f"class {number}: {len(seen)} terms")
    return save(items, out, source=f"IP Australia TMGnS search API ({base})", force=force)


def main() -> None:
    change = sync(force="--force" in sys.argv)
    print(f"Saved the picklist to {OUT}. {change.summary()}")


if __name__ == "__main__":
    main()
