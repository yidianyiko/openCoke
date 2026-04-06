from unittest.mock import MagicMock


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
