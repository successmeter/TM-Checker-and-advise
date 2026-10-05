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
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

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


def test_explain_degrades_gracefully_without_llm():
    response = make_client(FakeExplainer(fail=True)).post("/api/explain", json={**BODY, "consent": True})
    assert response.status_code == 200
    data = response.json()
    assert data["explanation"] is None
    assert "not set up" in data["unavailable_reason"]
    assert data["report"]["conflicts"]  # the check itself still works
