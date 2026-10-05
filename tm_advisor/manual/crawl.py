"""Politely downloads the Trade Marks Manual: obeys robots.txt, one request at a time, a pause between requests.

Run it from the command line (see README); it writes one JSON line per page, then builds the search index.
"""

import json
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from .parse import manual_links

START_URL = "https://manuals.ipaustralia.gov.au/trademark"
USER_AGENT = "TM-Advisor-Manual-Indexer/0.2 (+https://github.com/successmeter/tm-checker-and-advise)"


def crawl(start_url: str = START_URL, out_file: str | Path = "data/manual/pages.jsonl", *, delay: float = 1.0,
          max_pages: int | None = None, min_pages: int = 0, client: httpx.Client | None = None,
          sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> int:
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
    robots = _robots(client, start_url)
    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")  # the previous download stays usable until this one finishes

    queue, seen, saved = deque([start_url]), {start_url}, 0
    with partial.open("w", encoding="utf-8") as f:
        while queue and (max_pages is None or saved < max_pages):
            url = queue.popleft()
            if not robots.can_fetch(USER_AGENT, url):
                log(f"skip (robots.txt): {url}")
                continue
            if saved:
                sleep(delay)
            response = client.get(url)
            if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
                log(f"skip ({response.status_code}): {url}")
                continue
            f.write(json.dumps({"url": url, "html": response.text}) + "\n")
            saved += 1
            if saved == 1 or saved % 50 == 0:
                log(f"saved {saved} pages so far…")
            for link in manual_links(url, response.text):
                if link not in seen:
                    seen.add(link)
                    queue.append(link)
    if saved < max(min_pages, 1):
        raise SystemExit(f"Only {saved} Manual pages downloaded (expected at least {min_pages}). Keeping the current "
                         "copy; the site may be down or may have changed.")
    partial.replace(out)
    return saved


def _robots(client: httpx.Client, start_url: str) -> robotparser.RobotFileParser:
    parts = urlparse(start_url)
    parser = robotparser.RobotFileParser()
    response = client.get(f"{parts.scheme}://{parts.netloc}/robots.txt")
    parser.parse(response.text.splitlines() if response.status_code == 200 else [])
    return parser
