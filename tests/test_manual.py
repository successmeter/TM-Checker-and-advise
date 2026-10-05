import json
from pathlib import Path

import httpx

from tm_advisor.manual import ManualIndex, build_index, chunk_page, parse_page
from tm_advisor.manual.crawl import crawl
from tm_advisor.manual.parse import Page, Section, manual_links

FIXTURES = Path(__file__).parent / "fixtures" / "manual"
BASE = "https://manuals.ipaustralia.gov.au"


def html(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_manual_links_stay_in_trade_mark_manual():
    links = manual_links(f"{BASE}/trademark", html("index.html"))
    assert links == [
        f"{BASE}/trademark/1.-introduction-to-section-44",
        f"{BASE}/trademark/3.-similar-goods-and-services",
        f"{BASE}/trademark/1.-introduction-to-section-41",
    ]


def test_parse_page_drops_page_chrome_and_splits_on_headings():
    page = parse_page(f"{BASE}/trademark/3.-similar-goods-and-services", html("s44-goods.html"))
    assert page.title == "Part 26.3. Similar goods and closely related services"
    assert [s.heading for s in page.sections] == [
        "Part 26.3. Similar goods and closely related services",
        "3.1 Goods of the same description",
        "3.2 Closely related services",
    ]
    all_text = " ".join(t for s in page.sections for t in s.text)
    assert "Menu" not in all_text and "Related links" not in all_text and "Last updated" not in all_text
    assert "Clothing and knitted garments" in page.sections[1].text[1]


def test_parse_page_falls_back_to_content_div():
    page = parse_page(f"{BASE}/trademark/1.-introduction-to-section-41", html("s41-intro.html"))
    assert page.title == "Part 22.1. Introduction to section 41"
    assert page.sections[1].heading == "Evidence of use"


def test_long_sections_are_split_with_overlap():
    words = [f"w{i}" for i in range(100)]
    page = Page(url=f"{BASE}/trademark/x", title="T", sections=[Section("H", [" ".join(words)])])
    chunks = chunk_page(page, max_words=40, overlap=10)
    assert [c.id for c in chunks] == ["x#1", "x#2", "x#3"]
    assert chunks[1].text.split()[0] == "w30"
    assert chunks[-1].text.split()[-1] == "w99"


def test_index_search_ranks_relevant_chunk_first():
    chunks = chunk_page(parse_page(f"{BASE}/trademark/3.-similar", html("s44-goods.html")))
    chunks += chunk_page(parse_page(f"{BASE}/trademark/1.-s41", html("s41-intro.html")))
    index = ManualIndex()
    index.build(chunks)

    hits = index.search("goods of the same description clothing knitted")
    assert hits[0].heading == "3.1 Goods of the same description"
    assert index.search("laudatory words evidence of use")[0].url.endswith("1.-s41")
    assert index.search("the and of") == []
    assert index.get(hits[0].id) == hits[0]


def test_crawl_obeys_robots_and_builds_index(tmp_path):
    pages = {
        "/robots.txt": "User-agent: *\nDisallow: /trademark/1.-introduction-to-section-44\n",
        "/trademark": html("index.html"),
        "/trademark/3.-similar-goods-and-services": html("s44-goods.html"),
        "/trademark/1.-introduction-to-section-41": html("s41-intro.html"),
    }
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        body = pages.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        kind = "text/plain" if request.url.path == "/robots.txt" else "text/html; charset=utf-8"
        return httpx.Response(200, text=body, headers={"content-type": kind})

    sleeps = []
    out = tmp_path / "pages.jsonl"
    saved = crawl(f"{BASE}/trademark", out, client=httpx.Client(transport=httpx.MockTransport(handler)),
                  sleep=sleeps.append, log=lambda _: None)

    assert saved == 3
    assert "/trademark/1.-introduction-to-section-44" not in requested  # blocked by robots.txt
    assert sleeps == [1.0, 1.0]  # pause between requests, not before the first
    assert [json.loads(line)["url"] for line in out.read_text().splitlines()][0] == f"{BASE}/trademark"

    count = build_index(out, tmp_path / "manual.sqlite")
    assert count > 0
    assert ManualIndex(tmp_path / "manual.sqlite").search("closely related services retail")


def test_failed_crawl_keeps_previous_download(tmp_path):
    out = tmp_path / "pages.jsonl"
    out.write_text('{"url": "old", "html": ""}\n')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    saved = crawl(f"{BASE}/trademark", out, client=httpx.Client(transport=httpx.MockTransport(handler)),
                  sleep=lambda _: None, log=lambda _: None)
    assert saved == 0
    assert out.read_text() == '{"url": "old", "html": ""}\n'


def test_crawl_command_skips_when_already_downloaded(tmp_path, monkeypatch, capsys):
    import sys
    from tm_advisor.manual import __main__ as cli

    (tmp_path / "pages.jsonl").write_text("")
    (tmp_path / "manual.sqlite").write_text("")
    monkeypatch.setattr(cli, "PAGES", tmp_path / "pages.jsonl")
    monkeypatch.setattr(cli, "INDEX", tmp_path / "manual.sqlite")
    monkeypatch.setattr(cli, "crawl", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not crawl")))
    monkeypatch.setattr(sys, "argv", ["tm_advisor.manual", "crawl"])
    cli.main()
    assert "already downloaded" in capsys.readouterr().out
