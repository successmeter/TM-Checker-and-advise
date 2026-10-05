"""Download the Trade Marks Manual and build the search index.

  python -m tm_advisor.manual crawl      download every Manual page (about one per second), then index them;
                                         does nothing if the Manual is already downloaded (add --refresh to update it)
  python -m tm_advisor.manual index      rebuild the index from pages already downloaded
"""

import argparse
from pathlib import Path

from . import ManualChange, build_index, compare, fingerprints
from .crawl import START_URL, crawl

# Always the project's data folder, whichever folder the command is run from.
DATA = Path(__file__).resolve().parents[2] / "data" / "manual"
PAGES = DATA / "pages.jsonl"
INDEX = DATA / "manual.sqlite"
MIN_RATIO = 0.7  # a refresh with far fewer pages than before is treated as a failure


def refresh(start: str = START_URL, delay: float = 1.0, max_pages: int | None = None) -> ManualChange:
    """Download the Manual again, keep the current copy if the download looks incomplete, rebuild the index."""
    old = fingerprints(PAGES)
    crawl(start, PAGES, delay=delay, max_pages=max_pages, min_pages=int(len(old) * MIN_RATIO))
    change = compare(old, fingerprints(PAGES))
    build_index(PAGES, INDEX)
    return change


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tm_advisor.manual", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("crawl", help="download the Manual, then build the index")
    c.add_argument("--start", default=START_URL)
    c.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1)")
    c.add_argument("--max-pages", type=int, default=None)
    c.add_argument("--refresh", action="store_true", help="download again even if the Manual is already downloaded")
    sub.add_parser("index", help="rebuild the index from downloaded pages")
    args = parser.parse_args()

    if args.command == "crawl":
        if PAGES.exists() and INDEX.exists() and not args.refresh:
            print(f"The Manual is already downloaded ({PAGES}). Nothing to do.\n"
                  "To download it again for updates, add --refresh. To rebuild only the index, use: index")
            return
        change = refresh(args.start, args.delay, args.max_pages)
        print(f"Downloaded the Manual to {PAGES}. {change.summary()}")
        print(f"Indexed it into {INDEX}")
        return
    if not PAGES.exists():
        raise SystemExit(f"No downloaded Manual at {PAGES}. Run the crawl command first.")
    print(f"Indexed {build_index(PAGES, INDEX)} chunks into {INDEX}")


if __name__ == "__main__":
    main()
