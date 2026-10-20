import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tm_advisor.api import create_app
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient, IpAustraliaRegisterClient
from tm_advisor.register.terms import split_terms
from tm_advisor.register.wording import WordingIndex, collect, harvest, save
from tests.test_register_terms import DATA, SPEC


def rec(number, cls, *texts, group="REGISTERED"):
    return {"number": number, "statusGroup": group,
            "goodsAndServices": [{"class": str(cls), "descriptionText": list(texts)},
                                 {"class": "41", "descriptionText": ["Education services"]}]}


def test_split_terms_on_semicolons():
    assert split_terms(["Clothing; footwear;headgear.", "x", "Advertising, marketing"]) == [
        "Clothing", "footwear", "headgear", "Advertising, marketing"]


def test_collect_counts_wording_within_the_class_searched():
    pages = {35: [[rec("1", 35, "Strategic business planning; Advertising"), rec("2", 35, "strategic business planning"),
                   rec("2", 35, "strategic business planning"), rec("3", 35, "Advertising", group="REMOVED"),
                   rec("4", 35, "One-off wording")]]}
    terms, marks = collect(lambda c: pages.get(c, []), classes=[35, 41], log=lambda _: None)
    assert terms == [{"class_number": 35, "description": "Strategic business planning", "uses": 2}]
    assert marks == 3  # duplicates and non-registered marks skipped; class 41 terms only count when searching class 41


def test_index_search_needs_every_word_and_spreads_over_classes():
    index = WordingIndex([
        {"class_number": 35, "description": "Strategic business planning", "uses": 40},
        {"class_number": 36, "description": "Strategic financial planning", "uses": 12},
        {"class_number": 41, "description": "Event planning", "uses": 99},
        {"class_number": 42, "description": "Strategic planning of IT systems", "uses": 3},
    ])
    found = index.search("strategic planning")
    assert [(t.class_number, t.uses) for t in found] == [(35, 40), (36, 12), (42, 3)]
    assert index.search("the and") == []


def test_harvest_pages_each_class_with_a_spec_valid_query(tmp_path):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        body = json.loads(request.content)
        sent.append(body)
        cls = int(body["rows"][0]["query"]["classNumber"]["text"])
        page = body["pageNumber"]
        rows = [rec(f"{cls}-{page}-{i}", cls, f"Wording {cls}", f"Rare {cls}-{page}-{i}") for i in range(2 if page == 0 else 1)]
        return httpx.Response(200, json={"trademarks": rows})

    client = IpAustraliaRegisterClient("id", "s", "https://auth.example/token", base_url="https://api.example/v1",
                                       transport=httpx.MockTransport(handler))
    out = tmp_path / "w.json"
    change = harvest(client, out, pages=3, page_size=2, delay=0, log=lambda _: None)
    assert change.after == 45 + 1 and change.marks == 45 * 3  # plus "Education services" in class 41
    assert len(sent) == 45 * 2  # second page was short, so the class stopped there
    query = sent[0]["rows"][0]["query"]
    props = SPEC["definitions"]["TrademarkApiAdvancedSearch"]["properties"]
    assert set(query) <= set(props)
    assert query["classNumber"]["type"] in SPEC["definitions"]["TrademarkApiClass"]["properties"]["type"]["enum"]
    assert sent[0]["sort"]["field"] in SPEC["definitions"]["ApiQuickSearchSort"]["properties"]["field"]["enum"]
    assert WordingIndex.load(out).search("wording 25")[0].uses == 3


def test_much_smaller_list_is_refused(tmp_path):
    out = tmp_path / "w.json"
    save([{"class_number": 1, "description": f"T{i}", "uses": 2} for i in range(10)], 5, out)
    with pytest.raises(SystemExit, match="far fewer"):
        save([{"class_number": 1, "description": "T", "uses": 2}], 5, out)
    assert len(json.loads(out.read_text())["terms"]) == 10


def test_search_uses_saved_wording_for_every_class():
    wording = WordingIndex([{"class_number": c, "description": f"Strategic planning services class {c}", "uses": c}
                            for c in (35, 36, 41, 42, 44, 45, 9, 16)], "2026-10-01", 9000)
    app = create_app(FixtureRegisterClient([]), Picklist.load(DATA / "picklist_sample.json"), wording=wording)
    data = TestClient(app).get("/api/picklist/find", params={"q": "strategic planning"}).json()
    assert {35, 36, 41, 42, 44, 45, 9, 16} <= {g["class_number"] for g in data["groups"]}
    status = TestClient(app).get("/api/data-status").json()
    assert status["wording"] == {"updated": "2026-10-01", "terms": 8, "marks": 9000}
