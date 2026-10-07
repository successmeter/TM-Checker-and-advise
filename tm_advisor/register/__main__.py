"""Check your IP Australia API access from the command line.

  python -m tm_advisor.register "EcoKnit"

Uses IPA_CLIENT_ID, IPA_CLIENT_SECRET and IPA_BASE_URL (test or production) from the environment, runs the same
search the website runs, and prints what came back, or the error, so access problems are easy to see.
"""

import os
import sys

import httpx

from ..ipa_auth import has_credentials
from .ipaustralia import PRODUCTION_BASE, IpAustraliaRegisterClient


def main() -> None:
    mark = " ".join(sys.argv[1:]).strip() or "EcoKnit"
    if not has_credentials():
        sys.exit("Set IPA_CLIENT_ID and IPA_CLIENT_SECRET first (from your client application in the IP Australia portal).")
    client = IpAustraliaRegisterClient.from_env()
    base = os.environ.get("IPA_BASE_URL", PRODUCTION_BASE)
    print(f"Searching {'TEST' if 'test.' in base else 'PRODUCTION'} register for: {mark}")
    try:
        marks = client.search(mark, [])
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500]
        hint = {400: "The login was refused: check the client ID and secret were copied fully, and that they belong to "
                     "the same environment (Test or Production) as IPA_BASE_URL.",
                401: "The client ID or secret was not accepted.",
                403: "These credentials aren't allowed to use this API or environment (check the access request "
                     "and that IPA_BASE_URL matches Test or Production)."}.get(e.response.status_code, "")
        sys.exit(f"IP Australia returned {e.response.status_code} for {e.request.url}\n{hint}\n{body}")
    except httpx.HTTPError as e:
        sys.exit(f"Could not reach IP Australia: {type(e).__name__}: {e}")
    print(f"Search method: {'advanced search' if client._advanced_available else 'quick search (advanced not enabled)'}")
    print(f"{len(marks)} marks found.")
    for m in marks[:15]:
        classes = ",".join(str(c.class_number) for c in m.classes)
        print(f"  {m.number:>8}  {m.words[:40]:<40}  {'LIVE' if m.is_live else 'dead'}  {m.status[:40]}  classes {classes}")


if __name__ == "__main__":
    main()
