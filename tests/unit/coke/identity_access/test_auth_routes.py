from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.api.auth_routes import create_auth_blueprint
from coke.api.claim_routes import create_claim_blueprint
from coke.app import create_app
from coke.config import Settings
from coke.domains.identity_access.models import IdentityAccessError


class FakeObject(SimpleNamespace):
    pass


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account = FakeObject(id="acct_1", origin="web_first")
        self.session = FakeObject(
            id="sess_1", account_id="acct_1", token="session_token"
        )

    def register_web_account(
        self, email, password, display_name=None, default_timezone="UTC"
    ):
        self.calls.append(
            (
                "register_web_account",
                {
                    "email": email,
                    "password": password,
                    "display_name": display_name,
                    "default_timezone": default_timezone,
                },
            )
        )
        return FakeObject(
            id="registration_result",
            account=self.account,
            session=self.session,
            email_verification=FakeObject(id="artifact_1"),
        )

    def login(self, email, password):
        self.calls.append(("login", {"email": email, "password": password}))
        return FakeObject(id="login_result", account=self.account, session=self.session)

    def verify_email(self, token):
        self.calls.append(("verify_email", {"token": token}))
        return FakeObject(id="credential_1", account_id="acct_1", email="a@example.com")

    def verify_email_and_create_session(self, token):
        self.calls.append(("verify_email_and_create_session", {"token": token}))
        return FakeObject(
            account_id="acct_1",
            email="a@example.com",
            session=self.session,
        )

    def issue_password_reset(self, email):
        self.calls.append(("issue_password_reset", {"email": email}))
        return FakeObject(code="reset_token", artifact=FakeObject(id="artifact_2"))

    def resend_email_verification(self, email):
        self.calls.append(("resend_email_verification", {"email": email}))
        return FakeObject(code="verify_token", artifact=FakeObject(id="artifact_1"))

    def reset_password(self, token, password):
        self.calls.append(
            (
                "reset_password",
                {
                    "token": token,
                    "password": password,
                },
            )
        )
        return FakeObject(id="credential_1", account_id="acct_1", email="a@example.com")

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        return self.account

    def get_access_status(self, account_id):
        self.calls.append(("get_access_status", {"account_id": account_id}))
        return FakeObject(
            id="access_1",
            account_id=account_id,
            access_allowed=True,
            denial_reason=None,
        )

    def redeem_login_url(self, token, browser_session):
        self.calls.append(
            (
                "redeem_login_url",
                {
                    "token": token,
                    "browser_session": browser_session,
                },
            )
        )
        return FakeObject(
            account_id="acct_1",
            session=self.session,
            continuation={"next": "/channels"},
        )

    def issue_web_claim_code(self, browser_session, continuation=None):
        self.calls.append(
            (
                "issue_web_claim_code",
                {
                    "browser_session": browser_session,
                    "continuation": continuation or {},
                },
            )
        )
        return FakeObject(code="claim_code", artifact=FakeObject(id="artifact_3"))

    def send_claim_email(self, token, email):
        self.calls.append(("send_claim_email", {"token": token, "email": email}))
        return FakeObject(code=token, artifact=FakeObject(id="artifact_5"))

    def get_claim_code_status(self, code, browser_session):
        self.calls.append(
            (
                "get_claim_code_status",
                {
                    "code": code,
                    "browser_session": browser_session,
                },
            )
        )
        return FakeObject(
            found=True,
            consumed=False,
            target_account_id=None,
            delivery_state="pending",
        )

    def redeem_claim_code_from_channel(self, code, provider_type, provider_subject):
        self.calls.append(
            (
                "redeem_claim_code_from_channel",
                {
                    "code": code,
                    "provider_type": provider_type,
                    "provider_subject": provider_subject,
                },
            )
        )
        return FakeObject(account_id="acct_1", continuation={"friend_link_id": "fl_1"})

    def complete_web_claim_from_browser(self, code, browser_session):
        self.calls.append(
            (
                "complete_web_claim_from_browser",
                {
                    "code": code,
                    "browser_session": browser_session,
                },
            )
        )
        return FakeObject(
            account_id="acct_1",
            session=self.session,
            continuation={"friend_link_id": "fl_1"},
        )

    def issue_pairing_code(self, account_id):
        self.calls.append(("issue_pairing_code", {"account_id": account_id}))
        return FakeObject(code="pairing_code", artifact=FakeObject(id="artifact_4"))

    def resolve_or_create_channel_identity(
        self, provider_type, provider_subject, pairing_code=None
    ):
        self.calls.append(
            (
                "resolve_or_create_channel_identity",
                {
                    "provider_type": provider_type,
                    "provider_subject": provider_subject,
                    "pairing_code": pairing_code,
                },
            )
        )
        return FakeObject(
            account=self.account,
            channel_identity=FakeObject(id="ci_1", account_id="acct_1"),
        )


class ErrorService(FakeService):
    def login(self, email, password):
        raise IdentityAccessError("invalid_credentials")

    def redeem_claim_code_from_channel(self, code, provider_type, provider_subject):
        raise IdentityAccessError("unknown_channel_identity")

    def issue_pairing_code(self, account_id):
        raise IdentityAccessError("pairing_requires_web_first_account")


class AccessDeniedService(FakeService):
    def issue_pairing_code(self, account_id):
        raise IdentityAccessError(
            "access_denied",
            fact={
                "type": "account_access_denied",
                "account_id": account_id,
                "denial_reason": "email_verification_required",
                "checkout_url": None,
            },
        )


class UnknownEmailService(FakeService):
    def resend_email_verification(self, email):
        self.calls.append(("resend_email_verification", {"email": email}))
        raise IdentityAccessError("unknown_email")


class ClaimEmailConflictService(FakeService):
    def send_claim_email(self, token, email):
        self.calls.append(("send_claim_email", {"token": token, "email": email}))
        raise IdentityAccessError("email_already_registered")


class ClaimEmailInvalidTokenService(FakeService):
    def send_claim_email(self, token, email):
        self.calls.append(("send_claim_email", {"token": token, "email": email}))
        raise IdentityAccessError("artifact_expired")


class PairingRedemptionAccessDeniedService(FakeService):
    def resolve_or_create_channel_identity(
        self, provider_type, provider_subject, pairing_code=None
    ):
        raise IdentityAccessError(
            "access_denied",
            fact={
                "type": "account_access_denied",
                "account_id": "acct_1",
                "denial_reason": "subscription_inactive",
                "checkout_url": None,
            },
        )


class PairingRedemptionWriteConflictService(FakeService):
    def resolve_or_create_channel_identity(
        self, provider_type, provider_subject, pairing_code=None
    ):
        raise IdentityAccessError(
            "channel_identity_write_conflict",
            fact={
                "type": "channel_identity_write_conflict",
                "provider_type": provider_type,
            },
        )


def make_client(service=None):
    service = service or FakeService()
    app = Flask(__name__)
    app.register_blueprint(create_auth_blueprint(service))
    app.register_blueprint(create_claim_blueprint(service))
    return app.test_client(), service


def make_factory_client(service=None):
    service = service or FakeService()
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            app_env="test",
        ),
        identity_access_service=service,
    )
    return app.test_client(), service


def test_create_app_registers_auth_and_claim_routes_with_identity_service():
    client, service = make_factory_client()

    auth_response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "hash_1"},
    )
    claim_response = client.post(
        "/api/claim/code",
        json={"browser_session": "browser_1", "continuation": {"next": "/channels"}},
    )

    assert auth_response.status_code == 200
    assert auth_response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
    }
    assert claim_response.status_code == 201
    assert claim_response.get_json() == {
        "code": "claim_code",
        "artifact_id": "artifact_3",
    }
    assert service.calls == [
        ("login", {"email": "a@example.com", "password": "hash_1"}),
        (
            "issue_web_claim_code",
            {
                "browser_session": "browser_1",
                "continuation": {"next": "/channels"},
            },
        ),
    ]


def test_register_route_calls_service_and_returns_json():
    client, service = make_client()

    response = client.post(
        "/api/auth/register",
        json={
            "email": "a@example.com",
            "password": "hash_1",
            "display_name": "Alice",
            "default_timezone": "Asia/Tokyo",
        },
    )

    assert response.status_code == 201
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "email_verification_artifact_id": "artifact_1",
    }
    assert service.calls[-1] == (
        "register_web_account",
        {
            "email": "a@example.com",
            "password": "hash_1",
            "display_name": "Alice",
            "default_timezone": "Asia/Tokyo",
        },
    )


def test_register_route_rejects_missing_display_name_before_service_call():
    client, service = make_client()

    response = client.post(
        "/api/auth/register",
        json={
            "email": "a@example.com",
            "password": "hash_1",
            "default_timezone": "Asia/Tokyo",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": "display_name",
                "reason": "required_field_missing",
            },
        }
    }
    assert service.calls == []


def test_login_and_current_user_routes_call_service():
    client, service = make_client()

    login_response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "hash_1"},
    )
    current_response = client.get(
        "/api/auth/current-user",
        headers={"Authorization": "Bearer session_token"},
    )

    assert login_response.status_code == 200
    assert login_response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
    }
    assert current_response.status_code == 200
    assert current_response.get_json() == {
        "account_id": "acct_1",
        "origin": "web_first",
    }
    assert service.calls[-1] == ("current_user", {"session_token": "session_token"})


def test_access_status_route_calls_service():
    client, service = make_client()

    response = client.get(
        "/api/auth/access-status",
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "access_allowed": True,
        "denial_reason": None,
    }
    assert service.calls[-2:] == [
        ("current_user", {"session_token": "session_token"}),
        ("get_access_status", {"account_id": "acct_1"}),
    ]


def test_access_status_route_rejects_missing_session_before_service_call():
    client, service = make_client()

    response = client.get("/api/auth/access-status")

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
    assert service.calls == []


def test_verification_and_password_reset_routes_call_service():
    client, service = make_client()

    verify_response = client.post(
        "/api/auth/email-verification/verify", json={"token": "verify_token"}
    )
    request_response = client.post(
        "/api/auth/password-reset/request", json={"email": "a@example.com"}
    )
    complete_response = client.post(
        "/api/auth/password-reset/complete",
        json={"token": "reset_token", "password": "hash_2"},
    )

    assert verify_response.status_code == 200
    assert verify_response.get_json() == {
        "account_id": "acct_1",
        "email": "a@example.com",
        "session_token": "session_token",
    }
    assert request_response.status_code == 202
    assert complete_response.status_code == 200
    assert service.calls[-3:] == [
        ("verify_email_and_create_session", {"token": "verify_token"}),
        ("issue_password_reset", {"email": "a@example.com"}),
        ("reset_password", {"token": "reset_token", "password": "hash_2"}),
    ]


def test_resend_email_verification_route_calls_service_and_returns_accepted():
    client, service = make_client()

    response = client.post(
        "/api/auth/email-verification/resend",
        json={"email": "a@example.com"},
    )

    assert response.status_code == 202
    assert response.get_json() == {"accepted": True}
    assert service.calls[-1] == (
        "resend_email_verification",
        {"email": "a@example.com"},
    )


def test_resend_email_verification_route_hides_unknown_email():
    client, service = make_client(UnknownEmailService())

    response = client.post(
        "/api/auth/email-verification/resend",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 202
    assert response.get_json() == {"accepted": True}
    assert service.calls[-1] == (
        "resend_email_verification",
        {"email": "missing@example.com"},
    )


def test_login_url_landing_calls_service():
    client, service = make_client()

    response = client.post(
        "/api/auth/login-url/redeem",
        json={"token": "login_token", "browser_session": "browser_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "continuation": {"next": "/channels"},
    }
    assert service.calls[-1] == (
        "redeem_login_url",
        {
            "token": "login_token",
            "browser_session": "browser_1",
        },
    )


def test_claim_login_url_redeem_route_uses_canonical_claim_namespace():
    client, service = make_client()

    response = client.post(
        "/api/claim/login-url/redeem",
        json={"token": "login_token", "browser_session": "browser_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "continuation": {"next": "/channels"},
    }
    assert service.calls[-1] == (
        "redeem_login_url",
        {
            "token": "login_token",
            "browser_session": "browser_1",
        },
    )


def test_claim_code_issue_and_redeem_routes_call_service():
    client, service = make_client()

    issue_response = client.post(
        "/api/claim/code",
        json={
            "browser_session": "browser_1",
            "continuation": {"friend_link_id": "fl_1"},
        },
    )
    redeem_response = client.post(
        "/api/claim/code/redeem",
        json={
            "code": "claim_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert issue_response.status_code == 201
    assert issue_response.get_json() == {
        "code": "claim_code",
        "artifact_id": "artifact_3",
    }
    assert redeem_response.status_code == 200
    assert redeem_response.get_json() == {
        "account_id": "acct_1",
        "continuation": {"friend_link_id": "fl_1"},
    }
    assert "session_token" not in redeem_response.get_json()


def test_claim_email_route_sends_existing_login_url_token_to_email():
    client, service = make_client()

    response = client.post(
        "/api/claim/email",
        json={"entry_token": "login_token", "email": "claimant@example.com"},
    )

    assert response.status_code == 202
    assert response.get_json() == {"accepted": True}
    assert service.calls[-1] == (
        "send_claim_email",
        {"token": "login_token", "email": "claimant@example.com"},
    )


def test_claim_email_route_returns_existing_email_error():
    client, service = make_client(ClaimEmailConflictService())

    response = client.post(
        "/api/claim/email",
        json={"entry_token": "login_token", "email": "a@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "email_already_registered"}}
    assert service.calls[-1] == (
        "send_claim_email",
        {"token": "login_token", "email": "a@example.com"},
    )


def test_claim_email_route_returns_invalid_token_error():
    client, service = make_client(ClaimEmailInvalidTokenService())

    response = client.post(
        "/api/claim/email",
        json={"entry_token": "expired_token", "email": "claimant@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "artifact_expired"}}
    assert service.calls[-1] == (
        "send_claim_email",
        {"token": "expired_token", "email": "claimant@example.com"},
    )


def test_claim_code_poll_route_calls_service():
    client, service = make_client()

    response = client.get("/api/claim/code/claim_code/status?browser_session=browser_1")

    assert response.status_code == 200
    assert response.get_json() == {
        "found": True,
        "consumed": False,
        "target_account_id": None,
        "delivery_state": "pending",
    }
    assert service.calls[-1] == (
        "get_claim_code_status",
        {
            "code": "claim_code",
            "browser_session": "browser_1",
        },
    )


def test_claim_code_browser_complete_route_returns_session_to_original_browser():
    client, service = make_client()

    response = client.post(
        "/api/claim/code/complete",
        json={"code": "claim_code", "browser_session": "browser_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "continuation": {"friend_link_id": "fl_1"},
    }
    assert service.calls[-1] == (
        "complete_web_claim_from_browser",
        {
            "code": "claim_code",
            "browser_session": "browser_1",
        },
    )


def test_auth_route_errors_are_json_facts():
    client, _service = make_client(ErrorService())

    response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "wrong"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "invalid_credentials"}}


def test_auth_route_missing_json_body_returns_invalid_request_fact():
    client, service = make_client()

    response = client.post("/api/auth/login")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        }
    }
    assert service.calls == []


def test_auth_route_missing_required_json_field_returns_invalid_request_fact():
    client, service = make_client()

    response = client.post("/api/auth/login", json={"email": "a@example.com"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": "password",
                "reason": "required_field_missing",
            },
        }
    }
    assert service.calls == []


def test_claim_route_errors_are_json_facts():
    client, _service = make_client(ErrorService())

    response = client.post(
        "/api/claim/code/redeem",
        json={
            "code": "claim_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "unknown_channel_identity"}}


def test_claim_route_missing_json_body_returns_invalid_request_fact():
    client, service = make_client()

    response = client.post("/api/claim/code")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        }
    }
    assert service.calls == []


def test_claim_route_missing_required_json_field_returns_invalid_request_fact():
    client, service = make_client()

    response = client.post("/api/claim/code", json={"continuation": {}})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": "browser_session",
                "reason": "required_field_missing",
            },
        }
    }
    assert service.calls == []


def test_claim_poll_route_missing_browser_session_query_returns_invalid_request_fact():
    client, service = make_client()

    response = client.get("/api/claim/code/claim_code/status")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "query",
                "field": "browser_session",
                "reason": "required_field_missing",
            },
        }
    }
    assert service.calls == []


def test_pairing_code_issue_route_returns_json_error_when_service_rejects_origin():
    client, _service = make_client(ErrorService())

    response = client.post(
        "/api/claim/pairing-code",
        json={"account_id": "spoofed_account"},
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {"code": "pairing_requires_web_first_account"}
    }


def test_pairing_code_issue_route_returns_access_denied_fact():
    client, _service = make_client(AccessDeniedService())

    response = client.post(
        "/api/claim/pairing-code",
        json={"account_id": "spoofed_account"},
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "access_denied",
            "fact": {
                "type": "account_access_denied",
                "account_id": "acct_1",
                "denial_reason": "email_verification_required",
                "checkout_url": None,
            },
        }
    }


def test_pairing_code_redeem_route_returns_access_denied_fact():
    client, _service = make_client(PairingRedemptionAccessDeniedService())

    response = client.post(
        "/api/claim/pairing-code/redeem",
        json={
            "pairing_code": "pairing_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "access_denied",
            "fact": {
                "type": "account_access_denied",
                "account_id": "acct_1",
                "denial_reason": "subscription_inactive",
                "checkout_url": None,
            },
        }
    }


def test_pairing_code_redeem_route_returns_write_conflict_json_fact():
    client, _service = make_client(PairingRedemptionWriteConflictService())

    response = client.post(
        "/api/claim/pairing-code/redeem",
        json={
            "pairing_code": "pairing_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "channel_identity_write_conflict",
            "fact": {
                "type": "channel_identity_write_conflict",
                "provider_type": "whatsapp_evolution",
            },
        }
    }


def test_pairing_code_issue_and_redeem_routes_call_service():
    client, service = make_client()

    issue_response = client.post(
        "/api/claim/pairing-code",
        json={"account_id": "spoofed_account"},
        headers={"Authorization": "Bearer session_token"},
    )
    redeem_response = client.post(
        "/api/claim/pairing-code/redeem",
        json={
            "pairing_code": "pairing_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert issue_response.status_code == 201
    assert issue_response.get_json() == {
        "code": "pairing_code",
        "artifact_id": "artifact_4",
    }
    assert redeem_response.status_code == 200
    assert redeem_response.get_json() == {
        "account_id": "acct_1",
        "channel_identity_id": "ci_1",
    }
    assert service.calls[:2] == [
        ("current_user", {"session_token": "session_token"}),
        ("issue_pairing_code", {"account_id": "acct_1"}),
    ]
    assert service.calls[-1] == (
        "resolve_or_create_channel_identity",
        {
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
            "pairing_code": "pairing_code",
        },
    )
