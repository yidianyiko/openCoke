def test_bridge_inbound_rejects_missing_bearer_token():
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    client = app.test_client()

    response = client.post("/bridge/inbound", json={"messages": []})

    assert response.status_code == 401


def test_unbound_inbound_returns_bind_instruction(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    monkeypatch.setitem(
        app.config,
        "TEST_BRIDGE_RESPONSE",
        {
            "status": "bind_required",
            "reply": "请先绑定账号: https://coke.local/bind/bt_1",
            "bind_url": "https://coke.local/bind/bt_1",
        },
    )

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
