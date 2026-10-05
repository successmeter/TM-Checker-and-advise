import json

import httpx
import pytest

from tm_advisor.picklist import Picklist
from tm_advisor.picklist_site import SITE, parse, sync


def page(terms, next_href=None):
    items = "".join(f'<li><a href="/d/{i}">{t}</a></li>' for i, t in enumerate(terms))
    nav = '<ul class="menu"><li>Home</li><li>Help</li></ul>'
    more = f'<a href="{next_href}">Next</a>' if next_href else ""
    return f"<html><body><header>{nav}</header><main><h1>Class</h1><ul>{items}</ul>{more}</main></body></html>"


def test_parse_picks_the_term_list_not_the_menu():
    terms, next_url = parse(page(["Adhesives for industrial purposes", "Fertilisers", "Compost"]),
                            f"{SITE}/descriptions?class=1", 1)
    assert terms == ["Adhesives for industrial purposes", "Fertilisers", "Compost"]
    assert next_url is None


def test_parse_table_layout():
    html = ("<table><thead><tr><th>Description</th></tr></thead><tbody>"
            "<tr><td>Paints</td></tr><tr><td>Varnishes</td></tr><tr><td>Lacquers</td></tr></tbody></table>")
    assert parse(html, f"{SITE}/descriptions?class=2", 2)[0] == ["Paints", "Varnishes", "Lacquers"]


def test_parse_follows_next_page_for_same_class_only():
    _, next_url = parse(page(["A term", "B term"], "/descriptions?class=3&page=2"), f"{SITE}/descriptions?class=3", 3)
    assert next_url == f"{SITE}/descriptions?class=3&page=2"
    _, other = parse(page(["A term", "B term"], "/descriptions?class=4&page=2"), f"{SITE}/descriptions?class=3", 3)
    assert other is None


def test_parse_json_response():
    body = json.dumps({"results": [{"description": "Soaps"}, {"description": "Perfumes"}]})
    assert parse(body, f"{SITE}/descriptions?class=3", 3)[0] == ["Soaps", "Perfumes"]


def test_sync_reads_all_classes_with_pagination(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        cls = int(request.url.params["class"])
        if request.url.params.get("page") == "2":
            return httpx.Response(200, text=page([f"Term {cls} c", f"Term {cls} d"]))
        nxt = f"/descriptions?class={cls}&page=2" if cls == 25 else None
        return httpx.Response(200, text=page([f"Term {cls} a", f"Term {cls} b"], nxt))

    sleeps = []
    out = tmp_path / "picklist.json"
    count = sync(out, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append, log=lambda _: None)

    assert count == 45 * 2 + 2
    picklist = Picklist.load(out)
    assert picklist.match(25, "Term 25 d") is not None
    assert not picklist.is_sample
    assert len(sleeps) == 45  # one pause between each of the 46 page requests


def test_sync_stops_with_advice_when_page_has_no_terms(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text='<html><body><div id="app"></div><script src="/app.js"></script></body></html>')

    with pytest.raises(SystemExit, match="probe"):
        sync(tmp_path / "p.json", client=httpx.Client(transport=httpx.MockTransport(handler)),
             sleep=lambda _: None, log=lambda _: None)
