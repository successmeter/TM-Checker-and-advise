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
    change = sync(out, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append, log=lambda _: None)

    assert change.after == 45 * 2 + 2 and change.before == 0
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


def site(terms_for):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=page(terms_for(int(request.url.params["class"]))))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_resync_reports_added_and_removed_terms(tmp_path):
    out = tmp_path / "picklist.json"
    sync(out, client=site(lambda c: [f"Term {c} a", f"Term {c} b", f"Term {c} c"]), sleep=lambda _: None, log=lambda _: None)
    change = sync(out, client=site(lambda c: [f"Term {c} a", f"Term {c} b", f"Term {c} c"] + (["Brand new"] if c == 9 else [])
                                   if c != 25 else ["Term 25 a", "Term 25 b"]),
                  sleep=lambda _: None, log=lambda _: None)
    assert change.added == ["Class 9: Brand new"]
    assert change.removed == ["Class 25: Term 25 c"]
    assert "1 added, 1 removed" in change.summary()
    assert json.loads(out.read_text())["updated"]


def test_much_smaller_list_is_refused_and_current_list_kept(tmp_path):
    out = tmp_path / "picklist.json"
    sync(out, client=site(lambda c: [f"Term {c} {i}" for i in range(10)]), sleep=lambda _: None, log=lambda _: None)
    before = out.read_text()
    with pytest.raises(SystemExit, match="far fewer"):
        sync(out, client=site(lambda c: [f"Term {c} 0", f"Term {c} 1"]), sleep=lambda _: None, log=lambda _: None)
    assert out.read_text() == before
    change = sync(out, client=site(lambda c: [f"Term {c} 0", f"Term {c} 1"]), force=True,
                  sleep=lambda _: None, log=lambda _: None)
    assert change.after == 90


def test_data_addresses_found_in_a_script_bundle():
    from tm_advisor.picklist_site import data_addresses
    bundle = ('const a="https://api.example.gov.au/tmgns/v1/descriptions",b=`/api/classes/${n}/terms`;'
              'import("/assets/vendor.js");const c="/logo.svg",d="hello";fetch("/search/goods?q="+q)')
    assert data_addresses(bundle) == ["https://api.example.gov.au/tmgns/v1/descriptions", "/api/classes/${n}/terms",
                                      "/search/goods?q="]
