from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from flask import Flask

from coke.api.account_routes import create_account_blueprint
from coke.app import create_app
from coke.config import Settings
from coke.domains.identity_access.models import IdentityAccessError

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"
NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


class FakeIdentityService:
    def __init__(self, account_id: str = "acct_1") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account_id = account_id

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        return SimpleNamespace(
            id=self.account_id,
            origin="web_first",
            default_timezone="Asia/Tokyo",
            lifecycle="active",
        )

    def get_access_status(self, account_id):
        self.calls.append(("get_access_status", {"account_id": account_id}))
        return SimpleNamespace(
            id="access_1",
            account_id=account_id,
            email_verification_state="verified",
            subscription_state="active",
            suspension_state="active",
            access_allowed=True,
            denial_reason=None,
        )

    def get_activation(self, account_id):
        self.calls.append(("get_activation", {"account_id": account_id}))
        return SimpleNamespace(
            id="activation_1",
            account_id=account_id,
            first_inbound_received_at=NOW,
            activation_completed_at=None,
            first_guidance_sent_at=None,
        )


def test_current_user_route_uses_session_token_and_returns_account_identity():
    client, service = make_client()

    response = client.get("/api/account/current-user")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "origin": "web_first",
        "default_timezone": "Asia/Tokyo",
        "lifecycle": "active",
    }
    assert service.calls == [("current_user", {"session_token": "session_token"})]


def test_access_status_route_returns_full_access_gate_projection():
    client, service = make_client()

    response = client.get("/api/account/access-status")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "email_verification_state": "verified",
        "subscription_state": "active",
        "suspension_state": "active",
        "access_allowed": True,
        "denial_reason": None,
    }
    assert service.calls == [
        ("current_user", {"session_token": "session_token"}),
        ("get_access_status", {"account_id": "acct_1"}),
    ]


def test_activation_route_returns_activation_projection_without_body_account_id():
    client, service = make_client()

    response = client.get("/api/account/activation?account_id=spoofed")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "first_inbound_received_at": "2026-05-31T12:00:00+00:00",
        "activation_completed_at": None,
        "first_guidance_sent_at": None,
    }
    assert service.calls == [
        ("current_user", {"session_token": "session_token"}),
        ("get_activation", {"account_id": "acct_1"}),
    ]


def test_account_routes_reject_missing_session_before_service_call():
    service = FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_account_blueprint(service))

    response = app.test_client().get("/api/account/access-status")

    assert response.status_code == 401
    assert response.get_json() == {
        "error": {
            "code": "unauthorized",
            "fact": {"type": "unauthorized", "reason": "missing_bearer_token"},
        }
    }
    assert service.calls == []


def test_create_app_registers_account_blueprint_with_identity_service():
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        identity_access_service=FakeIdentityService(),
    )

    response = app.test_client().get(
        "/api/account/current-user",
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 200


def make_client(service=None):
    service = service or FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_account_blueprint(service))
    return AuthenticatedClient(app.test_client()), service


class AuthenticatedClient:
    def __init__(self, raw_client) -> None:
        self.raw = raw_client

    def get(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.get(*args, **kwargs)
