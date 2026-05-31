from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.api.subscription_routes import create_subscription_blueprint
from coke.app import create_app
from coke.config import Settings

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeIdentityService:
    def __init__(self, subscription_state: str = "inactive") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.subscription_state = subscription_state
        self.account = SimpleNamespace(id="acct_1", origin="messaging_first")

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        return self.account

    def get_access_status(self, account_id):
        self.calls.append(("get_access_status", {"account_id": account_id}))
        subscription_inactive = self.subscription_state != "active"
        return SimpleNamespace(
            id="access_1",
            account_id=account_id,
            email_verification_state="verified",
            subscription_state=self.subscription_state,
            suspension_state="active",
            access_allowed=not subscription_inactive,
            denial_reason="subscription_inactive" if subscription_inactive else None,
        )

    def check_access_for_inbound(self, account_id):
        self.calls.append(("check_access_for_inbound", {"account_id": account_id}))
        access_allowed = self.subscription_state == "active"
        return SimpleNamespace(
            allowed=access_allowed,
            denial_reason=None if access_allowed else "subscription_inactive",
            fact={
                "type": "account_access_denied",
                "account_id": account_id,
                "denial_reason": None if access_allowed else "subscription_inactive",
                "checkout_url": None
                if access_allowed
                else "https://checkout.example/acct_1",
            },
        )


def test_subscription_status_route_reads_account_access_without_metering_fields():
    client, service = make_client()

    response = client.get("/api/subscription/status?account_id=spoofed")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "subscription_state": "inactive",
        "access_allowed": False,
        "denial_reason": "subscription_inactive",
        "checkout_url": "https://checkout.example/acct_1",
    }
    assert service.calls == [
        ("current_user", {"session_token": "session_token"}),
        ("get_access_status", {"account_id": "acct_1"}),
        ("check_access_for_inbound", {"account_id": "acct_1"}),
    ]


def test_checkout_link_route_surfaces_existing_access_checkout_url():
    client, service = make_client()

    response = client.post("/api/subscription/checkout-link", json={"plan": "ignored"})

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "available": True,
        "checkout_url": "https://checkout.example/acct_1",
        "denial_reason": "subscription_inactive",
    }
    assert service.calls == [
        ("current_user", {"session_token": "session_token"}),
        ("check_access_for_inbound", {"account_id": "acct_1"}),
    ]


def test_checkout_link_route_does_not_create_order_when_access_is_active():
    client, service = make_client(FakeIdentityService(subscription_state="active"))

    response = client.post("/api/subscription/checkout-link")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "available": False,
        "checkout_url": None,
        "denial_reason": None,
    }
    assert service.calls == [
        ("current_user", {"session_token": "session_token"}),
        ("check_access_for_inbound", {"account_id": "acct_1"}),
    ]


def test_subscription_routes_reject_missing_session_before_service_call():
    service = FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_subscription_blueprint(service))

    response = app.test_client().get("/api/subscription/status")

    assert response.status_code == 401
    assert response.get_json() == {
        "error": {
            "code": "unauthorized",
            "fact": {"type": "unauthorized", "reason": "missing_bearer_token"},
        }
    }
    assert service.calls == []


def test_create_app_registers_subscription_blueprint_with_identity_service():
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        identity_access_service=FakeIdentityService(),
    )

    response = app.test_client().get(
        "/api/subscription/status",
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 200


def make_client(service=None):
    service = service or FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_subscription_blueprint(service))
    return AuthenticatedClient(app.test_client()), service


class AuthenticatedClient:
    def __init__(self, raw_client) -> None:
        self.raw = raw_client

    def get(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.post(*args, **kwargs)
