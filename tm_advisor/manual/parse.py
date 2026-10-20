"""Turns a Trade Marks Manual web page into titled sections and search-sized chunks."""

import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

MANUAL_HOST = "manuals.ipaustralia.gov.au"
MANUAL_PATH = "/trademark"
_JUNK = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]
_HEADINGS = {"h2", "h3", "h4"}
_TEXT = {"p", "li", "td", "th", "dd", "dt", "blockquote", "pre"}
_PUBLISHED = re.compile(r"Date\s+Published\s*:?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I)


@dataclass
class Section:
    heading: str
    text: list[str] = field(default_factory=list)


@dataclass
class Page:
    url: str
    title: str
    sections: list[Section]
    published: str = ""  # the page's "Date Published", e.g. "10 Oct 2023"


@dataclass(frozen=True)
class Chunk:
    id: str
    url: str
    title: str
    heading: str
    text: str
    published: str = ""


def manual_links(base_url: str, html: str) -> list[str]:
    """Links on the page that point at other Trade Marks Manual pages, without fragments or queries."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        url, _ = urldefrag(urljoin(base_url, a["href"]))
        parts = urlparse(url)
        if parts.netloc != urlparse(base_url).netloc or not parts.path.startswith(MANUAL_PATH):
            continue
        url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        if url not in found:
            found.append(url)
    return found


def parse_page(url: str, html: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    found = _PUBLISHED.search(soup.get_text(" "))
    published = " ".join(found.group(1).split()) if found else ""
    for tag in soup(_JUNK):
        tag.decompose()
    body = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.find(class_="content") or soup.body or soup

    h1 = body.find("h1")
    title = _clean(h1.get_text(" ")) if h1 else _clean(title_tag.get_text(" ") if title_tag else url)
    title = re.sub(r"\s*-\s*IPA Manuals\s*$", "", title)

    sections = [Section(heading=title)]
    for el in body.find_all(list(_HEADINGS | _TEXT)):
        if el.name in _HEADINGS:
            sections.append(Section(heading=_clean(el.get_text(" "))))
        elif not el.find(list(_TEXT)):  # skip containers whose children are visited separately
            text = _clean(el.get_text(" "))
            if text:
                sections[-1].text.append(text)
    sections = [s for s in sections if s.text]
    for section in sections:  # the date line itself is page furniture, not Manual text
        section.text = [t for t in section.text if not _PUBLISHED.fullmatch(t)]
    return Page(url=url, title=title, sections=[s for s in sections if s.text], published=published)


def chunk_page(page: Page, max_words: int = 350, overlap: int = 40) -> list[Chunk]:
    """One chunk per section, split further when a section is long, with a little overlap between pieces."""
    chunks: list[Chunk] = []
    slug = urlparse(page.url).path.rstrip("/").rsplit("/", 1)[-1] or "index"
    for section in page.sections:
        words = " ".join(section.text).split()
        start = 0
        while start < len(words):
            piece = words[start:start + max_words]
            chunks.append(Chunk(id=f"{slug}#{len(chunks) + 1}", url=page.url, title=page.title,
                                heading=section.heading, text=" ".join(piece), published=page.published))
            if start + max_words >= len(words):
                break
            start += max_words - overlap
    return chunks


def _clean(text: str) -> str:
    return " ".join(text.split())
