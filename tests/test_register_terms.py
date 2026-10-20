import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tm_advisor.api import create_app
from tm_advisor.models import RegisterClass, RegisterMark
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient, IpAustraliaRegisterClient
from tm_advisor.register.terms import terms_from_marks

DATA = Path(__file__).resolve().parents[1] / "data"
SPEC = json.loads((Path(__file__).resolve().parents[1] / "docs" / "api" / "api.json").read_text())


def mark(number, status_group, *classes):
    return RegisterMark(number=number, words="X", status="s", status_group=status_group,
                        classes=[RegisterClass(class_number=c, terms=t) for c, t in classes])


MARKS = [
    mark("1", "REGISTERED", (35, ["Strategic business planning", "Advertising"]), (36, ["Strategic financial advisory services"])),
    mark("2", "REGISTERED", (35, ["strategic business planning ", "Business strategic planning services"])),
    mark("3", "REGISTERED", (35, ["Strategic business planning"]), (41, ["Wedding planning services"])),
    mark("4", "REMOVED", (35, ["Strategic planning for removed marks"])),
]


def test_terms_need_every_word_and_are_ranked_by_use():
    terms = terms_from_marks(MARKS, "strategic planning")
    assert [(t.class_number, t.description, t.uses) for t in terms] == [
        (35, "Strategic business planning", 3),
        (35, "Business strategic planning services", 1),
    ]
    assert terms_from_marks(MARKS, "strategic")[0].description == "Strategic business planning"
    assert any(t.class_number == 36 for t in terms_from_marks(MARKS, "strategic"))
    assert terms_from_marks(MARKS, "the and") == []


def test_register_lookup_sends_a_goods_and_services_search_and_caches_it():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"trademarks": [
            {"number": "1", "words": ["A"], "statusGroup": "REGISTERED",
             "goodsAndServices": [{"class": "35", "descriptionText": ["strategic business planning", "advertising"]}]},
        ]})

    client = IpAustraliaRegisterClient("id", "s", "https://auth.example/token", base_url="https://api.example/v1",
                                       transport=httpx.MockTransport(handler))
    terms = client.goods_terms("strategic planning")
    assert [(t.class_number, t.description) for t in terms] == [(35, "strategic business planning")]
    client.goods_terms("Strategic   Planning")  # same search: served from the cache
    assert len(sent) == 1
    query = sent[0]["rows"][0]["query"]
    allowed = SPEC["definitions"]["TrademarkApiAdvancedSearch"]["properties"]
    assert set(query) <= set(allowed) and query["goodsAndServices"] == "strategic planning"
    assert "REGISTERED" in allowed["statuses"]["items"]["enum"]


def test_register_lookup_failure_returns_nothing():
    client = IpAustraliaRegisterClient("id", "s", "https://auth.example/token", base_url="https://api.example/v1",
                                       transport=httpx.MockTransport(lambda r: httpx.Response(
                                           200, json={"access_token": "t"}) if r.url.path.endswith("/token")
                                           else httpx.Response(500)))
    assert client.goods_terms("anything") == []


def test_search_results_include_register_wording_labelled_with_use_count():
    app = create_app(FixtureRegisterClient(MARKS), Picklist.load(DATA / "picklist_sample.json"))
    data = TestClient(app).get("/api/picklist/find", params={"q": "strategic planning"}).json()
    c35 = next(g for g in data["groups"] if g["class_number"] == 35)
    top = c35["items"][0]
    assert top["description"] == "Strategic business planning"
    assert top["source"] == "register" and top["uses"] == 3
    services_only = TestClient(app).get("/api/picklist/find", params={"q": "strategic planning", "kinds": "goods"}).json()
    assert all(g["kind"] == "goods" for g in services_only["groups"])


def test_classes_with_every_search_word_come_before_one_word_matches():
    app = create_app(FixtureRegisterClient(MARKS), Picklist.load(DATA / "picklist_sample.json"))
    data = TestClient(app).get("/api/picklist/find", params={"q": "strategic planning"}).json()
    order = [g["class_number"] for g in data["groups"]]
    assert order.index(35) < order.index(45)  # "Wedding planning services" only shares "planning"
