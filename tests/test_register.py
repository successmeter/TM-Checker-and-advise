import pytest
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
    assert sorted(kinds) == sorted([("podicure plus", "EXACT"), ("podicureplus", "FUZZY"),
                                    ("podicure plus", "PHONETIC"), ("podicure", "PART"), ("plus", "PART"),
                                    ("pod", "PREFIX")])
    assert all(b["rows"][0]["query"]["classNumber"] == {"text": "44", "type": "ASSOCIATED"} for b in bodies)
    assert {"classNumber"} <= set(_props("TrademarkApiAdvancedSearch"))
    assert "ASSOCIATED" in DEFS["TrademarkApiClass"]["properties"]["type"]["enum"]


def test_each_word_search_runs_in_every_class_and_falls_back_to_the_single_class():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        query = json.loads(request.content)["rows"][0]["query"]
        seen.append((query["classNumber"]["text"], query["classNumber"]["type"]))
        if query["classNumber"]["type"] == "ASSOCIATED":
            return httpx.Response(400, json={"message": "bad class type"})
        return httpx.Response(200, json={"trademarks": []})

    client = IpAustraliaRegisterClient("id", "secret", "https://auth.example/token", base_url="https://api.example/v1",
                                       transport=httpx.MockTransport(handler))
    client.search("Success Meter", [42, 35])
    singles = {c for c, t in seen if t == "SINGLE"}
    assert singles == {"35", "42"}
    assert sum(1 for c, t in seen if t == "SINGLE") == 2 * 6  # six word searches in each class


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


def test_token_endpoint_matches_the_environment(monkeypatch):
    from tm_advisor.ipa_auth import DEFAULT_TOKEN_URL, TEST_TOKEN_URL, token_url_for
    monkeypatch.delenv("IPA_TOKEN_URL", raising=False)
    assert token_url_for("https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1") == TEST_TOKEN_URL
    assert token_url_for("https://production.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1") == DEFAULT_TOKEN_URL
    assert token_url_for(None) == DEFAULT_TOKEN_URL
    assert TEST_TOKEN_URL == SPEC["securityDefinitions"]["security.oauth2_client_credentials"]["tokenUrl"]
    monkeypatch.setenv("IPA_TOKEN_URL", "https://custom/token")
    assert token_url_for("https://test.api.ipaustralia.gov.au/x") == "https://custom/token"


def test_test_credentials_use_the_test_login(monkeypatch):
    monkeypatch.setenv("IPA_CLIENT_ID", "id")
    monkeypatch.setenv("IPA_CLIENT_SECRET", "secret")
    monkeypatch.delenv("IPA_TOKEN_URL", raising=False)
    monkeypatch.setenv("IPA_BASE_URL", "https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1")
    client = IpAustraliaRegisterClient.from_env()
    assert client._token.token_url.startswith("https://test.api.ipaustralia.gov.au/")


def test_login_retries_with_basic_auth_when_form_credentials_are_refused():
    from tm_advisor.ipa_auth import IpaToken
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if "authorization" in request.headers:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})
        return httpx.Response(400, json={"error": "invalid_request"})

    token = IpaToken("id", "secret", "https://auth.example/token", httpx.Client(transport=httpx.MockTransport(handler)))
    assert token.access_token() == "tok"
    assert len(attempts) == 2
    assert attempts[1].headers["authorization"].startswith("Basic ")


def _client(handler):
    def wrapped(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return handler(json.loads(request.content)["rows"][0]["query"])
    return IpAustraliaRegisterClient("id", "secret", "https://auth.example/token", base_url="https://api.example/v1",
                                     transport=httpx.MockTransport(wrapped))


RECORD = {"number": "7", "words": ["SUCCESS BOX"], "statusGroup": "REGISTERED",
          "goodsAndServices": [{"class": "35", "descriptionText": ["advertising"]}]}


def test_without_any_class_filter_when_ip_australia_refuses_both_kinds():
    client = _client(lambda q: httpx.Response(400) if "classNumber" in q else httpx.Response(200, json={"trademarks": [RECORD]}))
    assert [m.number for m in client.search("Success Meter", [35])] == ["7"]


def test_one_failed_search_is_skipped_not_fatal():
    client = _client(lambda q: httpx.Response(500) if q["word"]["type"] == "PHONETIC"
                     else httpx.Response(200, json={"trademarks": [RECORD]}))
    assert [m.number for m in client.search("Success Meter", [35])] == ["7"]


def test_all_searches_failing_is_reported():
    client = _client(lambda q: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        client.search("Success Meter", [35])


def test_too_many_requests_is_retried(monkeypatch):
    import tm_advisor.register.ipaustralia as ipa
    monkeypatch.setattr(ipa.time, "sleep", lambda s: None)
    calls = []

    def handler(q):
        calls.append(q["word"]["type"])
        if calls.count(q["word"]["type"]) == 1 and q["word"]["type"] == "EXACT":
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"trademarks": [RECORD]})

    assert [m.number for m in _client(handler).search("Success Meter", [35])] == ["7"]
    assert calls.count("EXACT") == 2


def test_check_page_gets_a_readable_error_when_the_register_fails():
    from fastapi.testclient import TestClient
    from tm_advisor.api import create_app
    from tm_advisor.picklist import Picklist

    app = create_app(_client(lambda q: httpx.Response(500)),
                     Picklist.load(Path(__file__).resolve().parents[1] / "data" / "picklist_sample.json"),
                     ai_checks=False)
    response = TestClient(app).post("/api/check", json={"mark": "Success Meter", "consent": True,
                                                        "classes": [{"class_number": 35, "terms": ["advertising"]}]})
    assert response.status_code == 502 and "register search" in response.json()["detail"]


def test_a_mark_in_class_all_covers_every_class():
    from tm_advisor.register.ipaustralia import _to_register_mark
    mark = _to_register_mark({"number": "123", "words": ["SUCCESS"], "statusGroup": "REGISTERED",
                              "goodsAndServices": [{"class": "All", "descriptionText": ["All goods"]},
                                                   {"class": "Odd", "descriptionText": ["x"]}]}, "123")
    assert sorted({c.class_number for c in mark.classes}) == list(range(1, 46))

    from tm_advisor.goods_similarity import relate
    from tm_advisor.models import GoodsLevel
    c35 = next(c for c in mark.classes if c.class_number == 35)
    overlap = relate(35, ["business data analysis"], 35, c35.terms)
    assert overlap.level == GoodsLevel.SAME and not overlap.narrowing_helps
