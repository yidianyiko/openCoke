from fastapi.testclient import TestClient

from api.app import create_app


def _gateway_config():
    return {
        "gateway": {
            "enabled": True,
            "openclaw_url": "https://openclaw.example.com",
            "openclaw_token": "token",
            "shared_secret": "secret-123",
            "group_chat": {"enabled": False},
            "account_mapping": {
                "acct-1": {
                    "character": "coke",
                    "channels": {
                        "wechat": {
                            "character_platform_id": "coke-wechat",
                        }
                    },
                }
            },
        }
    }


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_requires_bearer_token(monkeypatch):
    monkeypatch.setattr("api.app.get_config", _gateway_config)
    client = TestClient(create_app())

    response = client.post(
        "/v1/chat",
        json={
            "message_id": "msg-1",
            "channel": "wechat",
            "account_id": "acct-1",
            "sender": {"platform_id": "user-1"},
            "chat_type": "private",
            "message_type": "text",
            "content": "hello",
            "timestamp": 1742956800,
        },
    )

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_chat_validation_errors_return_400(monkeypatch):
    monkeypatch.setattr("api.app.get_config", _gateway_config)
    client = TestClient(create_app())

    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer secret-123"},
        json={},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "validation_error"
    assert body["detail"]


def test_chat_requires_non_empty_shared_secret(monkeypatch):
    monkeypatch.setattr(
        "api.app.get_config",
        lambda: {
            "gateway": {
                "enabled": True,
                "openclaw_url": "https://openclaw.example.com",
                "openclaw_token": "token",
                "shared_secret": "",
                "group_chat": {"enabled": False},
                "account_mapping": {},
            }
        },
    )
    client = TestClient(create_app())

    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer "},
        json={
            "message_id": "msg-1",
            "channel": "wechat",
            "account_id": "acct-1",
            "sender": {"platform_id": "user-1"},
            "chat_type": "private",
            "message_type": "text",
            "content": "hello",
            "timestamp": 1742956800,
        },
    )

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_chat_returns_202_and_internal_message_id(monkeypatch):
    monkeypatch.setattr("api.app.get_config", _gateway_config)
    client_app = create_app()
    client_app.state.ingest_service = type(
        "Service",
        (),
        {
            "accept": lambda self, payload: type(
                "Result",
                (),
                {
                    "request_message_id": payload.message_id,
                    "input_message_id": "507f1f77bcf86cd799439011",
                },
            )(),
        },
    )()
    client = TestClient(client_app)

    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer secret-123"},
        json={
            "message_id": "gw-001",
            "channel": "wechat",
            "account_id": "acct-1",
            "sender": {"platform_id": "user-1"},
            "chat_type": "private",
            "message_type": "text",
            "content": "hello",
            "timestamp": 1742956800,
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "request_message_id": "gw-001",
        "input_message_id": "507f1f77bcf86cd799439011",
    }


def test_chat_duplicate_returns_409(monkeypatch):
    from api.ingest import DuplicateMessageError

    monkeypatch.setattr("api.app.get_config", _gateway_config)
    client_app = create_app()

    class Service:
        def accept(self, payload):
            raise DuplicateMessageError(payload.message_id)

    client_app.state.ingest_service = Service()
    client = TestClient(client_app)

    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer secret-123"},
        json={
            "message_id": "gw-dup",
            "channel": "wechat",
            "account_id": "acct-1",
            "sender": {"platform_id": "user-1"},
            "chat_type": "private",
            "message_type": "text",
            "content": "hello",
            "timestamp": 1742956800,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"error": "duplicate", "message_id": "gw-dup"}


def test_chat_returns_404_for_unknown_routed_character(monkeypatch):
    monkeypatch.setattr("api.app.get_config", _gateway_config)
    client_app = create_app()

    class Service:
        def accept(self, payload):
            raise LookupError("character routing identity mismatch")

    client_app.state.ingest_service = Service()
    client = TestClient(client_app)

    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer secret-123"},
        json={
            "message_id": "gw-missing-character",
            "channel": "wechat",
            "account_id": "acct-1",
            "sender": {"platform_id": "user-1"},
            "chat_type": "private",
            "message_type": "text",
            "content": "hello",
            "timestamp": 1742956800,
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": "unknown_account",
        "account_id": "acct-1",
    }
