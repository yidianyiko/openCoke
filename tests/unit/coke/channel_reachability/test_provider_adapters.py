from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryRoute,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    RETAINED_PROVIDER_TYPES,
)
from coke.providers.base import provider_registry
from coke.providers.linq import LinqAdapter
from coke.providers.wechat_ecloud import WeChatECloudAdapter
from coke.providers.wechat_personal import WeChatPersonalAdapter
from coke.providers.whatsapp_evolution import WhatsAppEvolutionAdapter


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("adapter", "payload", "provider_subject", "text", "raw_event_id", "pairing_code"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "pair code ABC123",
                "pairing_code": "ABC123",
            },
            "whatsapp:+15555550123",
            "pair code ABC123",
            "wa_msg_1",
            "ABC123",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_1",
                "wxid": "wxid_alice",
                "text": "hello",
                "pairing_code": "WXPAIR",
            },
            "wxid_alice",
            "hello",
            "wx_msg_1",
            "WXPAIR",
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {
                "msg_id": "gewe_msg_1",
                "sender_id": "gewe_alice",
                "content": "hello",
            },
            "gewe_alice",
            "hello",
            "gewe_msg_1",
            None,
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {
                "id": "sms_msg_1",
                "from": "+15555550123",
                "body": "hello",
            },
            "+15555550123",
            "hello",
            "sms_msg_1",
            None,
        ),
    ],
)
def test_provider_adapters_normalize_inbound_payloads(
    adapter,
    payload,
    provider_subject,
    text,
    raw_event_id,
    pairing_code,
):
    inbound = adapter.normalize_inbound(payload)

    assert inbound.provider_type == adapter.provider_type
    assert inbound.provider_subject == provider_subject
    assert inbound.text == text
    assert inbound.raw_event_id == raw_event_id
    assert inbound.pairing_code == pairing_code
    assert inbound.received_at == NOW
    assert inbound.payload is not payload


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {
                "message_id": "wa_msg_blank",
                "sender": "whatsapp:+15555550123",
                "text": "",
            },
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_blank",
                "wxid": "wxid_alice",
                "text": "   ",
            },
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {
                "msg_id": "gewe_msg_blank",
                "sender_id": "gewe_alice",
                "content": "",
            },
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {
                "id": "sms_msg_blank",
                "from": "+15555550123",
                "body": "   ",
            },
        ),
    ],
)
def test_provider_adapters_normalize_explicit_blank_text(adapter, payload):
    inbound = adapter.normalize_inbound(payload)

    assert inbound.text == ""


def test_normalized_inbound_payload_is_recursively_immutable_copy():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)
    payload = {
        "message_id": "wa_msg_1",
        "sender": "whatsapp:+15555550123",
        "text": "hello",
        "metadata": {
            "headers": {"x-provider": "evolution"},
            "attachments": [{"id": "att_1", "labels": ["receipt", "image"]}],
        },
    }

    inbound = adapter.normalize_inbound(payload)
    payload["text"] = "mutated"
    payload["metadata"]["headers"]["x-provider"] = "mutated"
    payload["metadata"]["attachments"][0]["labels"].append("mutated")

    assert inbound.text == "hello"
    assert inbound.payload["text"] == "hello"
    assert inbound.payload["metadata"]["headers"]["x-provider"] == "evolution"
    assert inbound.payload["metadata"]["attachments"][0]["labels"] == (
        "receipt",
        "image",
    )
    with pytest.raises(TypeError):
        inbound.payload["text"] = "corrupt"
    with pytest.raises(TypeError):
        inbound.payload["metadata"]["headers"]["x-provider"] = "corrupt"
    with pytest.raises(TypeError):
        inbound.payload["metadata"]["attachments"][0]["id"] = "corrupt"
    with pytest.raises(AttributeError):
        inbound.payload["metadata"]["attachments"].append({"id": "corrupt"})


def test_provider_adapters_reject_non_json_payload_evidence_values():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)

    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "hello",
                "metadata": {"raw_bytes": b"not-json"},
            }
        )

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": "whatsapp_evolution",
        "field": "payload.metadata.raw_bytes",
        "reason": "non_json_payload_value",
    }


def test_provider_adapters_reject_tuple_payload_evidence_values():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)

    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "hello",
                "metadata": {"attachments": ("att_1",)},
            }
        )

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": "whatsapp_evolution",
        "field": "payload.metadata.attachments",
        "reason": "non_json_payload_value",
    }


@pytest.mark.parametrize(
    ("adapter", "payload", "missing_field"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"sender": "whatsapp:+15555550123"},
            "message_id",
        ),
        (WeChatPersonalAdapter(now=lambda: NOW), {"message_id": "wx_msg_1"}, "wxid"),
        (WeChatECloudAdapter(now=lambda: NOW), {"msg_id": "gewe_msg_1"}, "sender_id"),
        (LinqAdapter(now=lambda: NOW), {"id": "sms_msg_1"}, "from"),
    ],
)
def test_provider_adapters_reject_missing_required_fields(adapter, payload, missing_field):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": missing_field,
        "reason": "missing_required_field",
    }


@pytest.mark.parametrize(
    ("adapter", "payload", "field"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"message_id": "wa_msg_1", "sender": "", "text": "hello"},
            "sender",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {"message_id": "wx_msg_1", "wxid": None, "text": "hello"},
            "wxid",
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {"msg_id": "gewe_msg_1", "sender_id": [], "content": "hello"},
            "sender_id",
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {"id": "sms_msg_1", "from": {}, "body": "hello"},
            "from",
        ),
    ],
)
def test_provider_adapters_reject_malformed_required_fields(adapter, payload, field):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": field,
        "reason": "invalid_required_field",
    }


@pytest.mark.parametrize(
    ("adapter", "payload", "field"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"message_id": True, "sender": "whatsapp:+15555550123", "text": "hello"},
            "message_id",
        ),
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"message_id": "wa_msg_1", "sender": False, "text": "hello"},
            "sender",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {"message_id": "wx_msg_1", "wxid": True, "text": "hello"},
            "wxid",
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {"msg_id": "gewe_msg_1", "sender_id": False, "content": "hello"},
            "sender_id",
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {"id": "sms_msg_1", "from": True, "body": "hello"},
            "from",
        ),
    ],
)
def test_provider_adapters_reject_boolean_required_fields(adapter, payload, field):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": field,
        "reason": "invalid_required_field",
    }


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "hello",
                "pairing_code": ["ABC123"],
            },
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_1",
                "wxid": "wxid_alice",
                "text": "hello",
                "pairing_code": {"code": "WXPAIR"},
            },
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {
                "msg_id": "gewe_msg_1",
                "sender_id": "gewe_alice",
                "content": "hello",
                "pairing_code": ("ECLOUDPAIR",),
            },
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {
                "id": "sms_msg_1",
                "from": "+15555550123",
                "body": "hello",
                "pairing_code": {"code": "SMSPAIR"},
            },
        ),
    ],
)
def test_provider_adapters_reject_malformed_pairing_code(adapter, payload):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": "pairing_code",
        "reason": "invalid_optional_field",
    }


def test_registry_contains_all_retained_provider_adapters():
    registry = provider_registry(
        [
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            WeChatPersonalAdapter(now=lambda: NOW),
            WeChatECloudAdapter(now=lambda: NOW),
            LinqAdapter(now=lambda: NOW),
        ]
    )

    assert set(registry) == {
        "whatsapp_evolution",
        "wechat_personal",
        "wechat_ecloud",
        "linq",
    }
    assert RETAINED_PROVIDER_TYPES == {
        "whatsapp_evolution",
        "wechat_personal",
        "wechat_ecloud",
        "linq",
    }
    assert PRODUCT_CHANNEL_PROVIDER_TYPES == {
        "whatsapp_evolution",
        "wechat_personal",
    }


def test_fake_send_text_returns_provider_attempt_result():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)
    route = DeliveryRoute(
        id="route_1",
        account_id="acct_1",
        channel_id="channel_1",
        provider_type="whatsapp_evolution",
        provider_address="whatsapp:+15555550123",
        route_key="whatsapp_evolution:whatsapp:+15555550123",
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
    )

    result = adapter.send_text(
        route=route,
        text="hello",
        idempotency_key="send_1",
    )

    assert result.status == "sent"
    assert result.provider_message_id == "whatsapp_evolution:send_1"
    assert result.error_code is None
    assert result.delivered_at is None
