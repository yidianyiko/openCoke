from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.api.internal_routes import create_internal_blueprint
from coke.app import create_app
from coke.config import Settings

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeDeliveryCallbackService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def record_delivery_callback(
        self,
        *,
        provider_type,
        provider_idempotency_key,
        status,
        provider_message_id=None,
        error_code=None,
        delivered_at=None,
    ):
        self.calls.append(
            (
                "record_delivery_callback",
                {
                    "provider_type": provider_type,
                    "provider_idempotency_key": provider_idempotency_key,
                    "status": status,
                    "provider_message_id": provider_message_id,
                    "error_code": error_code,
                    "delivered_at": delivered_at,
                },
            )
        )
        return SimpleNamespace(
            attempt_id="attempt_1",
            provider_type=provider_type,
            provider_idempotency_key=provider_idempotency_key,
            status=status,
            idempotent=True,
        )


class FakeSubscription:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


UNSET = object()


class FakeReplyPubSub:
    def __init__(self, reply=UNSET) -> None:
        self.reply = {
            "event_id": "outbox_1",
            "turn_id": "turn_1",
            "disposition": "replied",
            "reason_code": None,
            "visible_text": "hello",
        } if reply is UNSET else reply
        self.subscription = FakeSubscription()
        self.calls: list[tuple[str, dict]] = []

    def subscribe(self, causal_inbound_event_id):
        self.calls.append(
            ("subscribe", {"causal_inbound_event_id": causal_inbound_event_id})
        )
        return self.subscription

    def get_reply(self, subscription, timeout_s=30.0):
        self.calls.append(
            ("get_reply", {"subscription": subscription, "timeout_s": timeout_s})
        )
        return self.reply


def test_delivery_callback_route_requires_internal_auth_and_records_lifecycle():
    delivery = FakeDeliveryCallbackService()
    client = make_client(delivery_callback_service=delivery)

    response = client.post(
        "/internal/outbound/delivery-callback",
        json={
            "provider_type": "whatsapp_evolution",
            "provider_idempotency_key": "idem_1",
            "status": "delivered",
            "provider_message_id": "wamid_1",
            "delivered_at": "2026-05-31T12:00:00+00:00",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "attempt_id": "attempt_1",
        "provider_type": "whatsapp_evolution",
        "provider_idempotency_key": "idem_1",
        "status": "delivered",
        "idempotent": True,
    }
    assert delivery.calls == [
        (
            "record_delivery_callback",
            {
                "provider_type": "whatsapp_evolution",
                "provider_idempotency_key": "idem_1",
                "status": "delivered",
                "provider_message_id": "wamid_1",
                "error_code": None,
                "delivered_at": "2026-05-31T12:00:00+00:00",
            },
        )
    ]


def test_reply_wait_route_subscribes_by_causal_inbound_event_id_and_closes():
    pubsub = FakeReplyPubSub()
    client = make_client(reply_pubsub=pubsub)

    response = client.get("/internal/reply-wait/inbound-1?timeout_s=0.25")

    assert response.status_code == 200
    assert response.get_json() == {
        "event_id": "outbox_1",
        "turn_id": "turn_1",
        "disposition": "replied",
        "reason_code": None,
        "visible_text": "hello",
    }
    assert pubsub.calls == [
        ("subscribe", {"causal_inbound_event_id": "inbound-1"}),
        (
            "get_reply",
            {"subscription": pubsub.subscription, "timeout_s": 0.25},
        ),
    ]
    assert pubsub.subscription.closed is True


def test_reply_wait_route_returns_no_content_when_no_reply_arrives():
    pubsub = FakeReplyPubSub(reply=None)
    client = make_client(reply_pubsub=pubsub)

    response = client.get("/internal/reply-wait/inbound-1?timeout_s=0.25")

    assert response.status_code == 204
    assert response.data == b""


def test_internal_routes_reject_missing_or_wrong_key_before_service_call():
    delivery = FakeDeliveryCallbackService()
    app = Flask(__name__)
    app.register_blueprint(
        create_internal_blueprint(
            delivery_callback_service=delivery,
            reply_pubsub=FakeReplyPubSub(),
            internal_api_key="internal-key",
        )
    )

    missing = app.test_client().post("/internal/outbound/delivery-callback", json={})
    wrong = app.test_client().get(
        "/internal/reply-wait/inbound-1",
        headers={"Authorization": "Bearer wrong"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert delivery.calls == []


def test_create_app_registers_internal_blueprint_additively():
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        delivery_callback_service=FakeDeliveryCallbackService(),
        reply_pubsub=FakeReplyPubSub(),
        internal_api_key="internal-key",
    )

    response = app.test_client().get(
        "/internal/reply-wait/inbound-1",
        headers={"Authorization": "Bearer internal-key"},
    )

    assert response.status_code == 200


def make_client(delivery_callback_service=None, reply_pubsub=None):
    app = Flask(__name__)
    app.register_blueprint(
        create_internal_blueprint(
            delivery_callback_service=delivery_callback_service
            or FakeDeliveryCallbackService(),
            reply_pubsub=reply_pubsub or FakeReplyPubSub(),
            internal_api_key="internal-key",
        )
    )
    return AuthenticatedClient(app.test_client())


class AuthenticatedClient:
    def __init__(self, raw_client) -> None:
        self.raw = raw_client

    def get(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer internal-key"})
        return self.raw.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer internal-key"})
        return self.raw.post(*args, **kwargs)
