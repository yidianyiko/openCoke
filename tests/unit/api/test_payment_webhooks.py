import hashlib
import hmac

from fastapi.testclient import TestClient

from api.app import create_app


def test_creem_checkout_completed_updates_access(monkeypatch):
    user_dao_calls = {}

    class DummyUserDao:
        def update_access_creem(self, **kwargs):
            user_dao_calls["update_access_creem"] = kwargs

    monkeypatch.setattr("api.payment_webhooks.CREEM_WEBHOOK_SECRET", "creem-secret")
    monkeypatch.setattr("api.payment_webhooks.user_dao", DummyUserDao())

    payload = (
        '{"eventType":"checkout.completed","object":{"metadata":{"user_id":"user-1"},'
        '"customer":{"id":"cust-1"},"subscription":{"id":"sub-1",'
        '"current_period_end":"2026-03-31T00:00:00Z"}}}'
    )
    signature = hmac.new(
        b"creem-secret",
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    client = TestClient(create_app())

    response = client.post(
        "/webhook/creem",
        content=payload,
        headers={
            "content-type": "application/json",
            "creem-signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert user_dao_calls["update_access_creem"]["user_id"] == "user-1"
    assert user_dao_calls["update_access_creem"]["creem_customer_id"] == "cust-1"
    assert user_dao_calls["update_access_creem"]["creem_subscription_id"] == "sub-1"


def test_stripe_checkout_completed_updates_access(monkeypatch):
    user_dao_calls = {}

    class DummyUserDao:
        def update_access_stripe(self, **kwargs):
            user_dao_calls["update_access_stripe"] = kwargs

    class DummySubscription:
        @staticmethod
        def retrieve(subscription_id):
            assert subscription_id == "sub_123"
            return {"current_period_end": 1774915200}

    class DummyWebhook:
        @staticmethod
        def construct_event(payload, sig_header, secret):
            assert payload == b'{"id":"evt_1"}'
            assert sig_header == "stripe-signature"
            assert secret == "stripe-secret"
            return {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "metadata": {"user_id": "user-2"},
                        "customer": "cus_123",
                        "subscription": "sub_123",
                    }
                },
            }

    class DummyStripe:
        Webhook = DummyWebhook
        Subscription = DummySubscription

    monkeypatch.setattr("api.payment_webhooks.STRIPE_WEBHOOK_SECRET", "stripe-secret")
    monkeypatch.setattr("api.payment_webhooks.stripe", DummyStripe())
    monkeypatch.setattr("api.payment_webhooks.user_dao", DummyUserDao())
    client = TestClient(create_app())

    response = client.post(
        "/webhook/stripe",
        content=b'{"id":"evt_1"}',
        headers={
            "content-type": "application/json",
            "stripe-signature": "stripe-signature",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert user_dao_calls["update_access_stripe"]["user_id"] == "user-2"
    assert user_dao_calls["update_access_stripe"]["stripe_customer_id"] == "cus_123"
    assert (
        user_dao_calls["update_access_stripe"]["stripe_subscription_id"] == "sub_123"
    )


def test_creem_malformed_json_returns_400_with_valid_signature(monkeypatch):
    monkeypatch.setattr("api.payment_webhooks.CREEM_WEBHOOK_SECRET", "creem-secret")
    client = TestClient(create_app())

    payload = b'{"eventType":"checkout.completed"'
    signature = hmac.new(
        b"creem-secret",
        payload,
        hashlib.sha256,
    ).hexdigest()

    response = client.post(
        "/webhook/creem",
        content=payload,
        headers={
            "content-type": "application/json",
            "creem-signature": signature,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid payload"}
