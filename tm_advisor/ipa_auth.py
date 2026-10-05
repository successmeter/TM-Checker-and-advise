"""OAuth2 client-credentials tokens for IP Australia's APIs (issued through the IP Australia API portal)."""

import os
import time

import httpx


class IpaToken:
    def __init__(self, client_id: str, client_secret: str, token_url: str, http: httpx.Client):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self._http = http
        self._token: str | None = None
        self._expires = 0.0

    @classmethod
    def from_env(cls, http: httpx.Client) -> "IpaToken":
        return cls(os.environ["IPA_CLIENT_ID"], os.environ["IPA_CLIENT_SECRET"], os.environ["IPA_TOKEN_URL"], http)

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
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        self._expires = time.time() + float(body.get("expires_in", 300))
        return self._token
