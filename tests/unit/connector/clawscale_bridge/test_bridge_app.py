import pytest
from unittest.mock import MagicMock


def test_create_app_uses_configured_bridge_api_key_in_non_testing_mode(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"], "api_key", "local-bridge-key"
    )
    monkeypatch.setattr(
        bridge_app, "_build_default_bridge_gateway", lambda: MagicMock()
    )
    monkeypatch.setattr(
        bridge_app, "_build_google_calendar_import_service", lambda: MagicMock()
    )

    app = bridge_app.create_app(testing=False)

    assert app.config["COKE_BRIDGE_API_KEY"] == "local-bridge-key"


def test_create_app_rejects_unresolved_required_bridge_settings(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"], "api_key", "${COKE_BRIDGE_API_KEY}"
    )

    with pytest.raises(RuntimeError) as exc:
        bridge_app.create_app(testing=False)

    assert str(exc.value) == "missing_required_clawscale_bridge_setting:api_key"


def test_create_app_starts_output_dispatcher_loop_in_non_testing_mode(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"], "api_key", "local-bridge-key"
    )
    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"],
        "outbound_api_url",
        "https://gateway.local/api/outbound",
    )
    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"],
        "outbound_api_key",
        "outbound-secret",
    )
    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"],
        "output_dispatcher_poll_interval_seconds",
        7,
    )
    monkeypatch.setattr(
        bridge_app, "_build_default_bridge_gateway", lambda: MagicMock()
    )
    monkeypatch.setattr(
        bridge_app, "_build_google_calendar_import_service", lambda: MagicMock()
    )
    monkeypatch.setattr(bridge_app, "MongoDBBase", lambda **kwargs: MagicMock())

    dispatcher_captured = {}

    class FakeDispatcher:
        def __init__(self, **kwargs):
            dispatcher_captured.update(kwargs)

        def dispatch_once(self):
            return False

    thread_captured = {}

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            thread_captured.update(
                {"target": target, "args": args, "daemon": daemon, "started": False}
            )

        def start(self):
            thread_captured["started"] = True

    monkeypatch.setattr(
        bridge_app, "ClawScaleOutputDispatcher", FakeDispatcher, raising=False
    )
    monkeypatch.setattr(
        bridge_app,
        "threading",
        type("ThreadingModule", (), {"Thread": FakeThread})(),
        raising=False,
    )

    bridge_app.create_app(testing=False)

    assert dispatcher_captured["outbound_api_url"] == "https://gateway.local/api/outbound"
    assert dispatcher_captured["outbound_api_key"] == "outbound-secret"
    assert thread_captured["daemon"] is True
    assert thread_captured["target"] is bridge_app._run_output_dispatcher_loop
    assert thread_captured["started"] is True
    assert thread_captured["args"][0] is not None
    assert thread_captured["args"][1] == 7


def test_output_dispatcher_loop_logs_exception_and_continues(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    dispatcher = MagicMock()
    dispatcher.dispatch_once.side_effect = [RuntimeError("temporary"), False]
    logger = MagicMock()
    sleep_calls = []

    class LoopExit(Exception):
        pass

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            raise LoopExit()

    monkeypatch.setattr(bridge_app, "logger", logger, raising=False)
    monkeypatch.setattr(bridge_app.time, "sleep", fake_sleep)

    with pytest.raises(LoopExit):
        bridge_app._run_output_dispatcher_loop(dispatcher, 3)

    assert dispatcher.dispatch_once.call_count == 2
    logger.exception.assert_called_once()
    assert sleep_calls == [3, 3]


def test_build_default_bridge_gateway_wires_business_only_protocol_services(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    gateway_captured = {}

    monkeypatch.setattr(
        bridge_app, "_mongo_uri", lambda: "mongodb://example", raising=False
    )
    monkeypatch.setitem(
        bridge_app.CONF["mongodb"], "mongodb_name", "test_db"
    )
    user_dao = MagicMock()
    message_gateway = MagicMock()
    reply_waiter = MagicMock()
    monkeypatch.setattr(bridge_app, "UserDAO", lambda **kwargs: user_dao)
    monkeypatch.setattr(bridge_app, "MongoDBBase", lambda **kwargs: MagicMock())
    monkeypatch.setattr(bridge_app, "CokeMessageGateway", lambda **kwargs: message_gateway)
    monkeypatch.setattr(bridge_app, "ReplyWaiter", lambda **kwargs: reply_waiter)

    class FakeBridgeGateway:
        def __init__(self, **kwargs):
            gateway_captured.update(kwargs)

    monkeypatch.setattr(bridge_app, "BusinessOnlyBridgeGateway", FakeBridgeGateway)
    monkeypatch.setattr(
        bridge_app,
        "_resolve_target_character_id",
        lambda user_dao: "char_1",
        raising=False,
    )

    bridge_app._build_default_bridge_gateway()

    assert gateway_captured["message_gateway"] is message_gateway
    assert gateway_captured["reply_waiter"] is reply_waiter
    assert gateway_captured["target_character_id"] == "char_1"


def test_bridge_user_auth_routes_are_not_registered():
    from connector.clawscale_bridge.app import create_app

    client = create_app(testing=True).test_client()

    assert client.post("/user/register").status_code == 404
    assert client.post("/user/login").status_code == 404
    assert client.post("/user/wechat-channel").status_code == 404
    assert client.post("/user/wechat-channel/connect").status_code == 404
    assert client.get("/user/wechat-channel/status").status_code == 404
    assert client.post("/user/wechat-channel/disconnect").status_code == 404
    assert client.delete("/user/wechat-channel").status_code == 404


def test_bridge_inbound_rejects_missing_bearer_token():
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    client = app.test_client()

    response = client.post("/bridge/inbound", json={"messages": []})

    assert response.status_code == 401


def test_bridge_inbound_rejects_untrusted_payload_without_bind_flow(monkeypatch):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=MagicMock(),
        reply_waiter=MagicMock(),
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_id": "wxid_123",
            "end_user_id": "eu_1",
            "input": "你好",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": "missing_coke_account_id",
    }


@pytest.mark.parametrize(
    ("payload", "expected_account_id"),
    [
        (
            {
                "tenant_id": "ten_1",
                "channel_id": "ch_1",
                "platform": "wechat_personal",
                "external_id": "wxid_123",
                "end_user_id": "eu_1",
                "input": "你好",
                "channel_scope": "personal",
                "clawscale_user_id": "csu_1",
                "customer_id": "acct_customer_snake",
            },
            "acct_customer_snake",
        ),
        (
            {
                "messages": [{"role": "user", "content": "你好"}],
                "metadata": {
                    "tenantId": "ten_1",
                    "channelId": "ch_1",
                    "platform": "wechat_personal",
                    "externalId": "wxid_123",
                    "endUserId": "eu_1",
                    "channelScope": "personal",
                    "clawscaleUserId": "csu_1",
                    "customerId": "acct_customer_camel",
                },
            },
            "acct_customer_camel",
        ),
    ],
)
def test_bridge_inbound_accepts_customer_id_aliases_for_existing_account_gate(
    monkeypatch, payload, expected_account_id
):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "in_evt_customer_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = {"reply": "ok"}
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    response = app.test_client().post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "reply": "ok"}
    assert message_gateway.enqueue.call_args.kwargs["account_id"] == expected_account_id
    assert reply_waiter.wait_for_reply.call_args.args == ("in_evt_customer_1",)


def test_bridge_inbound_accepts_shared_channel_customer_ids_without_personal_scope(
    monkeypatch,
):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "in_evt_shared_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = {"reply": "shared ok"}
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    response = app.test_client().post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_shared",
                "platform": "whatsapp_evolution",
                "externalId": "8617807028761",
                "endUserId": "eu_shared_1",
                "customerId": "ck_shared_1",
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "reply": "shared ok"}
    assert message_gateway.enqueue.call_args.kwargs["account_id"] == "ck_shared_1"
    assert reply_waiter.wait_for_reply.call_args.args == ("in_evt_shared_1",)


def test_bridge_inbound_blocks_denied_accounts_without_enqueueing(monkeypatch):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    reply_waiter = MagicMock()
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "gatewayConversationId": "gw_conv_1",
                "inboundEventId": "in_evt_1002",
                "externalId": "wxid_123",
                "businessConversationKey": "bc_1002",
                "platform": "wechat_personal",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acct_1",
                "cokeAccountDisplayName": "Alice",
                "accountStatus": "subscription_required",
                "emailVerified": True,
                "subscriptionActive": False,
                "subscriptionExpiresAt": "2026-04-30T00:00:00Z",
                "accountAccessAllowed": False,
                "accountAccessDeniedReason": "subscription_required",
                "renewalUrl": "https://renew.example/checkout",
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "reply": (
            "Your subscription is required. Renew here: "
            "https://renew.example/checkout"
        ),
    }
    message_gateway.enqueue.assert_not_called()
    reply_waiter.wait_for_reply.assert_not_called()


def test_first_turn_inbound_uses_normalized_shape_and_returns_business_metadata(
    monkeypatch,
):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "in_evt_1001"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = {
        "reply": "你好，我在",
        "business_conversation_key": "bc_1001",
        "output_id": "out_1001",
        "causal_inbound_event_id": "in_evt_1001",
    }
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    client = app.test_client()
    payload = {
        "tenant_id": "ten_1",
        "channel_id": "ch_1",
        "end_user_id": "eu_1",
        "external_id": "wxid_123",
        "platform": "wechat_personal",
        "input": "在吗",
        "inbound_event_id": "in_evt_1001",
        "sync_reply_token": "sync_tok_1",
        "channel_scope": "personal",
        "clawscale_user_id": "csu_1",
        "coke_account_id": "acct_1",
        "coke_account_display_name": "Alice",
        "account_status": "active",
        "email_verified": True,
        "subscription_active": True,
        "subscription_expires_at": "2026-04-30T00:00:00Z",
        "account_access_allowed": True,
        "account_access_denied_reason": None,
        "renewal_url": "https://renew.example/checkout",
    }
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "reply": "你好，我在",
        "business_conversation_key": "bc_1001",
        "output_id": "out_1001",
        "causal_inbound_event_id": "in_evt_1001",
    }
    message_gateway.enqueue.assert_called_once()
    enqueue_inbound = message_gateway.enqueue.call_args.kwargs["inbound"]
    assert isinstance(enqueue_inbound.get("timestamp"), int)
    assert enqueue_inbound == {
        "tenant_id": "ten_1",
        "channel_id": "ch_1",
        "platform": "wechat_personal",
        "end_user_id": "eu_1",
        "external_id": "wxid_123",
        "timestamp": enqueue_inbound["timestamp"],
        "sync_reply_token": "sync_tok_1",
        "inbound_event_id": "in_evt_1001",
        "customer_id": "acct_1",
        "coke_account_id": "acct_1",
        "coke_account_display_name": "Alice",
    }
    reply_waiter.wait_for_reply.assert_called_once_with(
        "in_evt_1001", sync_reply_token="sync_tok_1"
    )


def test_bridge_inbound_turns_sync_timeout_into_async_late_reply_fallback(monkeypatch):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "in_evt_timeout_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.side_effect = TimeoutError(
        "Timed out waiting for causal_inbound_event_id=in_evt_timeout_1"
    )
    late_reply_fallback = MagicMock()

    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
        late_reply_fallback=late_reply_fallback,
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "end_user_id": "eu_1",
            "external_id": "wxid_123",
            "platform": "whatsapp_evolution",
            "input": "are you there?",
            "inbound_event_id": "in_evt_timeout_1",
            "sync_reply_token": "sync_tok_timeout_1",
            "channel_scope": "shared",
            "coke_account_id": "acct_1",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    late_reply_fallback.start_async.assert_called_once_with(
        causal_inbound_event_id="in_evt_timeout_1",
        customer_id="acct_1",
        tenant_id="ten_1",
        conversation_id=None,
        channel_id="ch_1",
        end_user_id="eu_1",
        external_end_user_id="wxid_123",
        sync_reply_token="sync_tok_timeout_1",
    )


def test_late_reply_fallback_promotes_pending_sync_reply_for_async_dispatch():
    import connector.clawscale_bridge.app as bridge_app

    mongo = MagicMock()
    mongo.update_one.return_value = 1
    reply_waiter = MagicMock()
    delivery_route_client = MagicMock()
    reply_waiter.wait_for_reply_message.return_value = {
        "_id": "out_late_1",
        "status": "pending",
        "message": "稍后补发",
        "metadata": {
            "source": "clawscale",
            "business_protocol": {
                "delivery_mode": "request_response",
                "causal_inbound_event_id": "in_evt_late_1",
                "business_conversation_key": "bc_late_1",
            },
        },
    }

    promoter = bridge_app.LateReplyFallbackPromoter(
        mongo=mongo,
        reply_waiter=reply_waiter,
        delivery_route_client=delivery_route_client,
    )

    promoted = promoter._promote_for_async_dispatch(
        causal_inbound_event_id="in_evt_late_1",
        customer_id="acct_1",
        tenant_id="ten_1",
        conversation_id="conv_1",
        channel_id="ch_1",
        end_user_id="eu_1",
        external_end_user_id="wxid_1",
        sync_reply_token="sync_tok_late_1",
    )

    assert promoted is True
    reply_waiter.wait_for_reply_message.assert_called_once_with(
        "in_evt_late_1",
        sync_reply_token="sync_tok_late_1",
        consume=False,
    )
    delivery_route_client.bind.assert_called_once_with(
        tenant_id="ten_1",
        conversation_id="conv_1",
        account_id="acct_1",
        business_conversation_key="bc_late_1",
        channel_id="ch_1",
        end_user_id="eu_1",
        external_end_user_id="wxid_1",
    )
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_late_1", "status": "pending"},
        {
            "$set": {
                "customer_id": "acct_1",
                "metadata.business_conversation_key": "bc_late_1",
                "metadata.delivery_mode": "push",
                "metadata.output_id": "out_late_1",
                "metadata.idempotency_key": "late_sync_reply:out_late_1",
                "metadata.trace_id": "late_sync_reply:out_late_1",
                "metadata.causal_inbound_event_id": "in_evt_late_1",
            }
        },
    )


def test_bridge_inbound_accepts_live_messages_and_metadata_shape(monkeypatch):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "in_evt_live_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = {
        "reply": "live ok",
        "business_conversation_key": "bc_live_1",
        "output_id": "out_live_1",
        "causal_inbound_event_id": "in_evt_live_1",
    }
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "gatewayConversationId": "gw_conv_1",
                "inboundEventId": "in_evt_live_1",
                "externalId": "wxid_123",
                "businessConversationKey": "bc_live_1",
                "platform": "wechat_personal",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acct_1",
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "reply": "live ok",
        "business_conversation_key": "bc_live_1",
        "output_id": "out_live_1",
        "causal_inbound_event_id": "in_evt_live_1",
    }
    message_gateway.enqueue.assert_called_once()
    reply_waiter.wait_for_reply.assert_called_once_with("in_evt_live_1")


def test_google_calendar_import_preflight_rejects_missing_bearer_token():
    from connector.clawscale_bridge.app import create_app

    client = create_app(testing=True).test_client()

    response = client.post(
        "/bridge/internal/google-calendar-import/preflight",
        json={"customer_id": "ck_1"},
    )

    assert response.status_code == 401


def test_google_calendar_import_preflight_returns_target_conversation(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    service = MagicMock(
        preflight=MagicMock(
            return_value={
                "conversation_id": "conv-1",
                "user_id": "ck_1",
                "character_id": "char_1",
                "timezone": "Asia/Tokyo",
            }
        )
    )
    monkeypatch.setitem(app.config, "GOOGLE_CALENDAR_IMPORT_SERVICE", service)

    response = app.test_client().post(
        "/bridge/internal/google-calendar-import/preflight",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={"customer_id": "ck_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "data": {
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "Asia/Tokyo",
        },
    }
    service.preflight.assert_called_once_with(
        customer_id="ck_1",
        business_conversation_key=None,
        gateway_conversation_id=None,
    )


def test_google_calendar_import_preflight_forwards_business_conversation_context(
    monkeypatch,
):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    service = MagicMock(
        preflight=MagicMock(
            return_value={
                "conversation_id": "conv-whatsapp",
                "user_id": "ck_email",
                "character_id": "char_1",
                "timezone": "Asia/Tokyo",
            }
        )
    )
    monkeypatch.setitem(app.config, "GOOGLE_CALENDAR_IMPORT_SERVICE", service)

    response = app.test_client().post(
        "/bridge/internal/google-calendar-import/preflight",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "customer_id": "ck_email",
            "business_conversation_key": "bc_1",
            "gateway_conversation_id": "gw_1",
        },
    )

    assert response.status_code == 200
    service.preflight.assert_called_once_with(
        customer_id="ck_email",
        business_conversation_key="bc_1",
        gateway_conversation_id="gw_1",
    )


def test_google_calendar_import_preflight_returns_conversation_required(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    service = MagicMock(preflight=MagicMock(side_effect=ValueError("conversation_required")))
    monkeypatch.setitem(app.config, "GOOGLE_CALENDAR_IMPORT_SERVICE", service)

    response = app.test_client().post(
        "/bridge/internal/google-calendar-import/preflight",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={"customer_id": "ck_1"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": "conversation_required",
    }


def test_google_calendar_import_run_rejects_missing_bearer_token():
    from connector.clawscale_bridge.app import create_app

    client = create_app(testing=True).test_client()

    response = client.post(
        "/bridge/internal/google-calendar-import/run",
        json={"customer_id": "ck_1", "identity_id": "id_1", "run_id": "run_1", "events": []},
    )

    assert response.status_code == 401


def test_google_calendar_import_run_returns_counts_and_warnings(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    target = {
        "conversation_id": "conv-1",
        "user_id": "ck_1",
        "character_id": "char_1",
        "timezone": "Asia/Tokyo",
    }
    service = MagicMock(
        preflight=MagicMock(return_value=target),
        import_events=MagicMock(
            return_value={
                "imported_count": 2,
                "skipped_count": 1,
                "warning_count": 1,
                "warnings": [
                    {
                        "event_id": "evt-2",
                        "reason": "unsupported_recurring_exceptions",
                    }
                ],
            }
        )
    )
    monkeypatch.setitem(app.config, "GOOGLE_CALENDAR_IMPORT_SERVICE", service)

    payload = {
        "customer_id": "ck_1",
        "identity_id": "ident_1",
        "run_id": "run_1",
        "provider_account_email": "alice@example.com",
        "target_conversation_id": "conv-1",
        "target_character_id": "char_1",
        "target_timezone": "Asia/Tokyo",
        "calendar_defaults": {"timezone": "Asia/Tokyo", "default_reminders": []},
        "events": [{"id": "evt-1", "status": "confirmed"}],
    }

    response = app.test_client().post(
        "/bridge/internal/google-calendar-import/run",
        headers={"Authorization": "Bearer test-bridge-key"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "data": {
            "imported_count": 2,
            "skipped_count": 1,
            "warning_count": 1,
            "warnings": [
                {
                    "event_id": "evt-2",
                    "reason": "unsupported_recurring_exceptions",
                }
            ],
        },
    }
    service.preflight.assert_not_called()
    service.import_events.assert_called_once_with(
        target=target,
        run_id="run_1",
        provider_account_email="alice@example.com",
        calendar_defaults={"timezone": "Asia/Tokyo", "default_reminders": []},
        events=[{"id": "evt-1", "status": "confirmed"}],
    )


def test_google_calendar_import_run_uses_provided_target_without_re_resolving(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    service = MagicMock(
        preflight=MagicMock(
            side_effect=AssertionError("run route should not re-resolve target")
        ),
        import_events=MagicMock(
            return_value={
                "imported_count": 1,
                "skipped_count": 0,
                "warning_count": 0,
                "warnings": [],
            }
        ),
    )
    monkeypatch.setitem(app.config, "GOOGLE_CALENDAR_IMPORT_SERVICE", service)

    response = app.test_client().post(
        "/bridge/internal/google-calendar-import/run",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "customer_id": "ck_1",
            "identity_id": "ident_1",
            "run_id": "run_2",
            "target_conversation_id": "conv-stable",
            "target_character_id": "char-stable",
            "target_timezone": "America/New_York",
            "calendar_defaults": {"timezone": "Asia/Tokyo", "default_reminders": []},
            "events": [{"id": "evt-1", "status": "confirmed"}],
        },
    )

    assert response.status_code == 200
    service.preflight.assert_not_called()
    service.import_events.assert_called_once_with(
        target={
            "conversation_id": "conv-stable",
            "user_id": "ck_1",
            "character_id": "char-stable",
            "timezone": "America/New_York",
        },
        run_id="run_2",
        provider_account_email=None,
        calendar_defaults={"timezone": "Asia/Tokyo", "default_reminders": []},
        events=[{"id": "evt-1", "status": "confirmed"}],
    )
