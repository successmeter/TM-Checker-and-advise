import json
from pathlib import Path

import anthropic
import httpx2
import pytest

from tm_advisor.analysis import check
from tm_advisor.explain import Explainer, ExplanationUnavailable, retrieve
from tm_advisor.manual import ManualIndex, chunk_page, parse_page
from tm_advisor.models import Application
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "manual"
BASE = "https://manuals.ipaustralia.gov.au/trademark"


@pytest.fixture(scope="module")
def index():
    idx = ManualIndex()
    idx.build(
        chunk_page(parse_page(f"{BASE}/3.-similar-goods", (FIXTURES / "s44-goods.html").read_text()))
        + chunk_page(parse_page(f"{BASE}/1.-section-41", (FIXTURES / "s41-intro.html").read_text()))
    )
    return idx


@pytest.fixture(scope="module")
def report():
    application = Application(mark="Best EcoKnit", classes=[{"class_number": 25, "terms": ["Clothing", "Sweaters"]}])
    return check(application, FixtureRegisterClient.load(ROOT / "data" / "register_fixture.json"),
                 Picklist.load(ROOT / "data" / "picklist_sample.json"))


def sdk_client(handler):
    return anthropic.Anthropic(api_key="test-key", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def message(payload, stop_reason="end_turn"):
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_retrieve_finds_s44_and_s41_passages(report, index):
    excerpts = retrieve(report, index)
    headings = [c.heading for c in excerpts]
    assert "3.1 Goods of the same description" in headings
    assert any(c.url.endswith("1.-section-41") for c in excerpts)
    assert len({c.id for c in excerpts}) == len(excerpts)


def test_explain_sends_findings_and_excerpts_and_keeps_only_real_citations(report, index):
    excerpts = retrieve(report, index)
    good_id = excerpts[0].id
    sent = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent["body"] = json.loads(request.content)
        sent["beta"] = request.headers.get("anthropic-beta", "")
        return httpx2.Response(200, json=message({
            "overview": "High risk because of ECO KNITWEAR.",
            "conflicts": [
                {"cited_number": "2198432", "explanation": "Same clothing goods.", "excerpt_ids": [good_id, "made-up#9"]},
                {"cited_number": "9999999", "explanation": "Invented conflict.", "excerpt_ids": []},
            ],
            "distinctiveness": {"explanation": "BEST praises the goods.", "excerpt_ids": []},
            "next_steps": ["Speak to an attorney."],
        }))

    explanation = Explainer(client=sdk_client(handler)).explain(report, excerpts)

    body = sent["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in sent["beta"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["effort"] == "medium"
    assert "thinking" not in body and "temperature" not in body
    user_text = body["messages"][0]["content"]
    assert "ECO KNITWEAR" in user_text
    assert f'<excerpt id="{good_id}"' in user_text
    assert "Do not change, soften or upgrade any risk level" in body["system"]

    assert [c.cited_number for c in explanation.conflicts] == ["2198432"]  # invented conflict dropped
    assert [c.id for c in explanation.conflicts[0].citations] == [good_id]  # made-up citation dropped
    assert explanation.conflicts[0].citations[0].url.startswith(BASE)
    assert explanation.distinctiveness.explanation.startswith("BEST")


def test_refusal_is_reported_not_parsed(report, index):
    client = sdk_client(lambda r: httpx2.Response(200, json=message({}, stop_reason="refusal")))
    with pytest.raises(ExplanationUnavailable, match="could not be generated"):
        Explainer(client=client).explain(report, [])


def test_bad_key_gives_friendly_message(report):
    client = sdk_client(lambda r: httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad"}}))
    with pytest.raises(ExplanationUnavailable, match="API key"):
        Explainer(client=client).explain(report, [])


def test_missing_credentials_gives_friendly_message(report, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")
    client = anthropic.Anthropic(max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(500))))
    with pytest.raises(ExplanationUnavailable, match="not set up"):
        Explainer(client=client).explain(report, [])


def test_api_key_with_stray_spaces_or_quotes_is_cleaned(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", '  "sk-ant-test-key" ')
    assert Explainer().client.api_key == "sk-ant-test-key"


def test_keywords_asks_claude_for_picklist_search_words():
    sent = {}

    def handler(request):
        sent["body"] = json.loads(request.content)
        return httpx2.Response(200, json=message({"keywords": ["cafe", "coffee", "cafe", " takeaway food "]}))

    words = Explainer(client=sdk_client(handler)).keywords("We run a cafe")
    assert words == ["cafe", "coffee", "takeaway food"]
    assert sent["body"]["output_config"]["effort"] == "low"
    assert sent["body"]["messages"][0]["content"] == "We run a cafe"
