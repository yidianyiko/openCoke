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
