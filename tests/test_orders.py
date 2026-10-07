import base64
import time

from fastapi.testclient import TestClient

from tests.test_payments import FakeClient, SECRET, event, signed
from tm_advisor.api import create_app
from tm_advisor.payments import Payments
from tm_advisor.picklist import Picklist
from tm_advisor.register import FixtureRegisterClient
from tm_advisor.store import Store
from tests.test_report_build import DATA, mark

REGISTER = FixtureRegisterClient([mark("711535", "SUCCESSMAKER", 35, ["business consultancy"], owner="Savvas")])

APP = {"mark": "Success Meter", "mark_kind": "word", "applicant": "Example Pty Ltd",
       "classes": [{"class_number": 35, "terms": ["business consultancy"]}]}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


class FakeMailer:
    def __init__(self):
        self.sent = []

    def report_ready(self, to, mark, links):
        self.sent.append((to, links))
        return True


def fake_pdf(doc, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"%PDF-1.4 " + doc.mark.encode())
    return out


def setup(full=False, review=False, payments=True):
    store, mailer = Store(), FakeMailer()
    pay = Payments(secret_key="sk_test_x", webhook_secret=SECRET, public_url="https://example.com",
                   client=FakeClient()) if payments else None
    app = create_app(REGISTER, Picklist.load(DATA / "picklist_sample.json"), store=store, payments=pay, mailer=mailer,
                     pdf=fake_pdf, review=review, ai_checks=False, full_check_results=full)
    return TestClient(app), store, mailer, pay


def wait_for(store, order_id, status, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if store.get(order_id).status == status:
            return True
        time.sleep(0.05)
    return False


def test_free_check_shows_only_risk_and_where_the_concerns_are():
    client, *_ = setup()
    data = client.post("/api/check", json={**APP, "consent": True}).json()
    assert set(data) >= {"overall_risk", "concerns", "report_covers", "price_cents"}
    assert "conflicts" not in data and "route" not in data and "distinctiveness" not in data
    assert data["price_cents"] == 29900 and data["payments_enabled"]
    assert data["concerns"]["similar_marks"] >= 1
    assert client.post("/api/explain", json={**APP, "consent": True}).status_code == 404  # part of the paid report


def test_paid_order_produces_a_private_report():
    client, store, mailer, pay = setup()
    logo = "data:image/png;base64," + base64.b64encode(PNG).decode()
    r = client.post("/api/orders", json={"email": "me@example.com", "terms": True, "application": APP, "logo": logo,
                                         "industry": "for small businesses"})
    assert r.status_code == 200
    order_id, url = r.json()["order_id"], r.json()["url"]
    assert url.startswith("https://checkout.stripe.com") and store.get(order_id).logo == PNG
    token = store.token_for(order_id)

    page = client.get(f"/report/{order_id}?t={token}")
    assert "Confirming your payment" in page.text  # the success redirect alone never marks it paid

    payload, header = signed(event("checkout.session.completed", {
        "id": "cs_test_1", "payment_status": "paid", "metadata": {"order_id": order_id}, "payment_intent": "pi_1"}))
    assert client.post("/api/stripe/webhook", content=payload, headers={"stripe-signature": header}).status_code == 200
    assert wait_for(store, order_id, "ready")

    page = client.get(f"/report/{order_id}?t={token}")
    assert "Trade mark filing report" in page.text and "Download PDF" in page.text and "data:image/png;base64" in page.text
    pdf = client.get(f"/report/{order_id}/pdf?t={token}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/report/{order_id}?t=wrong").status_code == 404
    assert client.get(f"/report/{order_id}/pdf").status_code == 404
    assert mailer.sent[0][0] == "me@example.com" and token in mailer.sent[0][1][0][1]

    # Lost link: same answer whether or not the address has reports.
    assert client.post("/api/orders/links", json={"email": "ME@example.com"}).status_code == 200
    assert len(mailer.sent) == 2
    client.post("/api/orders/links", json={"email": "nobody@example.com"})
    assert len(mailer.sent) == 2


def test_bad_webhooks_and_orders_are_rejected():
    client, store, *_ = setup()
    payload, header = signed(event("checkout.session.completed", {}), secret="whsec_wrong")
    assert client.post("/api/stripe/webhook", content=payload, headers={"stripe-signature": header}).status_code == 400
    base = {"email": "me@example.com", "terms": True, "application": APP}
    assert client.post("/api/orders", json={**base, "terms": False}).status_code == 422
    assert client.post("/api/orders", json={**base, "email": "not-an-email"}).status_code == 422
    exe = "data:application/octet-stream;base64," + base64.b64encode(b"MZ\x90\x00").decode()
    assert client.post("/api/orders", json={**base, "logo": exe}).status_code == 422
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg><script>alert(1)</script></svg>").decode()
    assert client.post("/api/orders", json={**base, "logo": svg}).status_code == 422


def test_review_hold_and_no_payments_configured():
    client, store, mailer, _ = setup(review=True)
    order_id = client.post("/api/orders", json={"email": "a@b.co", "terms": True, "application": APP}).json()["order_id"]
    payload, header = signed(event("checkout.session.completed", {
        "payment_status": "paid", "metadata": {"order_id": order_id}, "payment_intent": "pi_2"}))
    client.post("/api/stripe/webhook", content=payload, headers={"stripe-signature": header})
    assert wait_for(store, order_id, "review") and not mailer.sent
    assert "being checked" in client.get(f"/report/{order_id}?t={store.token_for(order_id)}").text

    client, *_ = setup(payments=False)
    assert client.post("/api/orders", json={"email": "a@b.co", "terms": True, "application": APP}).status_code == 503
    assert client.post("/api/check", json={**APP, "consent": True}).json()["payments_enabled"] is False


def test_sample_report_page():
    client, *_ = setup()
    assert "Sample report" in client.get("/report/sample").text
