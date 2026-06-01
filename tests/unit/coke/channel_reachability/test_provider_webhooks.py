from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from flask import Flask

from coke.api.provider_webhooks import create_provider_webhook_blueprint
from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    NormalizedInbound,
    ProviderWebhookAcceptance,
)
from coke.providers.wechat_personal import WeChatPersonalAdapter


class FakeAdapter:
    provider_type = "whatsapp_evolution"

    def __init__(self) -> None:
        self.calls = []

    def normalize_inbound(self, payload):
        self.calls.append(payload)
        return NormalizedInbound(
            provider_type="whatsapp_evolution",
            provider_subject=payload["data"]["key"]["remoteJid"].removesuffix(
                "@s.whatsapp.net"
            ),
            text=payload["data"]["message"].get("conversation", ""),
            raw_event_id=payload["data"]["key"]["id"],
            received_at=datetime.fromtimestamp(
                payload["data"]["messageTimestamp"], UTC
            ),
            pairing_code=payload.get("pairing_code"),
            payload=payload,
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


class FakeConversationRuntimeService:
    def __init__(self) -> None:
        self.calls = []
        self.enqueued = []

    def record_inbound(
        self,
        *,
        account_id,
        channel_identity_id,
        causal_inbound_event_id,
        text,
        payload,
        traceparent,
        media=None,
    ):
        self.calls.append(
            {
                "account_id": account_id,
                "channel_identity_id": channel_identity_id,
                "causal_inbound_event_id": causal_inbound_event_id,
                "text": text,
                "payload": payload,
                "traceparent": traceparent,
                "media": tuple(media or ()),
            }
        )
        return SimpleNamespace(
            conversation=SimpleNamespace(id="conversation_1"),
            message=SimpleNamespace(id="message_1", seq=1),
        )

    def enqueue_render_turn(
        self,
        *,
        topic,
        idempotency_key,
        payload,
        traceparent,
    ):
        self.enqueued.append(
            {
                "topic": topic,
                "idempotency_key": idempotency_key,
                "payload": payload,
                "traceparent": traceparent,
            }
        )


class FakeReminderService:
    def __init__(self, fire_ids=None) -> None:
        self.fire_ids = list(fire_ids or [])
        self.calls = []

    def undelivered_resend_turn(self, account_id):
        self.calls.append(account_id)
        return SimpleNamespace(
            owner_account_id=account_id,
            fire_ids=list(self.fire_ids),
            trigger_id=f"reminder_undelivered:{account_id}",
        )


class FakeSocialSchedulingService:
    def __init__(self, notification_fact_ids=None) -> None:
        self.notification_fact_ids = list(notification_fact_ids or [])
        self.calls = []

    def undelivered_notification_resend_turn(self, account_id):
        self.calls.append(account_id)
        return SimpleNamespace(
            recipient_account_id=account_id,
            notification_fact_ids=list(self.notification_fact_ids),
            trigger_id=f"notification_undelivered:{account_id}",
        )


def make_client(
    service=None,
    adapters=None,
    conversation_runtime_service=None,
    reminder_service=None,
    social_scheduling_service=None,
    commit_callback=None,
    webhook_secret=None,
):
    service = service or FakeReachabilityService()
    adapters = (
        adapters if adapters is not None else {"whatsapp_evolution": FakeAdapter()}
    )
    app = Flask(__name__)
    app.register_blueprint(
        create_provider_webhook_blueprint(
            service,
            adapters,
            conversation_runtime_service=conversation_runtime_service,
            reminder_service=reminder_service,
            social_scheduling_service=social_scheduling_service,
            commit_callback=commit_callback,
            webhook_secret=webhook_secret,
        )
    )
    return app.test_client(), service, adapters


def test_provider_webhook_normalizes_and_returns_structured_identity_facts_only():
    client, service, adapters = make_client()
    payload = {
        "event": "messages.upsert",
        "instance": "coke",
        "data": {
            "key": {
                "remoteJid": "15555550123@s.whatsapp.net",
                "fromMe": False,
                "id": "wa_msg_1",
            },
            "pushName": "Alice",
            "message": {"conversation": "hello"},
            "messageTimestamp": 1_700_000_000,
        },
    }

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json=payload,
    )

    assert response.status_code == 202
    assert response.get_json() == {
        "accepted": True,
        "provider_type": "whatsapp_evolution",
        "provider_subject": "15555550123",
        "account_id": "acct_1",
        "channel_identity_id": "ci_1",
        "channel_id": "channel_1",
        "created_account": True,
        "raw_event_id": "wa_msg_1",
    }
    assert service.calls[0][0] == "accept_provider_inbound"
    assert service.calls[0][1].raw_event_id == "wa_msg_1"
    assert adapters["whatsapp_evolution"].calls == [payload]


def test_configured_webhook_secret_rejects_missing_header_before_normalization():
    client, service, adapters = make_client(webhook_secret="secret-1")

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={
            "event": "messages.upsert",
            "instance": "coke",
            "data": {
                "key": {
                    "remoteJid": "15555550123@s.whatsapp.net",
                    "fromMe": False,
                    "id": "wa_msg_1",
                },
                "message": {"conversation": "hello"},
                "messageTimestamp": 1_700_000_000,
            },
        },
    )

    assert response.status_code == 401
    assert response.get_json() == {"error": {"code": "webhook_unauthorized"}}
    assert service.calls == []
    assert adapters["whatsapp_evolution"].calls == []


def test_configured_webhook_secret_accepts_coke_secret_header():
    client, service, _adapters = make_client(webhook_secret="secret-1")

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={
            "event": "messages.upsert",
            "instance": "coke",
            "data": {
                "key": {
                    "remoteJid": "15555550123@s.whatsapp.net",
                    "fromMe": False,
                    "id": "wa_msg_1",
                },
                "message": {"conversation": "hello"},
                "messageTimestamp": 1_700_000_000,
            },
        },
        headers={"X-Coke-Webhook-Secret": "secret-1"},
    )

    assert response.status_code == 202
    assert service.calls[0][0] == "accept_provider_inbound"


def test_configured_webhook_secret_accepts_evolution_header_and_bearer_token():
    for headers in (
        {"X-Webhook-Secret": "secret-1"},
        {"Authorization": "Bearer secret-1"},
    ):
        client, service, _adapters = make_client(webhook_secret="secret-1")

        response = client.post(
            "/webhooks/whatsapp/evolution",
            json={
                "event": "messages.upsert",
                "instance": "coke",
                "data": {
                    "key": {
                        "remoteJid": "15555550123@s.whatsapp.net",
                        "fromMe": False,
                        "id": "wa_msg_1",
                    },
                    "message": {"conversation": "hello"},
                    "messageTimestamp": 1_700_000_000,
                },
            },
            headers=headers,
        )

        assert response.status_code == 202
        assert service.calls[0][0] == "accept_provider_inbound"


def test_unset_webhook_secret_keeps_transition_mode_accepting_payloads():
    client, service, _adapters = make_client(webhook_secret=None)

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={
            "event": "messages.upsert",
            "instance": "coke",
            "data": {
                "key": {
                    "remoteJid": "15555550123@s.whatsapp.net",
                    "fromMe": False,
                    "id": "wa_msg_1",
                },
                "message": {"conversation": "hello"},
                "messageTimestamp": 1_700_000_000,
            },
        },
    )

    assert response.status_code == 202
    assert service.calls[0][0] == "accept_provider_inbound"


def test_wechat_personal_webhook_accepts_account_bound_ilink_payload():
    client, service, _adapters = make_client(
        adapters={
            "wechat_personal": WeChatPersonalAdapter(
                now=lambda: datetime(2026, 5, 29, tzinfo=UTC)
            )
        }
    )

    response = client.post(
        "/webhooks/wechat/personal",
        json={
            "account_id": "acct_1",
            "session_id": "session_1",
            "message_id": "wx_msg_1",
            "wxid": "wxid_lizihao",
            "text": "hello",
            "context_token": "ctx-1",
        },
    )

    assert response.status_code == 202
    inbound = service.calls[0][1]
    assert inbound.provider_type == "wechat_personal"
    assert inbound.provider_subject == "wxid_lizihao"
    assert inbound.text == "hello"
    assert inbound.raw_event_id == "wx_msg_1"
    assert inbound.account_id == "acct_1"
    assert inbound.connector_session_id == "session_1"
    assert inbound.context_token == "ctx-1"
    assert inbound.pairing_code is None


def test_wechat_personal_webhook_records_media_with_durable_inbound_turn():
    conversation_runtime = FakeConversationRuntimeService()
    commits = []
    client, _service, _adapters = make_client(
        adapters={
            "wechat_personal": WeChatPersonalAdapter(
                now=lambda: datetime(2026, 5, 29, tzinfo=UTC)
            )
        },
        conversation_runtime_service=conversation_runtime,
        commit_callback=lambda: commits.append("committed"),
    )

    response = client.post(
        "/webhooks/wechat/personal",
        json={
            "account_id": "acct_1",
            "session_id": "session_1",
            "message_id": "wx_msg_image_1",
            "wxid": "wxid_lizihao",
            "text": "",
            "context_token": "ctx-image-1",
            "media": [
                {
                    "media_type": "image",
                    "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                    "mime": "image/jpeg",
                    "agent_label": "image",
                }
            ],
        },
    )

    assert response.status_code == 202
    assert conversation_runtime.calls[0]["text"] == ""
    assert len(conversation_runtime.calls[0]["media"]) == 1
    assert conversation_runtime.calls[0]["media"][0].media_type == "image"
    assert (
        conversation_runtime.calls[0]["media"][0].storage_uri
        == "data:image/jpeg;base64,/9j/2w=="
    )
    assert conversation_runtime.calls[0]["media"][0].mime == "image/jpeg"
    assert conversation_runtime.calls[0]["media"][0].agent_label == "image"
    assert commits == ["committed"]


def test_provider_webhook_records_durable_inbound_turn_when_runtime_is_wired():
    conversation_runtime = FakeConversationRuntimeService()
    commits = []
    client, _service, _adapters = make_client(
        conversation_runtime_service=conversation_runtime,
        commit_callback=lambda: commits.append("committed"),
    )
    payload = {
        "event": "messages.upsert",
        "instance": "coke",
        "data": {
            "key": {
                "remoteJid": "15555550123@s.whatsapp.net",
                "fromMe": False,
                "id": "wa_msg_1",
            },
            "pushName": "Alice",
            "message": {"conversation": "hello"},
            "messageTimestamp": 1_700_000_000,
        },
    }

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json=payload,
        headers={
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        },
    )

    assert response.status_code == 202
    assert conversation_runtime.calls == [
        {
            "account_id": "acct_1",
            "channel_identity_id": "ci_1",
            "causal_inbound_event_id": "wa_msg_1",
            "text": "hello",
            "payload": payload,
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
        }
    ]
    assert commits == ["committed"]


def test_provider_webhook_enqueues_undelivered_resend_after_next_inbound():
    conversation_runtime = FakeConversationRuntimeService()
    reminder_service = FakeReminderService(fire_ids=["fire_1", "fire_2"])
    client, _service, _adapters = make_client(
        conversation_runtime_service=conversation_runtime,
        reminder_service=reminder_service,
    )
    payload = {
        "event": "messages.upsert",
        "instance": "coke",
        "data": {
            "key": {
                "remoteJid": "15555550123@s.whatsapp.net",
                "fromMe": False,
                "id": "wa_msg_1",
            },
            "pushName": "Alice",
            "message": {"conversation": "hello again"},
            "messageTimestamp": 1_700_000_000,
        },
    }

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json=payload,
        headers={
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        },
    )

    assert response.status_code == 202
    assert reminder_service.calls == ["acct_1"]
    assert conversation_runtime.enqueued == [
        {
            "topic": "turn.undelivered_resend",
            "idempotency_key": "undelivered_resend:acct_1:wa_msg_1",
            "payload": {
                "trigger_id": "undelivered_resend:acct_1:wa_msg_1",
                "trigger_type": "UndeliveredResendTurn",
                "account_id": "acct_1",
                "conversation_id": "conversation_1",
                "fire_ids": ["fire_1", "fire_2"],
                "causal_inbound_event_id": "wa_msg_1",
                "framing": "previously_undelivered",
            },
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
        }
    ]


def test_provider_webhook_enqueues_notification_resend_after_next_inbound():
    conversation_runtime = FakeConversationRuntimeService()
    social_service = FakeSocialSchedulingService(
        notification_fact_ids=["notification_fact_1"]
    )
    client, _service, _adapters = make_client(
        conversation_runtime_service=conversation_runtime,
        social_scheduling_service=social_service,
    )
    payload = {
        "event": "messages.upsert",
        "instance": "coke",
        "data": {
            "key": {
                "remoteJid": "15555550123@s.whatsapp.net",
                "fromMe": False,
                "id": "wa_msg_2",
            },
            "pushName": "Alice",
            "message": {"conversation": "hello again"},
            "messageTimestamp": 1_700_000_000,
        },
    }

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json=payload,
        headers={
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        },
    )

    assert response.status_code == 202
    assert social_service.calls == ["acct_1"]
    assert conversation_runtime.enqueued == [
        {
            "topic": "turn.undelivered_resend",
            "idempotency_key": "undelivered_resend:acct_1:wa_msg_2",
            "payload": {
                "trigger_id": "undelivered_resend:acct_1:wa_msg_2",
                "trigger_type": "UndeliveredResendTurn",
                "account_id": "acct_1",
                "conversation_id": "conversation_1",
                "notification_fact_ids": ["notification_fact_1"],
                "causal_inbound_event_id": "wa_msg_2",
                "framing": "previously_undelivered",
            },
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
        }
    ]


def test_provider_webhook_rejects_unknown_provider_with_json_error():
    client, _service, _adapters = make_client(adapters={})

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

    client, service, _adapters = make_client(
        adapters={"wechat_ecloud": WeChatECloudFakeAdapter()}
    )

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

    client, _service, _adapters = make_client(service=ErrorService())

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={
            "event": "messages.upsert",
            "instance": "coke",
            "data": {
                "key": {
                    "remoteJid": "15555550123@s.whatsapp.net",
                    "fromMe": False,
                    "id": "wa_msg_1",
                },
                "message": {"conversation": "hello"},
                "messageTimestamp": 1_700_000_000,
            },
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "active_channel_exists",
            "fact": {"type": "channel_conflict", "account_id": "acct_1"},
        }
    }
