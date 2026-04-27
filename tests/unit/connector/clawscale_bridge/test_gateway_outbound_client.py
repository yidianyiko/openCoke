from unittest.mock import MagicMock


def test_gateway_outbound_client_posts_normalized_payload_with_auth_header():
    from connector.clawscale_bridge.gateway_outbound_client import (
        GatewayOutboundClient,
    )

    session = MagicMock()
    session.post.return_value.status_code = 200

    client = GatewayOutboundClient(
        api_url="https://gateway.local/api/outbound",
        api_key="outbound-secret",
        session=session,
        timeout_seconds=12,
    )

    response = client.post_output(
        output_id="out_1",
        account_id="acc_1",
        business_conversation_key="bc_1",
        text="time to eat",
        message_type="text",
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id="in_1",
    )

    assert response.status_code == 200
    session.post.assert_called_once_with(
        "https://gateway.local/api/outbound",
        json={
            "output_id": "out_1",
            "customer_id": "acc_1",
            "business_conversation_key": "bc_1",
            "text": "time to eat",
            "message_type": "text",
            "delivery_mode": "push",
            "expect_output_timestamp": "2024-03-09T16:00:00Z",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "causal_inbound_event_id": "in_1",
        },
        headers={"Authorization": "Bearer outbound-secret"},
        timeout=12,
    )


def test_gateway_outbound_client_omits_optional_causal_event_id():
    from connector.clawscale_bridge.gateway_outbound_client import (
        GatewayOutboundClient,
    )

    session = MagicMock()
    session.post.return_value.status_code = 202

    client = GatewayOutboundClient(
        api_url="https://gateway.local/api/outbound",
        api_key="outbound-secret",
        session=session,
    )

    client.post_output(
        output_id="out_1",
        account_id="acc_1",
        business_conversation_key="bc_1",
        text="time to eat",
        message_type="text",
        delivery_mode="push",
        expect_output_timestamp="2024-03-09T16:00:00Z",
        idempotency_key="idem_1",
        trace_id="trace_1",
    )

    session.post.assert_called_once_with(
        "https://gateway.local/api/outbound",
        json={
            "output_id": "out_1",
            "customer_id": "acc_1",
            "business_conversation_key": "bc_1",
            "text": "time to eat",
            "message_type": "text",
            "delivery_mode": "push",
            "expect_output_timestamp": "2024-03-09T16:00:00Z",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
        },
        headers={"Authorization": "Bearer outbound-secret"},
        timeout=15,
    )


def test_gateway_outbound_client_serializes_media_options():
    from connector.clawscale_bridge.gateway_outbound_client import (
        GatewayOutboundClient,
    )

    session = MagicMock()

    client = GatewayOutboundClient(
        api_url="https://gateway.local/api/outbound",
        api_key="outbound-secret",
        session=session,
    )

    client.post_output(
        output_id="out_1",
        account_id="acc_1",
        business_conversation_key="bc_1",
        text="voice note",
        message_type="voice",
        delivery_mode="push",
        expect_output_timestamp="2024-03-09T16:00:00Z",
        idempotency_key="idem_1",
        trace_id="trace_1",
        media_urls=["https://cdn.example.com/voice.mp3"],
        audio_as_voice=True,
    )

    session.post.assert_called_once_with(
        "https://gateway.local/api/outbound",
        json={
            "output_id": "out_1",
            "customer_id": "acc_1",
            "business_conversation_key": "bc_1",
            "text": "voice note",
            "message_type": "voice",
            "delivery_mode": "push",
            "expect_output_timestamp": "2024-03-09T16:00:00Z",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "mediaUrls": ["https://cdn.example.com/voice.mp3"],
            "audioAsVoice": True,
        },
        headers={"Authorization": "Bearer outbound-secret"},
        timeout=15,
    )
