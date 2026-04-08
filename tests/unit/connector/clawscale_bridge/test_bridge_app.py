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


def test_build_user_bind_service_wires_gateway_identity_client(monkeypatch):
    import connector.clawscale_bridge.app as bridge_app

    gateway_identity_client = MagicMock()
    captured = {}

    monkeypatch.setattr(
        bridge_app,
        "_build_gateway_identity_client",
        lambda: gateway_identity_client,
        raising=False,
    )
    monkeypatch.setattr(
        bridge_app, "WechatBindSessionDAO", lambda **kwargs: MagicMock()
    )
    monkeypatch.setattr(
        bridge_app, "ExternalIdentityDAO", lambda **kwargs: MagicMock()
    )

    class FakeBindSessionService:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(bridge_app, "WechatBindSessionService", FakeBindSessionService)

    bridge_app._build_user_bind_service()

    assert captured["gateway_identity_client"] is gateway_identity_client


def test_bridge_inbound_rejects_missing_bearer_token():
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    client = app.test_client()

    response = client.post("/bridge/inbound", json={"messages": []})

    assert response.status_code == 401


def test_unbound_inbound_returns_bind_instruction(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    gateway = MagicMock()
    gateway.handle_inbound.return_value = {
        "status": "bind_required",
        "reply": "请先绑定账号: https://coke.local/bind/bt_1",
        "bind_url": "https://coke.local/bind/bt_1",
    }
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", gateway)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {"tenantId": "ten_1"},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("请先绑定账号")


def test_bound_inbound_request_returns_coke_reply(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    gateway = MagicMock()
    gateway.handle_inbound.return_value = {"reply": "你好，我在", "status": "ok"}
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", gateway)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "在吗"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "externalId": "wxid_123",
                "sender": "Alice",
                "platform": "wechat_personal",
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "reply": "你好，我在"}


def test_user_bind_session_requires_user_bearer_token():
    app, client = _build_user_client()

    response = client.post("/user/wechat-bind/session")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False


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
    app.config["USER_PROVISION_SERVICE"] = MagicMock()

    response = client.post(
        "/user/register",
        json={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 201
    app.config["USER_PROVISION_SERVICE"].ensure_user.assert_called_once_with(
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


def test_user_bind_session_returns_pending_payload():
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
    app.config["USER_BIND_SERVICE"] = type(
        "Bind",
        (),
        {
            "create_or_reuse_session": lambda self, account_id, now_ts: {
                "status": "pending",
                "connect_url": "https://wx.example.com/entry?bind_token=ctx_123",
                "expires_at": 1775472600,
            }
        },
    )()

    response = client.post(
        "/user/wechat-bind/session",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "pending"
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:4040"


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


def test_user_bind_entry_renders_pending_session_page():
    app, client = _build_user_client()
    app.config["USER_BIND_SERVICE"] = type(
        "Bind",
        (),
        {
            "get_entry_page_context": lambda self, bind_token, now_ts: {
                "status": "pending",
                "bind_code": "COKE-184263",
                "public_connect_url": None,
                "expires_at": 1775472600,
            }
        },
    )()

    response = client.get("/user/wechat-bind/entry/ctx_bind_123")

    assert response.status_code == 200
    assert "COKE-184263" in response.get_data(as_text=True)


def test_user_bind_entry_returns_gone_when_session_missing():
    app, client = _build_user_client()
    app.config["USER_BIND_SERVICE"] = type(
        "Bind",
        (),
        {
            "get_entry_page_context": lambda self, bind_token, now_ts: {
                "status": "expired",
            }
        },
    )()

    response = client.get("/user/wechat-bind/entry/ctx_missing")

    assert response.status_code == 410
    assert "已过期" in response.get_data(as_text=True)


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


def test_user_bind_status_requires_user_bearer_token():
    app, client = _build_user_client()

    response = client.get("/user/wechat-bind/status")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False


def test_user_bind_status_returns_bound_payload():
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
    app.config["USER_BIND_SERVICE"] = type(
        "Bind",
        (),
        {
            "get_status": lambda self, account_id, now_ts: {
                "status": "bound",
                "masked_identity": "wxid_***8e0a",
            }
        },
    )()

    response = client.get(
        "/user/wechat-bind/status",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "status": "bound",
        "masked_identity": "wxid_***8e0a",
    }
