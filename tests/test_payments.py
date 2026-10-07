import hashlib
import hmac
import json
import time

import pytest
import stripe

from tm_advisor.payments import Payments
from tm_advisor.store import Store

SECRET = "whsec_test"
APP = {"mark": "Success Meter", "mark_kind": "word", "classes": [{"class_number": 35, "terms": ["advertising"]}]}


def signed(event: dict, secret: str = SECRET) -> tuple[bytes, str]:
    payload = json.dumps(event).encode()
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, f"t={t},v1={sig}"


def event(kind: str, obj: dict) -> dict:
    return {"id": "evt_1", "object": "event", "type": kind, "data": {"object": obj}}


class FakeSessions:
    def __init__(self):
        self.params = None

    def create(self, params=None, options=None):
        self.params = params
        return {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}


class FakeClient:
    def __init__(self):
        self.sessions = FakeSessions()
        self.v1 = type("V1", (), {"checkout": type("C", (), {"sessions": self.sessions})()})()


def payments(**kw):
    return Payments(secret_key="sk_test_x", webhook_secret=SECRET, public_url="https://example.com",
                    client=FakeClient(), **kw)


def test_checkout_session_is_for_the_order():
    p = payments()
    session_id, url = p.checkout_url("TA-ABC", "tok", "me@example.com", "Success Meter")
    params = p.client.sessions.params
    assert session_id == "cs_test_1" and url.startswith("https://checkout.stripe.com")
    assert params["mode"] == "payment" and params["customer_email"] == "me@example.com"
    assert params["metadata"]["order_id"] == "TA-ABC" and params["client_reference_id"] == "TA-ABC"
    line = params["line_items"][0]["price_data"]
    assert line["unit_amount"] == 29900 and line["currency"] == "aud" and line["tax_behavior"] == "inclusive"
    assert params["success_url"] == "https://example.com/report/TA-ABC?t=tok"
    assert p.test_mode

    p = payments(price_id="price_123")
    p.checkout_url("TA-ABC", "tok", "me@example.com", "X")
    assert p.client.sessions.params["line_items"] == [{"price": "price_123", "quantity": 1}]


def test_verified_webhook_marks_paid_once_and_refunds():
    store = Store()
    order, _ = store.create_order("me@example.com", APP, 29900, "aud")
    p = payments()
    paid = event("checkout.session.completed", {"id": "cs_1", "object": "checkout.session", "payment_status": "paid",
                                                "metadata": {"order_id": order.id}, "payment_intent": "pi_1"})
    assert p.handle_webhook(*signed(paid), store) == order.id
    assert store.get(order.id).status == "paid"
    assert p.handle_webhook(*signed(paid), store) is None  # Stripe sent it again: no second report

    store.claim(order.id)
    store.save_report(order.id, {}, None)
    refund = event("charge.refunded", {"id": "ch_1", "object": "charge", "payment_intent": "pi_1"})
    p.handle_webhook(*signed(refund), store)
    assert store.get(order.id).status == "refunded"


def test_unpaid_or_unknown_sessions_are_ignored():
    store = Store()
    order, _ = store.create_order("me@example.com", APP, 29900, "aud")
    p = payments()
    pending = event("checkout.session.completed", {"payment_status": "unpaid", "metadata": {"order_id": order.id}})
    assert p.handle_webhook(*signed(pending), store) is None and store.get(order.id).status == "pending"
    unknown = event("checkout.session.completed", {"payment_status": "paid", "metadata": {"order_id": "TA-NOPE"}})
    assert p.handle_webhook(*signed(unknown), store) is None


def test_bad_signatures_are_rejected():
    store = Store()
    p = payments()
    payload, header = signed(event("checkout.session.completed", {}), secret="whsec_other")
    with pytest.raises(stripe.SignatureVerificationError):
        p.handle_webhook(payload, header, store)
    with pytest.raises(stripe.SignatureVerificationError):
        p.handle_webhook(payload, None, store)
    with pytest.raises(stripe.SignatureVerificationError):
        Payments(secret_key="sk_test_x", webhook_secret="", public_url="x").handle_webhook(payload, header, store)
