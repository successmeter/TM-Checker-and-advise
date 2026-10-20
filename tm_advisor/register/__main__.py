"""Check your IP Australia API access from the command line.

  python -m tm_advisor.register "EcoKnit"
  python -m tm_advisor.register "BizImprint" --class 42 --find 1574635

--class searches within that class, as the website does. --find shows, for each search the website runs, how many
marks came back and whether that trade mark number was among them.

Uses IPA_CLIENT_ID, IPA_CLIENT_SECRET and IPA_BASE_URL (test or production) from the environment, runs the same
search the website runs, and prints what came back, or the error, so access problems are easy to see.
"""

import argparse
import os

import httpx

from ..ipa_auth import has_credentials
from ..mark_similarity import compare
from .ipaustralia import PRODUCTION_BASE, IpAustraliaRegisterClient, _advanced_queries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mark", nargs="*")
    parser.add_argument("--class", dest="classes", type=int, action="append", default=[])
    parser.add_argument("--find")
    args = parser.parse_args()
    mark = " ".join(args.mark).strip() or "EcoKnit"
    if not has_credentials():
        raise SystemExit("Set IPA_CLIENT_ID and IPA_CLIENT_SECRET first (from your client application in the IP Australia portal).")
    client = IpAustraliaRegisterClient.from_env()
    base = os.environ.get("IPA_BASE_URL", PRODUCTION_BASE)
    print(f"Searching {'TEST' if 'test.' in base else 'PRODUCTION'} register for: {mark}")
    try:
        if args.find:
            _trace(client, mark, args.classes, args.find)
        marks = client.search(mark, args.classes)
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500]
        hint = {400: "The login was refused: check the client ID and secret were copied fully, and that they belong to "
                     "the same environment (Test or Production) as IPA_BASE_URL.",
                401: "The client ID or secret was not accepted.",
                403: "These credentials aren't allowed to use this API or environment (check the access request "
                     "and that IPA_BASE_URL matches Test or Production)."}.get(e.response.status_code, "")
        raise SystemExit(f"IP Australia returned {e.response.status_code} for {e.request.url}\n{hint}\n{body}")
    except httpx.HTTPError as e:
        raise SystemExit(f"Could not reach IP Australia: {type(e).__name__}: {e}")
    print(f"Search method: {'advanced search' if client._advanced_available else 'quick search (advanced not enabled)'}")
    print(f"{len(marks)} marks found, most similar name first (score 0.5 or more is listed if the goods overlap).")
    scored = sorted(((compare(mark, m.words), m) for m in marks), key=lambda x: -x[0].score)
    for sim, m in scored:
        classes = ",".join(str(c.class_number) for c in m.classes)
        print(f"  {sim.score:4.2f}  {m.number:>8}  {m.words[:30]:<30}  {'LIVE' if m.is_live else 'dead'}  "
              f"{m.status[:30]:<30}  classes {classes}")


def _trace(client: IpAustraliaRegisterClient, mark: str, classes: list[int], number: str) -> None:
    client._headers()
    for text, kind in _advanced_queries(mark):
        for c in classes or [None]:
            records = client._try_page(text, kind, c)
            if isinstance(records, Exception):
                print(f"  {kind:<8} {text!r:<16} class {c}: failed: {records}")
                continue
            hit = next((r for r in records if str(r.get("number")) == number), None)
            print(f"  {kind:<8} {text!r:<16} class {c}: {len(records)} marks; {number} "
                  f"{'FOUND' if hit else 'not found'}")
            if hit:
                print(f"           record: words={hit.get('words')!r} status={hit.get('statusGroup')} "
                      f"classes={[g.get('classNumber', g) if isinstance(g, dict) else g for g in hit.get('goodsAndServices') or hit.get('classes') or []][:5]}")


if __name__ == "__main__":
    main()
