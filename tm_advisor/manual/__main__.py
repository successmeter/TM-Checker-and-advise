"""Download the Trade Marks Manual and build the search index.

  python -m tm_advisor.manual crawl      download every Manual page (about one per second), then index them
  python -m tm_advisor.manual index      rebuild the index from pages already downloaded
"""

import argparse

from . import build_index
from .crawl import START_URL, crawl

PAGES = "data/manual/pages.jsonl"
INDEX = "data/manual/manual.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tm_advisor.manual", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("crawl", help="download the Manual, then build the index")
    c.add_argument("--start", default=START_URL)
    c.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1)")
    c.add_argument("--max-pages", type=int, default=None)
    sub.add_parser("index", help="rebuild the index from downloaded pages")
    args = parser.parse_args()

    if args.command == "crawl":
        saved = crawl(args.start, PAGES, delay=args.delay, max_pages=args.max_pages)
        print(f"Downloaded {saved} pages to {PAGES}")
    print(f"Indexed {build_index(PAGES, INDEX)} chunks into {INDEX}")


if __name__ == "__main__":
    main()
