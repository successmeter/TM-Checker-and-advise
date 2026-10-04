from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tm_advisor.api import create_app
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def client():
    app = create_app(FixtureRegisterClient.load(DATA / "register_fixture.json"), Picklist.load(DATA / "picklist_sample.json"))
    return TestClient(app)


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
