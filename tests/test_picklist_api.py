import httpx
import pytest

from tm_advisor.picklist import Picklist
from tm_advisor.picklist_api import sync

BASE = "https://api.example/tmgns-search-api/v1"


def api(class_rows, pages_for):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.endswith("/access_token"):
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        if path.endswith("/tradeMarkClasses"):
            return httpx.Response(200, json=class_rows)
        class_id = path.split("/")[-2]
        page = int(request.url.params.get("page", 0))
        return httpx.Response(200, json=pages_for(class_id, page))

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("IPA_CLIENT_ID", " id ")
    monkeypatch.setenv("IPA_CLIENT_SECRET", "secret")
    monkeypatch.setenv("IPA_TOKEN_URL", "https://auth.example/access_token")


def test_downloads_every_class_with_paging(tmp_path):
    classes = [{"id": f"c{n}", "classNumber": n, "title": "x"} for n in range(1, 46)]

    def pages(class_id, page):
        n = int(class_id[1:])
        if n == 25:  # Spring-style paging over two pages
            rows = [{"id": f"25-{page}-{i}", "description": f"Clothing item {page}-{i}"} for i in range(2)]
            return {"content": rows, "totalPages": 2, "number": page}
        return {"content": [{"id": f"{n}-1", "description": f"Term {n}"}], "totalPages": 1}

    http, calls = api(classes, pages)
    out = tmp_path / "picklist.json"
    change = sync(out, http=http, base=BASE, delay=0, log=lambda _: None)

    assert change.after == 44 + 4
    picklist = Picklist.load(out)
    assert picklist.match(25, "Clothing item 1-1").id == "25-1-1"
    assert picklist.match(9, "Term 9") is not None
    assert not picklist.is_sample
    assert sum(1 for c in calls if c.url.path.endswith("/access_token")) == 1  # token reused
    assert any(c.url.path == "/tmgns-search-api/v1/tradeMarkClasses/c25/descriptions" for c in calls)


def test_plain_lists_are_understood(tmp_path):
    http, _ = api(list(range(1, 46)), lambda class_id, page: [f"Plain term {class_id}"] if page == 0 else [])
    change = sync(tmp_path / "p.json", http=http, base=BASE, delay=0, log=lambda _: None)
    assert change.after == 45


def test_empty_class_stops_without_replacing_the_list(tmp_path):
    http, _ = api([{"classNumber": 1}], lambda class_id, page: {"content": []})
    out = tmp_path / "p.json"
    out.write_text('{"items": []}')
    with pytest.raises(SystemExit, match="No terms returned for class 1"):
        sync(out, http=http, base=BASE, delay=0, log=lambda _: None)
    assert out.read_text() == '{"items": []}'


def test_explains_what_is_needed_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("IPA_CLIENT_ID")
    with pytest.raises(SystemExit, match="needs IP Australia API access"):
        sync(tmp_path / "p.json")
