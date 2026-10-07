import json
from pathlib import Path

import httpx

from tm_advisor.register import FixtureRegisterClient, IpAustraliaRegisterClient

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "register_fixture.json"


def test_fixture_search_finds_similar_marks_only():
    client = FixtureRegisterClient.load(FIXTURE)
    found = {m.words for m in client.search("EcoKnit", [25])}
    assert found == {"ECO KNITWEAR", "ECOKNIT"}


def test_ip_australia_client_token_search_and_mapping():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/token"):
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        if request.url.path.endswith("/search/quick"):
            body = json.loads(request.content)
            return httpx.Response(200, json={"trademarkIds": ["2198432"] if body["query"] == "EcoKnit" else []})
        if request.url.path.endswith("/trade-mark/2198432"):
            return httpx.Response(200, json={
                "number": "2198432",
                "words": ["ECO KNITWEAR"],
                "statusGroup": "REGISTERED",
                "owner": [{"name": "Green Threads Pty Ltd"}],
                "goodsAndServices": [{"class": "25", "descriptionText": ["Knitted sweaters", "Cardigans"]}],
            })
        return httpx.Response(404)

    client = IpAustraliaRegisterClient("id", "secret", "https://auth.example/token", base_url="https://api.example/v1",
                                       transport=httpx.MockTransport(handler))
    marks = client.search("EcoKnit", [25])

    assert len(marks) == 1
    mark = marks[0]
    assert mark.words == "ECO KNITWEAR"
    assert mark.owner == "Green Threads Pty Ltd"
    assert mark.classes[0].class_number == 25
    assert mark.classes[0].terms == ["Knitted sweaters", "Cardigans"]
    assert mark.is_live
    token_calls = [c for c in calls if c.url.path.endswith("/token")]
    assert len(token_calls) == 1  # token is reused across requests
    queries = [json.loads(c.content)["query"] for c in calls if c.url.path.endswith("/search/quick")]
    assert queries == ["EcoKnit"]  # the squashed form is the same search, so it is not repeated


def test_queries_cover_whole_mark_squashed_form_and_long_words():
    from tm_advisor.register.ipaustralia import _queries
    assert _queries("Bondi Brew Co") == ["Bondi Brew Co", "bondibrewco", "bondi", "brew"]


SPEC = json.loads((Path(__file__).resolve().parents[1] / "docs" / "api" / "api.json").read_text())
DEFS = SPEC["definitions"]


def _props(name):
    return DEFS[name]["properties"]


def _enum(name, field):
    schema = _props(name)[field]
    return (schema.get("items") or schema)["enum"]


def test_advanced_search_returns_full_records_without_extra_lookups():
    example = DEFS["ApiTrademark"]["example"]  # the spec's own example record
    lapsed = {**example, "number": "999", "statusGroup": "NEVER_REGISTERED", "statusCode": "Never registered",
              "statusDetail": "Lapsed/not protected"}
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.url.path.endswith("/page/advanced")
        return httpx.Response(200, json={"count": 2, "trademarks": [example, lapsed]})

    client = IpAustraliaRegisterClient("id", "secret", "https://auth.example/token", base_url="https://api.example/v1",
                                       transport=httpx.MockTransport(handler))
    marks = client.search("Podicure Plus", [44])

    assert not any("/trade-mark/" in r.url.path for r in requests)
    first = next(m for m in marks if m.number == "1129102")
    assert first.words == "P PODICURE"
    assert first.status == "Registered: Registered/protected"
    assert first.is_live
    assert first.owner == "Diana Palin"
    assert first.classes[0].class_number == 44
    assert "Treatment of feet" in first.classes[0].terms
    assert not next(m for m in marks if m.number == "999").is_live

    bodies = [json.loads(r.content) for r in requests if r.url.path.endswith("/page/advanced")]
    kinds = [(b["rows"][0]["query"]["word"]["text"], b["rows"][0]["query"]["word"]["type"]) for b in bodies]
    assert kinds == [("podicure plus", "EXACT"), ("podicureplus", "FUZZY"), ("podicure plus", "PHONETIC"),
                     ("podicure", "PART"), ("plus", "PART")]


def test_requests_match_the_published_specification():
    from tm_advisor.register.ipaustralia import _advanced_queries, _quick_search_body

    quick = _quick_search_body("EcoKnit")
    assert set(quick) <= set(SPEC["paths"]["/search/quick"]["post"]["parameters"][0]["schema"]["properties"])
    assert set(quick["filters"]["quickSearchType"]) <= set(_enum("ApiQuickSearchFilters", "quickSearchType"))
    assert set(quick["filters"]["status"]) <= set(_enum("ApiQuickSearchFilters", "status"))

    word_types = DEFS["TrademarkApiWord"]["properties"]["type"]["enum"]
    assert {kind for _, kind in _advanced_queries("Eco Knit Wear")} <= set(word_types)
    assert "PENDING_REGISTERED" in _enum("TrademarkApiAdvancedSearch", "statuses")
    assert {"rows", "pageNumber", "pageSize"} <= set(_props("TrademarkApiAdvancedSearchPageRequest"))
    assert {"word", "statuses"} <= set(_props("TrademarkApiAdvancedSearch"))
    assert {"trademarks"} <= set(_props("ApiAdvancedSearchPageResult"))


def test_status_groups_decide_liveness():
    from tm_advisor.models import RegisterMark
    for group, live in [("REGISTERED", True), ("PENDING", True), ("REFUSED", False), ("REMOVED", False),
                        ("NEVER_REGISTERED", False), ("DISCONTINUED", False)]:
        assert RegisterMark(number="1", words="A", status="x", classes=[], status_group=group).is_live is live
    assert not RegisterMark(number="1", words="A", status="DISCONTINUED", classes=[]).is_live


def test_command_line_check_explains_missing_credentials(monkeypatch, capsys):
    import pytest
    from tm_advisor.register.__main__ import main
    monkeypatch.delenv("IPA_CLIENT_ID", raising=False)
    monkeypatch.setattr("sys.argv", ["x", "EcoKnit"])
    with pytest.raises(SystemExit, match="Set IPA_CLIENT_ID"):
        main()
