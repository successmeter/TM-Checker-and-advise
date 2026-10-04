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
