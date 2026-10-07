"""Client for IP Australia's Australian Trade Mark Search API.

Access is granted manually through the IP Australia API portal; the API uses OAuth2 client credentials.
Request and response shapes follow the API's published specification (docs/api/api.json, v1.0.5).

Main path: POST /page/advanced returns full trade mark records for a word search that IP Australia runs as
EXACT, FUZZY, PHONETIC and PART matches, limited to pending and registered marks. If that endpoint isn't
available to the account, the client falls back to POST /search/quick plus GET /trade-mark/{number} per hit.
"""

import os

import httpx

from ..ipa_auth import IpaToken, token_url_for
from ..models import RegisterClass, RegisterMark
from ..text import squash, words

PRODUCTION_BASE = "https://production.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"
TEST_BASE = "https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"


class IpAustraliaRegisterClient:
    def __init__(self, client_id: str, client_secret: str, token_url: str, base_url: str = PRODUCTION_BASE,
                 transport: httpx.BaseTransport | None = None, max_results: int = 40, page_size: int = 50):
        self.base_url = base_url.rstrip("/")
        self.max_results = max_results
        self.page_size = page_size
        self._advanced_available = True
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
                return self._advanced_search(mark)
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in (403, 404, 405, 501):
                    raise
                self._advanced_available = False  # not enabled for this account: use quick search from now on
        return self._quick_then_get(mark)

    def _advanced_search(self, mark: str) -> list[RegisterMark]:
        found: dict[str, RegisterMark] = {}
        for text, kind in _advanced_queries(mark):
            body = {
                "rows": [{"op": "AND", "query": {"word": {"text": text, "type": kind},
                                                  "statuses": ["PENDING_REGISTERED"]}}],
                "pageNumber": 0,
                "pageSize": self.page_size,
            }
            response = self._http.post(f"{self.base_url}/page/advanced", json=body, headers=self._headers())
            response.raise_for_status()
            for record in response.json().get("trademarks") or []:
                mark_ = _to_register_mark(record, str(record.get("number", "")))
                if mark_.number and mark_.number not in found:
                    found[mark_.number] = mark_
            if len(found) >= self.max_results * 3:
                break
        return list(found.values())

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
    """Whole mark exact, fuzzy and sound-alike; then each distinctive word as a part of other marks."""
    whole = " ".join(words(mark)) or mark
    queries = [(whole, "EXACT"), (squash(mark), "FUZZY"), (whole, "PHONETIC")]
    queries += [(w, "PART") for w in words(mark) if len(w) >= 4]
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

    return RegisterMark(number=str(data.get("number") or number), words=words_, status=str(status), owner=owner,
                        classes=classes, status_group=str(group) if group else None)
