from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.api.settings_routes import create_settings_blueprint
from coke.app import create_app
from coke.config import Settings

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeSettingsService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def view_settings(self, account_id):
        self.calls.append(("view_settings", {"account_id": account_id}))
        return _view(account_id)

    def update_settings(self, account_id, **updates):
        self.calls.append(
            ("update_settings", {"account_id": account_id, "updates": updates})
        )
        return _view(
            account_id,
            default_timezone=updates.get("default_timezone", "UTC"),
            assistant_name=updates.get("assistant_name", "Coke"),
            memory_enabled=updates.get("memory_enabled", True),
        )

    def update_profile(self, account_id, **updates):
        self.calls.append(
            ("update_profile", {"account_id": account_id, "updates": updates})
        )
        return _view(account_id, nickname=updates.get("nickname"))

    def reset_agent_settings(self, account_id):
        self.calls.append(("reset_agent_settings", {"account_id": account_id}))
        return _view(account_id)


class FakeIdentityService:
    def __init__(self, account_id="acct_1") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account_id = account_id

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        return SimpleNamespace(id=self.account_id, origin="web_first")


class AuthenticatedClient:
    def __init__(self, raw_client) -> None:
        self.raw = raw_client

    def get(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.get(*args, **kwargs)

    def patch(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.patch(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.post(*args, **kwargs)


def test_view_and_update_settings_routes_use_session_account_not_body_account_id():
    client, service, identity = make_client()

    view_response = client.get("/api/settings")
    update_response = client.patch(
        "/api/settings",
        json={
            "account_id": "spoofed_account",
            "default_timezone": "Asia/Tokyo",
            "assistant_name": "Mina",
            "memory_enabled": False,
        },
    )

    assert view_response.status_code == 200
    assert view_response.get_json()["default_timezone"] == "UTC"
    assert update_response.status_code == 200
    assert update_response.get_json()["agent_settings"]["assistant_name"] == "Mina"
    assert update_response.get_json()["agent_settings"]["memory_enabled"] is False
    assert identity.calls == [
        ("current_user", {"session_token": "session_token"}),
        ("current_user", {"session_token": "session_token"}),
    ]
    assert service.calls == [
        ("view_settings", {"account_id": "acct_1"}),
        (
            "update_settings",
            {
                "account_id": "acct_1",
                "updates": {
                    "default_timezone": "Asia/Tokyo",
                    "assistant_name": "Mina",
                    "memory_enabled": False,
                },
            },
        ),
    ]


def test_profile_and_reset_routes_use_session_account():
    client, service, _identity = make_client()

    profile_response = client.patch(
        "/api/settings/profile",
        json={"account_id": "spoofed_account", "nickname": "Yuki"},
    )
    reset_response = client.post(
        "/api/settings/reset",
        json={"account_id": "spoofed_account"},
    )

    assert profile_response.status_code == 200
    assert profile_response.get_json()["user_profile"]["nickname"] == "Yuki"
    assert reset_response.status_code == 200
    assert [call[0] for call in service.calls] == [
        "update_profile",
        "reset_agent_settings",
    ]
    assert service.calls[0][1]["account_id"] == "acct_1"
    assert service.calls[1][1]["account_id"] == "acct_1"


def test_settings_route_rejects_missing_session_before_service_call():
    client, service, identity = make_client()

    response = client.get("/api/settings", headers={})

    assert response.status_code == 401
    assert response.get_json() == {
        "error": {
            "code": "unauthorized",
            "fact": {
                "type": "unauthorized",
                "reason": "missing_bearer_token",
            },
        }
    }
    assert identity.calls == []
    assert service.calls == []


def test_create_app_registers_settings_blueprint_only_with_identity_service():
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        settings_service=FakeSettingsService(),
    )
    assert (
        app.test_client()
        .get("/api/settings", headers={"Authorization": "Bearer session_token"})
        .status_code
        == 404
    )

    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        identity_access_service=FakeIdentityService(),
        settings_service=FakeSettingsService(),
    )

    response = app.test_client().get(
        "/api/settings",
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 200


def make_client(service=None, identity_service=None):
    service = service or FakeSettingsService()
    identity_service = identity_service or FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_settings_blueprint(service, identity_service))
    return AuthenticatedClient(app.test_client()), service, identity_service


def _view(
    account_id: str,
    *,
    default_timezone: str = "UTC",
    assistant_name: str = "Coke",
    memory_enabled: bool = True,
    nickname: str | None = None,
):
    return SimpleNamespace(
        account_id=account_id,
        default_timezone=default_timezone,
        agent_settings=SimpleNamespace(
            assistant_name=assistant_name,
            user_address_name=None,
            persona=None,
            background=None,
            speaking_style=None,
            extra_rules=None,
            proactive_enabled=True,
            memory_enabled=memory_enabled,
        ),
        user_profile=SimpleNamespace(
            real_name=None,
            nickname=nickname,
            description=None,
            relationship_description=None,
        ),
    )
