"""Client for IP Australia's Australian Trade Mark Search API.

Access is granted manually through the IP Australia API portal; the API uses OAuth2 client credentials.
Request and response shapes follow the API's published specification (docs/api/api.json, v1.0.5).

Main path: POST /page/advanced returns full trade mark records for a word search that IP Australia runs as
EXACT, FUZZY, PHONETIC and PART matches, limited to pending and registered marks. If that endpoint isn't
available to the account, the client falls back to POST /search/quick plus GET /trade-mark/{number} per hit.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from ..ipa_auth import IpaToken, token_url_for
from ..models import RegisterClass, RegisterMark
from ..text import squash, words
from .terms import RegisterTerm, terms_from_marks

log = logging.getLogger("uvicorn.error")

PRODUCTION_BASE = "https://production.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"
TEST_BASE = "https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"


class IpAustraliaRegisterClient:
    def __init__(self, client_id: str, client_secret: str, token_url: str, base_url: str = PRODUCTION_BASE,
                 transport: httpx.BaseTransport | None = None, max_results: int = 40, page_size: int = 100):
        self.base_url = base_url.rstrip("/")
        self.max_results = max_results
        self.page_size = page_size
        self._advanced_available = True
        self._class_type: str | None = "ASSOCIATED"  # the class plus its associated classes; None: no class filter
        self._terms_cache: dict[str, list[RegisterTerm]] = {}
        self._http = httpx.Client(transport=transport, timeout=20)
        self._token = IpaToken(client_id, client_secret, token_url, self._http)

    @classmethod
    def from_env(cls) -> "IpAustraliaRegisterClient":
        base_url = os.environ.get("IPA_BASE_URL") or PRODUCTION_BASE
        return cls(
            client_id=os.environ["IPA_CLIENT_ID"].strip(),
            client_secret=os.environ["IPA_CLIENT_SECRET"].strip(),
            token_url=token_url_for(base_url),
            base_url=base_url,
        )

    def search(self, mark: str, classes: list[int]) -> list[RegisterMark]:
        if self._advanced_available:
            try:
                return self._advanced_search(mark, classes)
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in (403, 404, 405, 501):
                    raise
                self._advanced_available = False  # not enabled for this account: use quick search from now on
        return self._quick_then_get(mark)

    def _advanced_search(self, mark: str, classes: list[int]) -> list[RegisterMark]:
        """Every word search, run within each of the applicant's classes and their associated classes.

        Searching the whole register returns mostly marks in unrelated classes (METER finds gauges and meters), and
        only the first page comes back, so the marks that matter would be crowded out. IP Australia's examiners
        search the application's classes together with the classes associated with them; so does this.
        """
        self._headers()  # get the access token once, before the parallel requests
        jobs = [(text, kind, c) for text, kind in _advanced_queries(mark) for c in (sorted(set(classes)) or [None])]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda job: self._try_page(*job), jobs))
        errors = [r for r in results if isinstance(r, Exception)]
        if errors and len(errors) == len(results):
            raise errors[0]  # nothing came back at all
        for e in errors[:3]:
            log.warning("One register search failed and was skipped: %s", e)
        found: dict[str, RegisterMark] = {}
        for records in (r for r in results if not isinstance(r, Exception)):
            for record in records:
                mark_ = _to_register_mark(record, str(record.get("number", "")))
                if mark_.number and mark_.number not in found:
                    found[mark_.number] = mark_
        return list(found.values())

    def _try_page(self, text: str, kind: str, class_number: int | None) -> list[dict] | Exception:
        try:
            return self._advanced_page(text, kind, class_number)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404, 405, 501):
                raise  # advanced search isn't enabled for this account: the caller switches to quick search
            return e
        except httpx.HTTPError as e:
            return e

    def _advanced_page(self, text: str, kind: str, class_number: int | None, attempt: int = 0) -> list[dict]:
        query: dict = {"word": {"text": text, "type": kind}, "statuses": ["PENDING_REGISTERED"]}
        if class_number is not None and self._class_type:
            query["classNumber"] = {"text": str(class_number), "type": self._class_type}
        body = {"rows": [{"op": "AND", "query": query}], "pageNumber": 0, "pageSize": self.page_size}
        response = self._http.post(f"{self.base_url}/page/advanced", json=body, headers=self._headers())
        if response.status_code == 400 and "classNumber" in query:
            # Class filter refused: try the class on its own, then no class filter at all.
            self._class_type = "SINGLE" if self._class_type == "ASSOCIATED" else None
            log.warning("IP Australia refused the class filter (%s); retrying with %s", response.text[:200],
                        self._class_type or "no class filter")
            return self._advanced_page(text, kind, class_number, attempt)
        if response.status_code == 429 and attempt < 3:  # too many requests: wait and try again
            time.sleep(min(float(response.headers.get("retry-after") or 1 + attempt), 5))
            return self._advanced_page(text, kind, class_number, attempt + 1)
        response.raise_for_status()
        return response.json().get("trademarks") or []

    def goods_terms(self, query: str, limit: int = 60, marks: int = 100) -> list[RegisterTerm]:
        """Accepted goods & services wording from registered marks whose specification contains the query."""
        key = " ".join(query.lower().split())
        if key in self._terms_cache:
            return self._terms_cache[key]
        body = {
            "rows": [{"op": "AND", "query": {"goodsAndServices": query, "statuses": ["REGISTERED"]}}],
            "pageNumber": 0,
            "pageSize": marks,
        }
        try:
            response = self._http.post(f"{self.base_url}/page/advanced", json=body, headers=self._headers())
            response.raise_for_status()
            records = response.json().get("trademarks") or []
        except httpx.HTTPError as e:
            log.warning("Goods and services lookup on the register failed: %s", e)
            return []
        result = terms_from_marks([_to_register_mark(r, str(r.get("number", ""))) for r in records], query, limit)
        if len(self._terms_cache) > 200:
            self._terms_cache.clear()
        self._terms_cache[key] = result
        return result

    def registered_in_class(self, class_number: int, page: int, page_size: int = 100) -> list[dict]:
        """One page of registered marks in a class, newest first (full records, for the wording list)."""
        body = {
            "rows": [{"op": "AND", "query": {"classNumber": {"text": str(class_number), "type": "SINGLE"},
                                              "statuses": ["REGISTERED"]}}],
            "pageNumber": page,
            "pageSize": page_size,
            "sort": {"field": "NUMBER", "direction": "DESCENDING"},
        }
        response = self._http.post(f"{self.base_url}/page/advanced", json=body, headers=self._headers())
        if response.status_code >= 400:
            raise SystemExit(f"Class {class_number}: IP Australia answered HTTP {response.status_code}: "
                             f"{response.text[:300]}")
        return response.json().get("trademarks") or []

    def _quick_then_get(self, mark: str) -> list[RegisterMark]:
        numbers: list[str] = []
        for query in _queries(mark):
            for number in self._quick_search(query):
                if number not in numbers:
                    numbers.append(number)
            if len(numbers) >= self.max_results:
                break
        return [self._get(n) for n in numbers[: self.max_results]]

    def _headers(self) -> dict[str, str]:
        return self._token.headers()

    def _quick_search(self, query: str) -> list[str]:
        response = self._http.post(f"{self.base_url}/search/quick", json=_quick_search_body(query), headers=self._headers())
        response.raise_for_status()
        body = response.json()
        ids = next((body[k] for k in ("trademarkIds", "tradeMarkIds", "ids", "results") if k in body), [])
        return [str(i if not isinstance(i, dict) else i.get("number") or i.get("id")) for i in ids]

    def _get(self, number: str) -> RegisterMark:
        response = self._http.get(f"{self.base_url}/trade-mark/{number}", headers=self._headers())
        response.raise_for_status()
        return _to_register_mark(response.json(), number)


def _queries(mark: str) -> list[str]:
    """The whole mark, its squashed form, and each longer word, so marks containing a part are found too."""
    queries = [mark, squash(mark)]
    queries += [w for w in words(mark) if len(w) >= 4]
    seen: list[str] = []
    for q in queries:
        if q and q.lower() not in (s.lower() for s in seen):
            seen.append(q)
    return seen


def _advanced_queries(mark: str) -> list[tuple[str, str]]:
    """Whole mark exact, fuzzy and sound-alike; each distinctive word as a part of other marks; the same start."""
    whole = " ".join(words(mark)) or mark
    queries = [(whole, "EXACT"), (squash(mark), "FUZZY"), (whole, "PHONETIC")]
    queries += [(w, "PART") for w in words(mark) if len(w) >= 4]
    if len(squash(mark)) >= 4:
        queries.append((squash(mark)[:3], "PREFIX"))  # marks that start the same way: REVMAX -> REVLAB, REVMAN
    seen: list[tuple[str, str]] = []
    for q in queries:
        if q[0] and q not in seen:
            seen.append(q)
    return seen


def _quick_search_body(query: str) -> dict:
    return {
        "query": query,
        "filters": {
            "quickSearchType": ["WORD"],
            "status": ["REGISTERED", "PENDING"],
        },
    }


def _to_register_mark(data: dict, number: str) -> RegisterMark:
    words_ = data.get("words") or data.get("markText") or ""
    if isinstance(words_, list):
        words_ = " ".join(words_)
    group = data.get("statusGroup")
    code, detail = data.get("statusCode"), data.get("statusDetail")
    status = ": ".join(str(v) for v in (code, detail) if v) or group or data.get("status") or ""
    if isinstance(status, dict):
        status = ": ".join(str(v) for v in status.values() if v)
    owners = data.get("owner") or data.get("owners") or []
    if isinstance(owners, dict):
        owners = [owners]
    owner = ", ".join(o.get("name", "") for o in owners if isinstance(o, dict)) or None

    classes: list[RegisterClass] = []
    for gs in data.get("goodsAndServices") or []:
        number_ = gs.get("class") or gs.get("classNumber")
        terms = gs.get("descriptionText") or gs.get("description") or []
        if isinstance(terms, str):
            terms = [t.strip() for t in terms.replace(";", ",").split(",") if t.strip()]
        if number_:
            classes.append(RegisterClass(class_number=int(number_), terms=terms))

    images = (data.get("images") or {}).get("images") if isinstance(data.get("images"), dict) else None
    kinds = data.get("kind") or []
    return RegisterMark(number=str(data.get("number") or number), words=words_, status=str(status), owner=owner,
                        classes=classes, status_group=str(group) if group else None,
                        image=images[0] if images else None,
                        logo=any(str(k).lower() in ("figurative", "fancy") for k in kinds))
