import pytest
from unittest.mock import MagicMock


def _build_user_client():
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    app.config["COKE_WEB_ALLOWED_ORIGIN"] = "http://127.0.0.1:4040"
    return app, app.test_client()


def test_create_app_uses_configured_bridge_api_key_in_non_testing_mode(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    monkeypatch.setitem(
        bridge_app.CONF["clawscale_bridge"], "api_key", "local-bridge-key"
    )
    monkeypatch.setattr(
        bridge_app, "_build_default_bridge_gateway", lambda: MagicMock()
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
    monkeypatch.setattr(bridge_app, "_build_user_auth_service", lambda: MagicMock())
    monkeypatch.setattr(
        bridge_app, "_build_personal_wechat_channel_service", lambda: MagicMock()
    )
    monkeypatch.setattr(
        bridge_app, "_build_gateway_user_provision_client", lambda: MagicMock()
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
    reply_waiter.wait_for_reply.assert_called_once_with(
        "in_evt_1001", sync_reply_token="sync_tok_1"
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


def test_user_bind_routes_are_removed():
    app, client = _build_user_client()

    assert client.post("/user/wechat-bind/session").status_code == 404
    assert client.get("/user/wechat-bind/status").status_code == 404
    assert client.get("/user/wechat-bind/entry/ctx_bind_123").status_code == 404


def test_user_wechat_channel_disconnect_requires_user_bearer_token():
    app, client = _build_user_client()

    response = client.post("/user/wechat-channel/disconnect")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False


def test_user_wechat_channel_archive_requires_user_bearer_token():
    app, client = _build_user_client()

    response = client.delete("/user/wechat-channel")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False


def test_user_register_rejects_malformed_json_body():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/register",
        data="{",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


def test_user_register_rejects_missing_required_fields():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/register",
        json={"display_name": "Alice", "email": "alice@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "missing_required_fields"}


def test_user_register_rejects_null_required_field_values():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/register",
        json={
            "display_name": "Alice",
            "email": None,
            "password": "correct horse battery staple",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


def test_user_register_rejects_empty_string_required_field_values():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/register",
        json={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


def test_user_register_provisions_gateway_user_after_auth_record_creation():
    app, client = _build_user_client()
    user_auth_service = MagicMock()
    user_auth_service.register.return_value = {
        "token": "token",
        "user": {
            "id": "user_1",
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    }
    app.config["USER_AUTH_SERVICE"] = user_auth_service
    provision_service = MagicMock()
    provision_service.ensure_user.return_value = {
        "tenant_id": "ten_1",
        "clawscale_user_id": "csu_1",
        "ready": True,
    }
    app.config["USER_PROVISION_SERVICE"] = provision_service

    response = client.post(
        "/user/register",
        json={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 201
    provision_service.ensure_user.assert_called_once_with(
        account_id="user_1",
        display_name="Alice",
    )


def test_user_register_rolls_back_created_user_when_gateway_provision_fails():
    from connector.clawscale_bridge.gateway_user_provision_client import (
        GatewayUserProvisionClientError,
    )

    app, client = _build_user_client()
    user_auth_service = MagicMock()
    user_auth_service.register.return_value = {
        "token": "token",
        "user": {
            "id": "user_1",
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    }
    user_auth_service.user_dao.delete_user.return_value = True
    provision_service = MagicMock()
    provision_service.ensure_user.side_effect = GatewayUserProvisionClientError(
        "gateway_user_provision_request_failed"
    )
    app.config["USER_AUTH_SERVICE"] = user_auth_service
    app.config["USER_PROVISION_SERVICE"] = provision_service

    response = client.post(
        "/user/register",
        json={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 502
    assert response.get_json() == {
        "ok": False,
        "error": "gateway_user_provision_request_failed",
    }
    user_auth_service.user_dao.delete_user.assert_called_once_with("user_1")


def test_user_login_rejects_malformed_json_body():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/login",
        data="{",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


def test_user_login_rejects_missing_required_fields():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/login",
        json={"email": "alice@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "missing_required_fields"}


def test_user_login_rejects_null_required_field_values():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/login",
        json={"email": None, "password": "correct-password"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


def test_user_login_rejects_empty_string_required_field_values():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.post(
        "/user/login",
        json={"email": "alice@example.com", "password": ""},
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


def test_user_login_provisions_gateway_user_before_returning_token():
    app, client = _build_user_client()
    auth_service = MagicMock()
    auth_service.login.return_value = (
        True,
        {
            "token": "token",
            "user": {
                "id": "user_1",
                "email": "alice@example.com",
                "display_name": "Alice",
            },
        },
    )
    provision_service = MagicMock()
    provision_service.ensure_user.return_value = {
        "tenant_id": "ten_1",
        "clawscale_user_id": "csu_1",
        "ready": True,
    }
    app.config["USER_AUTH_SERVICE"] = auth_service
    app.config["USER_PROVISION_SERVICE"] = provision_service

    response = client.post(
        "/user/login",
        json={"email": "alice@example.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    provision_service.ensure_user.assert_called_once_with(
        account_id="user_1",
        display_name="Alice",
    )


def test_user_register_rolls_back_created_user_when_gateway_provision_not_ready():
    app, client = _build_user_client()
    user_auth_service = MagicMock()
    user_auth_service.register.return_value = {
        "token": "token",
        "user": {
            "id": "user_1",
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    }
    user_auth_service.user_dao.delete_user.return_value = True
    provision_service = MagicMock()
    provision_service.ensure_user.return_value = {
        "tenant_id": "ten_1",
        "clawscale_user_id": "csu_1",
        "ready": False,
    }
    app.config["USER_AUTH_SERVICE"] = user_auth_service
    app.config["USER_PROVISION_SERVICE"] = provision_service

    response = client.post(
        "/user/register",
        json={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 502
    assert response.get_json() == {
        "ok": False,
        "error": "gateway_user_provision_not_ready",
    }
    user_auth_service.user_dao.delete_user.assert_called_once_with("user_1")


def test_user_login_rejects_when_gateway_provision_is_not_ready():
    app, client = _build_user_client()
    auth_service = MagicMock()
    auth_service.login.return_value = (
        True,
        {
            "token": "token",
            "user": {
                "id": "user_1",
                "email": "alice@example.com",
                "display_name": "Alice",
            },
        },
    )
    provision_service = MagicMock()
    provision_service.ensure_user.return_value = {
        "tenant_id": "ten_1",
        "clawscale_user_id": "csu_1",
        "ready": False,
    }
    app.config["USER_AUTH_SERVICE"] = auth_service
    app.config["USER_PROVISION_SERVICE"] = provision_service

    response = client.post(
        "/user/login",
        json={"email": "alice@example.com", "password": "correct-password"},
    )

    assert response.status_code == 502
    assert response.get_json() == {
        "ok": False,
        "error": "gateway_user_provision_not_ready",
    }


def test_user_wechat_channel_connect_returns_pending_payload_with_connect_url():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = type(
        "Auth",
        (),
        {
            "verify_token": lambda self, token: {
                "_id": "user_1",
                "email": "alice@example.com",
            }
        },
    )()
    app.config["USER_PERSONAL_CHANNEL_SERVICE"] = type(
        "Channel",
        (),
        {
            "start_connect": lambda self, account_id: {
                "channel_id": "ch_1",
                "status": "pending",
                "qr": "data:image/png;base64,abc",
                "qr_url": "https://liteapp.weixin.qq.com/q/demo",
                "connect_url": "https://liteapp.weixin.qq.com/q/demo",
            }
        },
    )()

    response = client.post(
        "/user/wechat-channel/connect",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "pending"
    assert data["connect_url"] == "https://liteapp.weixin.qq.com/q/demo"
    assert data["qr_url"] == "https://liteapp.weixin.qq.com/q/demo"


def test_user_wechat_channel_disconnect_returns_disconnected_payload():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = type(
        "Auth",
        (),
        {
            "verify_token": lambda self, token: {
                "_id": "user_1",
                "email": "alice@example.com",
            }
        },
    )()
    channel_service = MagicMock()
    channel_service.disconnect_channel.return_value = {
        "channel_id": "ch_1",
        "status": "disconnected",
    }
    app.config["USER_PERSONAL_CHANNEL_SERVICE"] = channel_service

    response = client.post(
        "/user/wechat-channel/disconnect",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "channel_id": "ch_1",
        "status": "disconnected",
    }
    channel_service.disconnect_channel.assert_called_once_with(account_id="user_1")


def test_user_wechat_channel_archive_returns_archived_payload():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = type(
        "Auth",
        (),
        {
            "verify_token": lambda self, token: {
                "_id": "user_1",
                "email": "alice@example.com",
            }
        },
    )()
    channel_service = MagicMock()
    channel_service.archive_channel.return_value = {
        "channel_id": "ch_1",
        "status": "archived",
    }
    app.config["USER_PERSONAL_CHANNEL_SERVICE"] = channel_service

    response = client.delete(
        "/user/wechat-channel",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "channel_id": "ch_1",
        "status": "archived",
    }
    channel_service.archive_channel.assert_called_once_with(account_id="user_1")


def test_user_register_accepts_localhost_loopback_alias_for_cors():
    app, client = _build_user_client()
    app.config["USER_AUTH_SERVICE"] = MagicMock()

    response = client.options(
        "/user/register",
        headers={
            "Origin": "http://localhost:4040",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:4040"
