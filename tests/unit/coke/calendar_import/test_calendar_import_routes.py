from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from flask import Flask

from coke.api.calendar_import_routes import create_calendar_import_blueprint
from coke.app import create_app
from coke.config import Settings
from coke.domains.calendar_import.models import CalendarImportError

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeCalendarImportService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def import_google_calendar(
        self,
        account_id,
        auth_handle,
        provider_account_id,
        visible_start,
        visible_end,
        captured_timezone,
        auth_artifact_id=None,
    ):
        self.calls.append(
            (
                "import_google_calendar",
                {
                    "account_id": account_id,
                    "auth_handle": auth_handle,
                    "provider_account_id": provider_account_id,
                    "visible_start": visible_start,
                    "visible_end": visible_end,
                    "captured_timezone": captured_timezone,
                    "auth_artifact_id": auth_artifact_id,
                },
            )
        )
        return SimpleNamespace(
            run_id="run_1",
            imported_count=1,
            skipped_count=0,
            downgraded_count=0,
            failed_count=0,
            items=[
                SimpleNamespace(
                    id="item_1",
                    provider_calendar_id="primary",
                    source_event_id="event_1",
                    recurrence_instance_key="event_1",
                    status="imported",
                    reason=None,
                    source_metadata={"title": "Team sync"},
                    reminder_id="reminder_1",
                )
            ],
            downgraded_items=[],
            failed_items=[],
        )

    def stop_authorization(self, account_id, auth_handle):
        self.calls.append(
            (
                "stop_authorization",
                {"account_id": account_id, "auth_handle": auth_handle},
            )
        )
        return SimpleNamespace(
            account_id=account_id, auth_handle=auth_handle, state="stopped"
        )

    def revoke_authorization(self, account_id, auth_handle):
        self.calls.append(
            (
                "revoke_authorization",
                {"account_id": account_id, "auth_handle": auth_handle},
            )
        )
        return SimpleNamespace(
            account_id=account_id, auth_handle=auth_handle, state="revoked"
        )


class ErrorService(FakeCalendarImportService):
    def stop_authorization(self, account_id, auth_handle):
        raise CalendarImportError(
            "calendar_authorization_not_found",
            fact={"type": "calendar_authorization_not_found"},
        )


class AccessDeniedImportService(FakeCalendarImportService):
    def import_google_calendar(self, **kwargs):
        raise CalendarImportError(
            "access_denied",
            fact={
                "type": "account_access_denied",
                "account_id": kwargs["account_id"],
                "denial_reason": "subscription_inactive",
                "checkout_url": None,
            },
        )


class FakeIdentityService:
    def __init__(self, account_id="acct_1") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account_id = account_id

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        if session_token != "session_token":
            raise AssertionError(f"unexpected session token: {session_token}")
        return SimpleNamespace(id=self.account_id, origin="web_first")


class AuthenticatedClient:
    def __init__(self, raw_client) -> None:
        self.raw = raw_client

    def get(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.post(*args, **kwargs)


def make_client(service=None, identity_service=None):
    service = service or FakeCalendarImportService()
    identity_service = identity_service or FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_calendar_import_blueprint(service, identity_service))
    return AuthenticatedClient(app.test_client()), service, identity_service


def test_import_route_is_a_thin_service_adapter():
    client, service, identity = make_client()

    response = client.post(
        "/api/calendar-import/google/import",
        json={
            "account_id": "spoofed_account",
            "auth_handle": "google-oauth-token",
            "provider_account_id": "google-user",
            "visible_start": "2026-05-30T12:00:00+00:00",
            "visible_end": "2026-06-30T12:00:00+00:00",
            "captured_timezone": "UTC",
            "auth_artifact_id": "artifact_1",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["summary"]["imported_count"] == 1
    assert response.get_json()["summary"]["items"][0]["status"] == "imported"
    assert identity.calls == [("current_user", {"session_token": "session_token"})]
    assert service.calls == [
        (
            "import_google_calendar",
            {
                "account_id": "acct_1",
                "auth_handle": "google-oauth-token",
                "provider_account_id": "google-user",
                "visible_start": datetime.fromisoformat("2026-05-30T12:00:00+00:00"),
                "visible_end": datetime.fromisoformat("2026-06-30T12:00:00+00:00"),
                "captured_timezone": "UTC",
                "auth_artifact_id": "artifact_1",
            },
        )
    ]


def test_import_route_rejects_missing_session_before_service_call():
    client, service, identity = make_client()

    response = client.post(
        "/api/calendar-import/google/import",
        json={
            "account_id": "acct_1",
            "auth_handle": "google-oauth-token",
            "visible_start": "2026-05-30T12:00:00+00:00",
            "visible_end": "2026-06-30T12:00:00+00:00",
            "captured_timezone": "UTC",
        },
        headers={},
    )

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


def test_stop_and_revoke_routes_delegate_to_service():
    client, service, _identity = make_client()

    stop_response = client.post(
        "/api/calendar-import/google/stop",
        json={"account_id": "spoofed_account", "auth_handle": "google-oauth-token"},
    )
    revoke_response = client.post(
        "/api/calendar-import/google/revoke",
        json={"account_id": "spoofed_account", "auth_handle": "google-oauth-token"},
    )

    assert stop_response.status_code == 200
    assert revoke_response.status_code == 200
    assert stop_response.get_json()["authorization"]["state"] == "stopped"
    assert revoke_response.get_json()["authorization"]["state"] == "revoked"
    assert [call[0] for call in service.calls] == [
        "stop_authorization",
        "revoke_authorization",
    ]


def test_route_errors_return_structured_error_body():
    client, _service, _identity = make_client(ErrorService())

    response = client.post(
        "/api/calendar-import/google/stop",
        json={"account_id": "acct_1", "auth_handle": "missing"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "calendar_authorization_not_found",
            "fact": {"type": "calendar_authorization_not_found"},
        }
    }


def test_import_route_returns_safe_access_denied_error():
    client, _service, _identity = make_client(AccessDeniedImportService())

    response = client.post(
        "/api/calendar-import/google/import",
        json={
            "auth_handle": "google-oauth-token",
            "visible_start": "2026-05-30T12:00:00+00:00",
            "visible_end": "2026-06-30T12:00:00+00:00",
            "captured_timezone": "UTC",
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


def test_create_app_registers_calendar_import_blueprint_when_service_is_provided():
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        calendar_import_service=FakeCalendarImportService(),
    )
    response = app.test_client().post(
        "/api/calendar-import/google/stop",
        json={"account_id": "acct_1", "auth_handle": "google-oauth-token"},
        headers={"Authorization": "Bearer session_token"},
    )
    assert response.status_code == 404

    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        identity_access_service=FakeIdentityService(),
        calendar_import_service=FakeCalendarImportService(),
    )
    client = app.test_client()

    response = client.post(
        "/api/calendar-import/google/stop",
        json={"account_id": "acct_1", "auth_handle": "google-oauth-token"},
        headers={"Authorization": "Bearer session_token"},
    )

    assert response.status_code == 200
