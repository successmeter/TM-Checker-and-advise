"""Builds data/picklist.json from IP Australia's public classification search, one page per class.

  python -m tm_advisor.picklist_site probe    save class 1's page and show what was found (send this output if sync fails)
  python -m tm_advisor.picklist_site sync     read classes 1-45 (about one request per second) into data/picklist.json;
                                              keeps the current list if the new one is much smaller (--force overrides)

https://tmgns.search.ipaustralia.gov.au/descriptions?class=N lists the picklist terms for class N. The page layout
isn't documented, so the term list is found by shape: the largest list or table of short entries on the page.
Pagination links are followed. robots.txt is obeyed. Check IP Australia's copyright/licence terms before
publishing the data, and attribute IP Australia.
"""

import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from urllib import robotparser
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .picklist_sync import PicklistChange, save

SITE = "https://tmgns.search.ipaustralia.gov.au"
USER_AGENT = "TM-Advisor-Picklist/0.3 (+https://github.com/successmeter/tm-checker-and-advise)"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "picklist.json"
PROBE = ROOT / "data" / "picklist_probe.html"
_CONTAINERS = ["ul", "ol", "tbody", "table", "div", "section"]
_ITEMS = ["li", "tr", "a", "label", "p", "span", "div"]


def class_url(class_number: int) -> str:
    return f"{SITE}/descriptions?class={class_number}"


def parse(content: str, url: str, class_number: int) -> tuple[list[str], str | None]:
    """Terms on one page, and the next page's URL if there is one."""
    stripped = content.lstrip()
    if stripped.startswith(("{", "[")):
        return _parse_json(json.loads(stripped)), None

    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "noscript"]):
        tag.decompose()

    best: list[str] = []
    for container in soup.find_all(_CONTAINERS):
        for child_tag in _ITEMS:
            children = container.find_all(child_tag, recursive=False)
            if child_tag == "tr" and not children and container.name == "table":
                children = container.select("tbody > tr")
            texts = [_clean(c.get_text(" ")) for c in children]
            texts = [t for t in texts if 1 < len(t) <= 200 and not _looks_like_chrome(t)]
            if len(texts) > len(best):
                best = texts
    terms = list(dict.fromkeys(best))
    return terms, _next_page(soup, url, class_number)


def _parse_json(data) -> list[str]:
    rows = data
    if isinstance(data, dict):
        rows = next((v for v in data.values() if isinstance(v, list)), [])
    terms = []
    for row in rows:
        if isinstance(row, str):
            terms.append(_clean(row))
        elif isinstance(row, dict):
            text = next((row[k] for k in row if k.lower() in ("description", "descriptiontext", "term", "text", "name")), None)
            if text:
                terms.append(_clean(str(text)))
    return [t for t in dict.fromkeys(terms) if t]


def _next_page(soup: BeautifulSoup, url: str, class_number: int) -> str | None:
    current = _page_number(url)
    candidates = []
    for a in soup.find_all("a", href=True):
        target = urljoin(url, a["href"])
        query = parse_qs(urlparse(target).query)
        if query.get("class", [str(class_number)])[0] != str(class_number):
            continue
        page = _page_number(target)
        label = _clean(a.get_text(" ")).lower()
        if page == current + 1 or (page and page > current and label in ("next", "next page", ">", "›", "»")):
            candidates.append((page, target))
    return min(candidates)[1] if candidates else None


def _page_number(url: str) -> int:
    query = parse_qs(urlparse(url).query)
    for key in ("page", "p", "pageNumber", "pageNo"):
        if key in query and query[key][0].isdigit():
            return int(query[key][0])
    return 1


def _looks_like_chrome(text: str) -> bool:
    lower = text.lower()
    return lower in {"next", "previous", "first", "last", "home", "search", "help", "contact us"} or lower.isdigit()


def _clean(text: str) -> str:
    return " ".join(text.split())


class _Fetcher:
    def __init__(self, client: httpx.Client, delay: float, sleep: Callable[[float], None]):
        self.client, self.delay, self.sleep = client, delay, sleep
        self.robots = robotparser.RobotFileParser()
        response = client.get(f"{SITE}/robots.txt")
        self.robots.parse(response.text.splitlines() if response.status_code == 200 else [])
        self._first = True

    def get(self, url: str) -> httpx.Response | None:
        if not self.robots.can_fetch(USER_AGENT, url):
            return None
        if not self._first:
            self.sleep(self.delay)
        self._first = False
        return self.client.get(url)


def sync(out: Path = OUT, *, client: httpx.Client | None = None, delay: float = 1.0, max_pages_per_class: int = 200,
         force: bool = False, sleep: Callable[[float], None] = time.sleep,
         log: Callable[[str], None] = print) -> PicklistChange:
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
    fetcher = _Fetcher(client, delay, sleep)
    items: list[dict] = []
    for class_number in range(1, 46):
        url: str | None = class_url(class_number)
        terms: list[str] = []
        pages = 0
        while url and pages < max_pages_per_class:
            response = fetcher.get(url)
            if response is None:
                raise SystemExit(f"robots.txt does not allow reading {url}. Stopping.")
            if response.status_code != 200:
                raise SystemExit(f"Class {class_number}: HTTP {response.status_code} for {url}. Stopping.")
            page_terms, url = parse(response.text, str(response.url), class_number)
            new = [t for t in page_terms if t not in terms]
            if not new:
                break
            terms.extend(new)
            pages += 1
        if not terms:
            raise SystemExit(f"No terms found for class {class_number}. The page is probably built by JavaScript. "
                             "Run `python -m tm_advisor.picklist_site probe` and send the output.")
        items.extend({"id": f"{class_number}-{n}", "class_number": class_number, "description": t}
                     for n, t in enumerate(terms, 1))
        log(f"class {class_number}: {len(terms)} terms ({pages} page{'s' if pages != 1 else ''})")
    return save(items, out, source=f"IP Australia classification search ({SITE})", force=force)


def probe(client: httpx.Client | None = None, log: Callable[[str], None] = print) -> None:
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
    response = client.get(class_url(1))
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    PROBE.write_text(response.text, encoding="utf-8")
    soup = BeautifulSoup(response.text, "html.parser")
    terms, next_url = parse(response.text, str(response.url), 1)
    log(f"status {response.status_code}, type {response.headers.get('content-type')}, {len(response.text)} characters")
    log(f"title: {soup.title.get_text(strip=True) if soup.title else '(none)'}")
    log(f"terms found: {len(terms)}; first ones: {terms[:8]}")
    log(f"next page: {next_url}")
    scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
    log(f"scripts: {scripts[:10]}")
    urls = sorted(set(re.findall(r"https?://[^\s\"'<>]*api[^\s\"'<>]*", response.text)))[:10]
    log(f"API-looking URLs in the page: {urls}")
    log(f"Saved the page to {PROBE}")
    for src in scripts[:5]:
        script_url = urljoin(str(response.url), src)
        script = client.get(script_url)
        if script.status_code != 200:
            log(f"Couldn't read {script_url} ({script.status_code})")
            continue
        saved = PROBE.with_name("picklist_probe_" + Path(urlparse(script_url).path).name)
        saved.write_text(script.text, encoding="utf-8")
        found = data_addresses(script.text)
        log(f"Data addresses in {src} ({len(script.text)} characters):")
        for address in found[:40]:
            log(f"  {address}")
        if not found:
            log("  (none found)")


_ADDRESS = re.compile(r"""["'`]((?:https?://[^"'`\s]{4,200})|(?:/[A-Za-z0-9_\-./{}$?=&]{2,200}))["'`]""")
_INTERESTING = ("api", "description", "class", "gns", "picklist", "search", "term", "goods")


def data_addresses(script: str) -> list[str]:
    """URLs and paths in a JavaScript bundle that look like data endpoints."""
    found = []
    for match in _ADDRESS.finditer(script):
        address = match.group(1)
        lower = address.lower()
        if any(word in lower for word in _INTERESTING) and not lower.endswith((".js", ".css", ".svg", ".png", ".woff2")):
            if address not in found:
                found.append(address)
    return found


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "probe":
        probe()
    elif command == "sync":
        change = sync(force="--force" in sys.argv)
        print(f"Saved the picklist to {OUT}. {change.summary()}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
