from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tm_advisor.api import create_app
from tm_advisor.explain import Explanation, ExplanationUnavailable
from tm_advisor.manual import ManualIndex, chunk_page, parse_page
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient

DATA = Path(__file__).resolve().parents[1] / "data"


class FakeExplainer:
    def __init__(self, fail=False, keywords=None):
        self.fail = fail
        self.calls = []
        self._keywords = keywords or ["coffee", "cafe"]

    def keywords(self, text):
        if self.fail:
            raise ExplanationUnavailable("Explanations are not set up: no Anthropic API key found.")
        return self._keywords

    def explain(self, report, excerpts):
        self.calls.append((report, excerpts))
        if self.fail:
            raise ExplanationUnavailable("Explanations are not set up: no Anthropic API key found.")
        return Explanation(overview=f"{report.mark} is {report.overall_risk.value} risk.", conflicts=[],
                           distinctiveness=None, next_steps=[], model="fake")


def make_client(explainer=None):
    manual = ManualIndex()
    page = (Path(__file__).parent / "fixtures" / "manual" / "s44-goods.html").read_text()
    manual.build(chunk_page(parse_page("https://manuals.ipaustralia.gov.au/trademark/3.-similar", page)))
    app = create_app(FixtureRegisterClient.load(DATA / "register_fixture.json"), Picklist.load(DATA / "picklist_sample.json"),
                     manual=manual, explainer=explainer or FakeExplainer())
    return TestClient(app)


@pytest.fixture(scope="module")
def client():
    return make_client()


BODY = {"mark": "EcoKnit", "classes": [{"class_number": 25, "terms": ["Clothing", "Sweaters"]}]}


def test_check_requires_consent(client):
    response = client.post("/api/check", json=BODY)
    assert response.status_code == 422
    assert "not legal advice" in response.json()["detail"]


def test_check_returns_report(client):
    response = client.post("/api/check", json={**BODY, "consent": True})
    assert response.status_code == 200
    report = response.json()
    assert report["overall_risk"] == "High"
    assert report["conflicts"][0]["cited_number"] == "2198432"
    assert report["disclaimers"]


def test_check_validates_classes(client):
    response = client.post("/api/check", json={"mark": "X", "classes": [{"class_number": 99, "terms": ["a"]}], "consent": True})
    assert response.status_code == 422


def test_picklist_search(client):
    response = client.get("/api/picklist/search", params={"q": "sweater"})
    assert response.status_code == 200
    assert {"class_number": 25, "description": "Sweaters"} in response.json()


def test_index_page_has_consent_box(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="consent"' in response.text


def test_explain_requires_consent(client):
    assert client.post("/api/explain", json=BODY).status_code == 422


def test_explain_returns_report_and_grounded_explanation():
    explainer = FakeExplainer()
    response = make_client(explainer).post("/api/explain", json={**BODY, "consent": True})
    assert response.status_code == 200
    data = response.json()
    assert data["report"]["overall_risk"] == "High"
    assert data["explanation"]["overview"] == "EcoKnit is High risk."
    assert data["manual_excerpts_used"] > 0
    assert explainer.calls[0][1]  # Manual excerpts were passed to the explainer


def test_explain_degrades_gracefully_without_llm(caplog):
    response = make_client(FakeExplainer(fail=True)).post("/api/explain", json={**BODY, "consent": True})
    assert "Explanation failed" in caplog.text  # the real cause is shown in the server window
    assert response.status_code == 200
    data = response.json()
    assert data["explanation"] is None
    assert "not set up" in data["unavailable_reason"]
    assert data["report"]["conflicts"]  # the check itself still works


def test_classes_endpoint(client):
    classes = client.get("/api/classes").json()
    assert len(classes) == 45
    assert classes[24] == {"class_number": 25, "title": "Clothing, footwear and headwear", "kind": "goods",
                           "heading": "", "notes": []}  # heading and notes come with the full picklist


def test_find_groups_results_by_class(client):
    data = client.get("/api/picklist/find", params={"q": "sweaters"}).json()
    assert data["groups"][0]["class_number"] == 25
    assert data["groups"][0]["title"] == "Clothing, footwear and headwear"
    assert {"description": "Sweaters"} .items() <= data["groups"][0]["items"][0].items()
    assert data["sample_picklist"] is True


def test_find_can_limit_to_services(client):
    data = client.get("/api/picklist/find", params={"q": "coffee", "kinds": "services"}).json()
    assert data["groups"] and all(g["kind"] == "services" for g in data["groups"])


def test_describe_uses_smart_keywords():
    data = make_client().post("/api/picklist/describe", json={"text": "I run a little cafe in Fitzroy"}).json()
    assert data["keywords"] == ["coffee", "cafe"]
    assert {g["class_number"] for g in data["groups"]} >= {30, 43}
    assert data["note"] is None


def test_describe_falls_back_to_plain_words():
    data = make_client(FakeExplainer(fail=True)).post(
        "/api/picklist/describe", json={"text": "We sell handmade candles and soaps"}).json()
    assert data["keywords"] == ["handmade", "candles", "soaps"]
    assert {g["class_number"] for g in data["groups"]} >= {3, 4}
    assert "main words" in data["note"]


def test_composite_kind_softens_descriptive_mark_and_is_recommended(client):
    body = {"mark": "Best Coffee", "consent": True, "classes": [{"class_number": 30, "terms": ["Coffee"]}]}
    word = client.post("/api/check", json=body).json()
    composite = client.post("/api/check", json={**body, "mark_kind": "composite"}).json()
    assert word["overall_risk"] == "High" and word["escalate"]
    assert word["route"]["recommended"] == "composite"
    assert any("new representation" in r for r in word["route"]["reasons"])
    assert composite["overall_risk"] == "Medium" and not composite["escalate"]
    assert composite["mark_kind"] == "composite" and composite["route"]["recommended"] == "composite"
    assert any("protects the combination as a whole" in n for n in composite["notes"])


def test_logo_only_skips_the_word_search(client):
    body = {"mark": "a stylised green leaf inside a circle", "mark_kind": "logo", "consent": True,
            "classes": [{"class_number": 30, "terms": ["Coffee"]}]}
    report = client.post("/api/check", json=body).json()
    assert report["conflicts"] == [] and report["distinctiveness"] == []
    assert report["route"]["recommended"] == "logo"
    assert any("image search" in n for n in report["notes"])


def test_data_status_reports_sample_and_manual(client):
    data = client.get("/api/data-status").json()
    assert data["picklist"]["sample"] is True and data["picklist"]["terms"] > 400
    assert data["manual"]["pages"] == 1 and data["manual"]["passages"] > 0


def test_picklist_file_is_reloaded_after_a_refresh(tmp_path, monkeypatch):
    import json
    import os
    import time
    path = tmp_path / "picklist.json"
    path.write_text(json.dumps({"updated": "2026-10-01", "items": [{"id": "1", "class_number": 25, "description": "Hats"}]}))
    monkeypatch.setenv("TM_PICKLIST", str(path))
    app = TestClient(create_app(FixtureRegisterClient.load(DATA / "register_fixture.json"), explainer=FakeExplainer()))

    status = app.get("/api/data-status").json()["picklist"]
    assert status == {"sample": False, "updated": "2026-10-01", "terms": 1}
    assert app.get("/api/picklist/find", params={"q": "beanies"}).json()["groups"] == []

    path.write_text(json.dumps({"updated": "2026-10-08", "items": [
        {"id": "1", "class_number": 25, "description": "Hats"}, {"id": "2", "class_number": 25, "description": "Beanies"}]}))
    later = time.time() + 5
    os.utime(path, (later, later))
    assert app.get("/api/data-status").json()["picklist"]["updated"] == "2026-10-08"
    assert app.get("/api/picklist/find", params={"q": "beanies"}).json()["groups"][0]["items"][0]["description"] == "Beanies"
