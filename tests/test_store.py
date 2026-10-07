from tm_advisor.store import Store

APP = {"mark": "Success Meter", "mark_kind": "word", "classes": [{"class_number": 35, "terms": ["advertising"]}]}


def test_order_lifecycle_and_tokens(tmp_path):
    store = Store(tmp_path / "orders.sqlite")
    order, token = store.create_order(" Me@Example.com ", APP, 29900, "aud", industry="cafes", logo=b"png", logo_type="image/png")
    assert order.id.startswith("TA-") and order.status == "pending" and order.email == "me@example.com"
    assert store.check_token(order.id, token) and not store.check_token(order.id, "wrong") and not store.check_token(order.id, "")

    store.set_session(order.id, "cs_1")
    assert store.by_session("cs_1").id == order.id
    assert store.mark_paid(order.id, "pi_1") and not store.mark_paid(order.id, "pi_1")  # repeated webhook: no-op
    assert store.unfinished() == [order.id]
    assert store.claim(order.id) and not store.claim(order.id)  # one worker only

    store.save_report(order.id, {"mark": "Success Meter"}, "/x.pdf")
    assert store.get(order.id).status == "ready" and store.report(order.id) == ({"mark": "Success Meter"}, "/x.pdf")
    assert store.unfinished() == []

    assert store.token_for(order.id) == token  # the same link can be sent again
    assert not Store(tmp_path / "orders.sqlite", secret=b"other").check_token(order.id, token)
    assert [o.id for o in store.orders_for_email("ME@example.com")] == [order.id]

    assert store.mark_refunded_by_payment("pi_1") == order.id and store.get(order.id).status == "refunded"
    assert store.mark_refunded_by_payment("pi_unknown") is None
    assert Store(tmp_path / "orders.sqlite").get(order.id).logo == b"png"  # persisted


def test_failures_retry_and_review_hold():
    store = Store()
    order, _ = store.create_order("a@b.co", APP, 29900, "aud")
    assert not store.claim(order.id)  # unpaid orders are never generated
    store.mark_paid(order.id, None)
    store.claim(order.id)
    store.mark_failed(order.id, "boom")
    assert store.get(order.id).status == "failed" and store.unfinished() == [order.id]
    assert store.claim(order.id) and store.get(order.id).attempts == 2
    store.save_report(order.id, {}, None, hold_for_review=True)
    assert store.get(order.id).status == "review" and store.approve(order.id) and store.get(order.id).status == "ready"
    assert store.orders_for_email("a@b.co")[0].status == "ready"
