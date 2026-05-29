from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.api.provider_webhooks import create_provider_webhook_blueprint
from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    ProviderWebhookAcceptance,
)


class FakeAdapter:
    provider_type = "whatsapp_evolution"

    def normalize_inbound(self, payload):
        return SimpleNamespace(
            provider_type="whatsapp_evolution",
            provider_subject=payload["sender"],
            text=payload.get("text", ""),
            raw_event_id=payload["message_id"],
            pairing_code=payload.get("pairing_code"),
        )

    def send_text(self, route, text, idempotency_key):
        raise AssertionError("webhook ingress must not send")


class FakeReachabilityService:
    def __init__(self) -> None:
        self.calls = []

    def accept_provider_inbound(self, inbound):
        self.calls.append(("accept_provider_inbound", inbound))
        return ProviderWebhookAcceptance(
            accepted=True,
            provider_type=inbound.provider_type,
            provider_subject=inbound.provider_subject,
            account_id="acct_1",
            channel_identity_id="ci_1",
            channel_id="channel_1",
            created_account=True,
            raw_event_id=inbound.raw_event_id,
        )


def make_client(service=None, adapters=None):
    service = service or FakeReachabilityService()
    adapters = adapters if adapters is not None else {"whatsapp_evolution": FakeAdapter()}
    app = Flask(__name__)
    app.register_blueprint(create_provider_webhook_blueprint(service, adapters))
    return app.test_client(), service


def test_provider_webhook_normalizes_and_returns_structured_identity_facts_only():
    client, service = make_client()

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={
            "message_id": "wa_msg_1",
            "sender": "whatsapp:+15555550123",
            "text": "hello",
        },
    )

    assert response.status_code == 202
    assert response.get_json() == {
        "accepted": True,
        "provider_type": "whatsapp_evolution",
        "provider_subject": "whatsapp:+15555550123",
        "account_id": "acct_1",
        "channel_identity_id": "ci_1",
        "channel_id": "channel_1",
        "created_account": True,
        "raw_event_id": "wa_msg_1",
    }
    assert service.calls[0][0] == "accept_provider_inbound"


def test_provider_webhook_rejects_unknown_provider_with_json_error():
    client, _service = make_client(adapters={})

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={"message_id": "wa_msg_1", "sender": "whatsapp:+15555550123"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "unsupported_provider"}}


def test_provider_webhook_rejects_retained_non_product_provider_before_binding():
    class WeChatECloudFakeAdapter:
        provider_type = "wechat_ecloud"

        def normalize_inbound(self, payload):
            return SimpleNamespace(
                provider_type="wechat_ecloud",
                provider_subject=payload["sender_id"],
                text=payload.get("content", ""),
                raw_event_id=payload["msg_id"],
                pairing_code=payload.get("pairing_code"),
            )

        def send_text(self, route, text, idempotency_key):
            raise AssertionError("webhook ingress must not send")

    client, service = make_client(adapters={"wechat_ecloud": WeChatECloudFakeAdapter()})

    response = client.post(
        "/webhooks/wechat/ecloud",
        json={"msg_id": "gewe_msg_1", "sender_id": "gewe_alice", "content": "hello"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "unsupported_product_channel",
            "fact": {
                "type": "unsupported_product_channel",
                "provider_type": "wechat_ecloud",
                "supported_provider_types": [
                    "wechat_personal",
                    "whatsapp_evolution",
                ],
            },
        }
    }
    assert service.calls == []


def test_provider_webhook_maps_reachability_error_to_json_error():
    class ErrorService(FakeReachabilityService):
        def accept_provider_inbound(self, inbound):
            raise ChannelReachabilityError(
                "active_channel_exists",
                fact={"type": "channel_conflict", "account_id": "acct_1"},
            )

    client, _service = make_client(service=ErrorService())

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={"message_id": "wa_msg_1", "sender": "whatsapp:+15555550123"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "active_channel_exists",
            "fact": {"type": "channel_conflict", "account_id": "acct_1"},
        }
    }
