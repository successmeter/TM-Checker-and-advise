"""Stripe Checkout for the paid report (design: docs/paid-report-design.md §5.2).

The customer pays on Stripe's hosted page; card details never reach this server. Only a webhook event whose
signature checks out with the signing secret marks an order paid, never the browser coming back to the success
page. Settings (environment variables, never in code):

  STRIPE_SECRET_KEY       sk_test_... in test mode, sk_live_... when live
  STRIPE_WEBHOOK_SECRET   whsec_... for the /api/stripe/webhook endpoint
  STRIPE_PRICE_ID         optional: a Price for the report; without it the amount below is used
  TM_PUBLIC_URL           the site's address, e.g. https://trademarkadvisor.com.au (for return links)
  TM_REPORT_PRICE_CENTS   default 29900 (A$299, GST inclusive)
"""

import json
import logging
import os
from dataclasses import dataclass

import stripe

from .store import Store

log = logging.getLogger("uvicorn.error")

PRODUCT_NAME = "Trade mark filing report"


@dataclass
class Payments:
    secret_key: str
    webhook_secret: str
    public_url: str
    price_id: str | None = None
    amount: int = 29900
    currency: str = "aud"
    client: stripe.StripeClient | None = None

    @classmethod
    def from_env(cls) -> "Payments | None":
        key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
        if not key:
            return None
        return cls(secret_key=key, webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip(),
                   public_url=os.environ.get("TM_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"),
                   price_id=os.environ.get("STRIPE_PRICE_ID", "").strip() or None,
                   amount=int(os.environ.get("TM_REPORT_PRICE_CENTS", "29900")))

    @property
    def test_mode(self) -> bool:
        return self.secret_key.startswith(("sk_test_", "rk_test_"))

    def _client(self) -> stripe.StripeClient:
        if self.client is None:
            self.client = stripe.StripeClient(self.secret_key)
        return self.client

    def checkout_url(self, order_id: str, token: str, email: str, mark: str) -> tuple[str, str]:
        """A Checkout Session for the order. Returns (session id, URL to send the customer to)."""
        if self.price_id:
            line = {"price": self.price_id, "quantity": 1}
        else:
            line = {"quantity": 1, "price_data": {
                "currency": self.currency, "unit_amount": self.amount, "tax_behavior": "inclusive",
                "product_data": {"name": PRODUCT_NAME, "description": f"Report for {mark}"[:200]}}}
        session = self._client().v1.checkout.sessions.create(params={
            "mode": "payment",
            "line_items": [line],
            "customer_email": email,
            "client_reference_id": order_id,
            "metadata": {"order_id": order_id},
            "payment_intent_data": {"metadata": {"order_id": order_id}},
            "invoice_creation": {"enabled": True},
            "success_url": f"{self.public_url}/report/{order_id}?t={token}",
            "cancel_url": f"{self.public_url}/?cancelled={order_id}",
        })
        return session["id"], session["url"]

    def handle_webhook(self, payload: bytes, signature: str | None, store: Store) -> str | None:
        """Verify and apply a webhook event. Returns the order id if the order has just been paid.

        Raises ValueError for a bad payload and stripe.SignatureVerificationError for a bad signature.
        """
        if not self.webhook_secret:
            raise stripe.SignatureVerificationError("No webhook signing secret is set.", signature)
        stripe.Webhook.construct_event(payload, signature, self.webhook_secret)  # raises unless signed by Stripe
        event = json.loads(payload)  # verified: read it as plain JSON (independent of the library's object types)
        kind, obj = event.get("type"), (event.get("data") or {}).get("object") or {}
        if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            if obj.get("payment_status") != "paid":
                return None  # a delayed payment method: wait for async_payment_succeeded
            order_id = (obj.get("metadata") or {}).get("order_id") or obj.get("client_reference_id")
            if not order_id or store.get(order_id) is None:
                log.warning("Stripe session %s has no matching order", obj.get("id"))
                return None
            if store.mark_paid(order_id, obj.get("payment_intent")):
                log.info("Order %s paid", order_id)
                return order_id
            return None  # already handled: Stripe can send an event more than once
        if kind == "charge.refunded" and obj.get("payment_intent"):
            order_id = store.mark_refunded_by_payment(obj["payment_intent"])
            if order_id:
                log.info("Order %s refunded", order_id)
        return None
