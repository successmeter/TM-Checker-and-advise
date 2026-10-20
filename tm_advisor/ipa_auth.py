"""OAuth2 client-credentials tokens for IP Australia's APIs (issued through the IP Australia API portal)."""

import os
import time

import httpx

# IP Australia's External Token API. Test and production each have their own (docs/api/api.json, tokenUrl).
DEFAULT_TOKEN_URL = "https://production.api.ipaustralia.gov.au/public/external-token-api/v1/access_token"
TEST_TOKEN_URL = "https://test.api.ipaustralia.gov.au/public/external-token-api/v1/access_token"


def token_url_for(base_url: str | None) -> str:
    """The token endpoint for the environment an API base URL belongs to, unless IPA_TOKEN_URL overrides it."""
    if os.environ.get("IPA_TOKEN_URL"):
        return os.environ["IPA_TOKEN_URL"]
    return TEST_TOKEN_URL if base_url and "//test.api.ipaustralia.gov.au" in base_url else DEFAULT_TOKEN_URL


def has_credentials() -> bool:
    return bool(os.environ.get("IPA_CLIENT_ID") and os.environ.get("IPA_CLIENT_SECRET"))


class IpaToken:
    def __init__(self, client_id: str, client_secret: str, token_url: str, http: httpx.Client):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self._http = http
        self._token: str | None = None
        self._expires = 0.0

    @classmethod
    def from_env(cls, http: httpx.Client, base_url: str | None = None) -> "IpaToken":
        return cls(os.environ["IPA_CLIENT_ID"].strip(), os.environ["IPA_CLIENT_SECRET"].strip(),
                   token_url_for(base_url or os.environ.get("IPA_BASE_URL")), http)

    def headers(self, accept: str = "application/json") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token()}", "Accept": accept}

    def access_token(self) -> str:
        if self._token and time.time() < self._expires - 30:
            return self._token
        response = self._http.post(self.token_url, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        if response.status_code in (400, 401):
            # Some OAuth servers only accept the credentials as HTTP Basic auth.
            response = self._http.post(self.token_url, data={"grant_type": "client_credentials"},
                                       auth=(self.client_id, self.client_secret))
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        self._expires = time.time() + float(body.get("expires_in", 300))
        return self._token
