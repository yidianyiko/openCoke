from __future__ import annotations

from datetime import UTC, datetime

import httpx
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
EVOLUTION_TS = datetime.fromtimestamp(1_700_000_000, UTC)


def evolution_payload(
    message: dict,
    *,
    remote_jid: str = "15555550123@s.whatsapp.net",
    from_me: bool = False,
    message_id: str = "EVT1",
) -> dict:
    return {
        "event": "messages.upsert",
        "instance": "coke",
        "data": {
            "key": {
                "remoteJid": remote_jid,
                "fromMe": from_me,
                "id": message_id,
            },
            "pushName": "Alice",
            "message": message,
            "messageTimestamp": 1_700_000_000,
        },
    }


def delivery_route(provider_type: str, address: str) -> DeliveryRoute:
    return DeliveryRoute(
        id="route_1",
        account_id="acct_1",
        channel_id="channel_1",
        provider_type=provider_type,
        provider_address=address,
        route_key=f"{provider_type}:{address}",
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    (
        "adapter",
        "payload",
        "provider_subject",
        "text",
        "raw_event_id",
        "pairing_code",
        "account_id",
        "context_token",
        "sender_display_name",
    ),
    [
        (
            WhatsAppEvolutionAdapter(),
            {
                **evolution_payload(
                    {"conversation": "pair code ABC123"},
                    message_id="wa_msg_1",
                ),
                "pairing_code": "ABC123",
            },
            "15555550123",
            "pair code ABC123",
            "wa_msg_1",
            "ABC123",
            None,
            None,
            "Alice",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_1",
                "wxid": "wxid_alice",
                "sender_name": "Alice WeChat",
                "text": "hello",
                "account_id": "acct_1",
                "session_id": "session_1",
                "context_token": "ctx-1",
            },
            "wxid_alice",
            "hello",
            "wx_msg_1",
            None,
            "acct_1",
            "ctx-1",
            "Alice WeChat",
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
            None,
            None,
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
            None,
            None,
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
    account_id,
    context_token,
    sender_display_name,
):
    inbound = adapter.normalize_inbound(payload)

    assert inbound.provider_type == adapter.provider_type
    assert inbound.provider_subject == provider_subject
    assert inbound.text == text
    assert inbound.raw_event_id == raw_event_id
    assert inbound.pairing_code == pairing_code
    assert inbound.account_id == account_id
    assert inbound.context_token == context_token
    assert inbound.sender_display_name == sender_display_name
    assert inbound.received_at in {NOW, EVOLUTION_TS}
    assert inbound.payload is not payload


def test_whatsapp_evolution_normalizes_extended_text_message():
    adapter = WhatsAppEvolutionAdapter()

    inbound = adapter.normalize_inbound(
        evolution_payload(
            {"extendedTextMessage": {"text": "extended hi"}},
            remote_jid="15555550123@g.us",
            message_id="EVT_EXT",
        )
    )

    assert inbound.provider_subject == "15555550123"
    assert inbound.text == "extended hi"
    assert inbound.raw_event_id == "EVT_EXT"
    assert inbound.received_at == EVOLUTION_TS


def test_whatsapp_evolution_normalizes_media_payload_as_blank_text():
    adapter = WhatsAppEvolutionAdapter()

    inbound = adapter.normalize_inbound(
        evolution_payload(
            {
                "imageMessage": {
                    "mimetype": "image/jpeg",
                    "url": "https://provider.example/image",
                }
            },
            message_id="EVT_IMAGE",
        )
    )

    assert inbound.provider_subject == "15555550123"
    assert inbound.text == ""
    assert inbound.raw_event_id == "EVT_IMAGE"
    assert (
        inbound.payload["data"]["message"]["imageMessage"]["mimetype"] == "image/jpeg"
    )


def test_whatsapp_evolution_rejects_from_me_echo():
    adapter = WhatsAppEvolutionAdapter()

    with pytest.raises(
        ChannelReachabilityError, match="provider_outbound_echo"
    ) as exc_info:
        adapter.normalize_inbound(
            evolution_payload({"conversation": "echo"}, from_me=True)
        )

    assert exc_info.value.code == "provider_outbound_echo"
    assert exc_info.value.fact == {
        "type": "provider_outbound_echo",
        "provider_type": "whatsapp_evolution",
        "raw_event_id": "EVT1",
    }


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            evolution_payload({"conversation": ""}, message_id="wa_msg_blank"),
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
        **evolution_payload({"conversation": "hello"}, message_id="wa_msg_1"),
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
    assert inbound.payload["data"]["message"]["conversation"] == "hello"
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

    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
        adapter.normalize_inbound(
            {
                **evolution_payload({"conversation": "hello"}, message_id="wa_msg_1"),
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

    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
        adapter.normalize_inbound(
            {
                **evolution_payload({"conversation": "hello"}, message_id="wa_msg_1"),
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
            {
                "event": "messages.upsert",
                "data": {
                    "key": {"remoteJid": "15555550123@s.whatsapp.net", "fromMe": False}
                },
            },
            "data.key.id",
        ),
        (WeChatPersonalAdapter(now=lambda: NOW), {"message_id": "wx_msg_1"}, "wxid"),
        (WeChatECloudAdapter(now=lambda: NOW), {"msg_id": "gewe_msg_1"}, "sender_id"),
        (LinqAdapter(now=lambda: NOW), {"id": "sms_msg_1"}, "from"),
    ],
)
def test_provider_adapters_reject_missing_required_fields(
    adapter, payload, missing_field
):
    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
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
            evolution_payload(
                {"conversation": "hello"}, remote_jid="", message_id="wa_msg_1"
            ),
            "data.key.remoteJid",
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
    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
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
            evolution_payload({"conversation": "hello"}, message_id=True),
            "data.key.id",
        ),
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            evolution_payload({"conversation": "hello"}, remote_jid=False),
            "data.key.remoteJid",
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
    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
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
                **evolution_payload({"conversation": "hello"}, message_id="wa_msg_1"),
                "pairing_code": ["ABC123"],
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
    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": "pairing_code",
        "reason": "invalid_optional_field",
    }


@pytest.mark.parametrize("field", ["account_id", "session_id", "context_token"])
def test_wechat_personal_rejects_malformed_ilink_optional_fields(field):
    payload = {
        "message_id": "wx_msg_1",
        "wxid": "wxid_alice",
        "text": "hello",
        field: {"bad": "value"},
    }

    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
        WeChatPersonalAdapter(now=lambda: NOW).normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": "wechat_personal",
        "field": field,
        "reason": "invalid_optional_field",
    }


def test_wechat_personal_normalizes_media_into_inbound_media_input():
    inbound = WeChatPersonalAdapter(now=lambda: NOW).normalize_inbound(
        {
            "account_id": "acct_1",
            "session_id": "session_1",
            "message_id": "wx_msg_image_1",
            "wxid": "wxid_alice",
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
        }
    )

    assert inbound.text == ""
    assert len(inbound.media) == 1
    assert inbound.media[0].media_type == "image"
    assert inbound.media[0].storage_uri == "data:image/jpeg;base64,/9j/2w=="
    assert inbound.media[0].mime == "image/jpeg"
    assert inbound.media[0].agent_label == "image"


@pytest.mark.parametrize(
    "media",
    [
        [
            {
                "media_type": "image",
                "storage_uri": "",
                "mime": "image/jpeg",
                "agent_label": "image",
            }
        ],
        [
            {
                "media_type": "video",
                "storage_uri": "data:video/mp4;base64,AAAA",
                "mime": "video/mp4",
                "agent_label": "video",
            }
        ],
        [
            {
                "media_type": "image",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "mime": {"bad": "value"},
                "agent_label": "image",
            }
        ],
        [
            {
                "media_type": "image",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "mime": "image/jpeg",
                "agent_label": "",
            }
        ],
    ],
)
def test_wechat_personal_rejects_malformed_media(media):
    payload = {
        "account_id": "acct_1",
        "session_id": "session_1",
        "message_id": "wx_msg_image_bad",
        "wxid": "wxid_alice",
        "text": "",
        "context_token": "ctx-image-bad",
        "media": media,
    }

    with pytest.raises(
        ChannelReachabilityError, match="invalid_provider_payload"
    ) as exc_info:
        WeChatPersonalAdapter(now=lambda: NOW).normalize_inbound(payload)

    assert exc_info.value.fact["type"] == "invalid_provider_payload"
    assert exc_info.value.fact["provider_type"] == "wechat_personal"
    assert exc_info.value.fact["field"] == "media"


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


def test_whatsapp_evolution_send_text_posts_real_send_text_request():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"key": {"id": "EV_SEND_1"}})

    adapter = WhatsAppEvolutionAdapter(
        base_url="https://evolution.example",
        api_key="secret-key",
        instance="coke",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: NOW,
    )
    result = adapter.send_text(
        route=delivery_route("whatsapp_evolution", "15555550123"),
        text="hello",
        idempotency_key="send_1",
    )

    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://evolution.example/message/sendText/coke"
    assert requests[0].headers["apikey"] == "secret-key"
    assert requests[0].headers["Idempotency-Key"] == "send_1"
    assert requests[0].read() == b'{"number":"15555550123","text":"hello"}'
    assert result.status == "sent"
    assert result.provider_message_id == "EV_SEND_1"
    assert result.error_code is None
    assert result.delivered_at is None


@pytest.mark.parametrize("status_code", [400, 500])
def test_whatsapp_evolution_send_text_maps_non_2xx_to_failed(status_code):
    adapter = WhatsAppEvolutionAdapter(
        base_url="https://evolution.example",
        api_key="secret-key",
        instance="coke",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(status_code))
        ),
        now=lambda: NOW,
    )

    result = adapter.send_text(
        route=delivery_route("whatsapp_evolution", "15555550123"),
        text="hello",
        idempotency_key="send_1",
    )

    assert result.status == "failed"
    assert result.provider_message_id is None
    assert result.error_code == f"provider_http_{status_code}"
    assert result.delivered_at is None


def test_whatsapp_evolution_send_text_maps_timeout_to_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    adapter = WhatsAppEvolutionAdapter(
        base_url="https://evolution.example",
        api_key="secret-key",
        instance="coke",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        now=lambda: NOW,
    )

    result = adapter.send_text(
        route=delivery_route("whatsapp_evolution", "15555550123"),
        text="hello",
        idempotency_key="send_1",
    )

    assert result.status == "failed"
    assert result.provider_message_id is None
    assert result.error_code == "provider_network_error"
    assert result.delivered_at is None


@pytest.mark.parametrize(
    (
        "adapter_class",
        "adapter_kwargs",
        "route",
        "provider_response",
        "expected_url",
        "expected_json",
        "expected_message_id",
        "send_kwargs",
    ),
    [
        (
            WeChatPersonalAdapter,
            {
                "endpoint_url": "https://connector.example/send",
                "api_key": "wx-secret",
            },
            delivery_route("wechat_personal", "wxid_alice"),
            {"message_id": "WX_SEND"},
            "https://connector.example/send",
            {
                "account_id": "acct_1",
                "to": "wxid_alice",
                "context_token": "ctx-1",
                "text": "hello",
            },
            "WX_SEND",
            {"context_token": "ctx-1"},
        ),
        (
            WeChatECloudAdapter,
            {
                "endpoint_url": "https://gewe.example/message/postText",
                "token": "gewe-token",
                "app_id": "app-1",
            },
            delivery_route("wechat_ecloud", "gewe_alice"),
            {"msgId": "GEWE_SEND"},
            "https://gewe.example/message/postText",
            {"appId": "app-1", "toWxid": "gewe_alice", "content": "hello"},
            "GEWE_SEND",
            {},
        ),
        (
            LinqAdapter,
            {"endpoint_url": "https://linq.example/sms/send", "api_key": "sms-secret"},
            delivery_route("linq", "+15555550123"),
            {"id": "SMS_SEND"},
            "https://linq.example/sms/send",
            {"to": "+15555550123", "text": "hello"},
            "SMS_SEND",
            {},
        ),
    ],
)
def test_secondary_provider_send_text_posts_real_http_request(
    adapter_class,
    adapter_kwargs,
    route,
    provider_response,
    expected_url,
    expected_json,
    expected_message_id,
    send_kwargs,
):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=provider_response)

    adapter = adapter_class(
        **adapter_kwargs,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send_text(
        route=route,
        text="hello",
        idempotency_key="send_1",
        **send_kwargs,
    )

    assert requests[0].method == "POST"
    assert str(requests[0].url) == expected_url
    assert requests[0].headers["Idempotency-Key"] == "send_1"
    assert (
        requests[0].read()
        == httpx.Request(
            "POST",
            expected_url,
            json=expected_json,
        ).read()
    )
    assert result.status == "sent"
    assert result.provider_message_id == expected_message_id
    assert result.error_code is None


def test_wechat_personal_send_text_maps_connector_ilink_failure_to_clear_code():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={
                "error": "ilink_send_failed",
                "ilink": {"ret": -2, "errmsg": "invalid context_token"},
            },
        )

    adapter = WeChatPersonalAdapter(
        endpoint_url="https://connector.example/send",
        api_key="wx-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.send_text(
        route=delivery_route("wechat_personal", "wxid_alice"),
        text="hello",
        idempotency_key="send_1",
        context_token="ctx-bad",
    )

    assert result.status == "failed"
    assert result.provider_message_id is None
    assert result.error_code == "ilink_send_failed_ret_-2"


def test_wechat_personal_login_uses_connector_root_when_send_endpoint_configured():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={
                "session_id": "session_1",
                "qrcode": "qr_1",
                "qrcode_image_data_url": "data:image/png;base64,abc",
            },
        )

    adapter = WeChatPersonalAdapter(
        endpoint_url="https://connector.example/send",
        api_key="wx-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    adapter.start_login(account_id="acct_1")

    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://connector.example/login/start"
    assert requests[0].headers["Authorization"] == "Bearer wx-secret"


def test_wechat_personal_login_status_timeout_returns_pending_status():
    request = httpx.Request(
        "GET",
        "https://connector.example/login/status?account_id=acct_1&session_id=session_1",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow connector", request=request)

    adapter = WeChatPersonalAdapter(
        endpoint_url="https://connector.example/send",
        api_key="wx-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    status = adapter.poll_login_status(account_id="acct_1", session_id="session_1")

    assert status == {
        "account_id": "acct_1",
        "session_id": "session_1",
        "status": "waiting_for_scan",
        "connector_status": "timeout",
        "retryable": True,
    }


def test_wechat_personal_login_status_remote_disconnect_returns_pending_status():
    request = httpx.Request(
        "GET",
        "https://connector.example/login/status?account_id=acct_1&session_id=session_1",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError(
            "Server disconnected without sending a response.",
            request=request,
        )

    adapter = WeChatPersonalAdapter(
        endpoint_url="https://connector.example/send",
        api_key="wx-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    status = adapter.poll_login_status(account_id="acct_1", session_id="session_1")

    assert status == {
        "account_id": "acct_1",
        "session_id": "session_1",
        "status": "waiting_for_scan",
        "connector_status": "timeout",
        "retryable": True,
    }
