"""Client for IP Australia's Australian Trade Mark Search API.

Access is granted manually through the IP Australia API portal; the API uses OAuth2 client credentials.
Two endpoints are used: POST /search/quick (returns trade mark numbers) and GET /trade-mark/{number}.

The request filters and the response field names below follow the public description of the API but have
NOT yet been checked against a live response. When access is granted, record a real response, adjust
`_quick_search_body` and `_to_register_mark`, and update the tests.
"""

import os
import time

import httpx

from ..models import RegisterClass, RegisterMark
from ..text import squash, words

PRODUCTION_BASE = "https://production.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"
TEST_BASE = "https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"


class IpAustraliaRegisterClient:
    def __init__(self, client_id: str, client_secret: str, token_url: str, base_url: str = PRODUCTION_BASE,
                 transport: httpx.BaseTransport | None = None, max_results: int = 40):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.base_url = base_url.rstrip("/")
        self.max_results = max_results
        self._http = httpx.Client(transport=transport, timeout=20)
        self._token: str | None = None
        self._token_expires = 0.0

    @classmethod
    def from_env(cls) -> "IpAustraliaRegisterClient":
        return cls(
            client_id=os.environ["IPA_CLIENT_ID"],
            client_secret=os.environ["IPA_CLIENT_SECRET"],
            token_url=os.environ["IPA_TOKEN_URL"],
            base_url=os.environ.get("IPA_BASE_URL", PRODUCTION_BASE),
        )

    def search(self, mark: str, classes: list[int]) -> list[RegisterMark]:
        numbers: list[str] = []
        for query in _queries(mark):
            for number in self._quick_search(query):
                if number not in numbers:
                    numbers.append(number)
            if len(numbers) >= self.max_results:
                break
        return [self._get(n) for n in numbers[: self.max_results]]

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 30:
            return self._token
        response = self._http.post(self.token_url, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + float(body.get("expires_in", 300))
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"}

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
    status = data.get("statusGroup") or data.get("status") or ""
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
                        classes=classes)
