from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.api.reminder_routes import create_reminder_blueprint
from coke.app import create_app
from coke.config import Settings
from coke.domains.reminder.models import ReminderError

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeReminderService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute_batch(self, owner_account_id, items):
        self.calls.append(
            ("execute_batch", {"owner_account_id": owner_account_id, "items": items})
        )
        return SimpleNamespace(
            owner_account_id=owner_account_id,
            items=[
                SimpleNamespace(
                    state="succeeded",
                    reminder_id="reminder_1",
                    reason=None,
                    time_state="valid_future",
                    fact={"content": "pay rent"},
                )
            ],
        )

    def calendar_entries(
        self, owner_account_id, visible_start, visible_end, display_timezone
    ):
        self.calls.append(
            (
                "calendar_entries",
                {
                    "owner_account_id": owner_account_id,
                    "visible_start": visible_start,
                    "visible_end": visible_end,
                    "display_timezone": display_timezone,
                },
            )
        )
        return SimpleNamespace(
            owner_account_id=owner_account_id,
            entries=[
                SimpleNamespace(
                    entry_type="one_time",
                    reminder_id="reminder_1",
                    fire_id=None,
                    display_start=visible_start,
                    display_end=visible_start,
                    content="pay rent",
                    action_handles=["edit", "complete", "delete"],
                    friend_identifiers=[],
                    member_reminder_ids=[],
                    fact={"kind": "timed"},
                )
            ],
        )

    def schedule_unscheduled(
        self, owner_account_id, reminder_id, trigger_time, captured_timezone
    ):
        self.calls.append(
            (
                "schedule_unscheduled",
                {"owner_account_id": owner_account_id, "reminder_id": reminder_id},
            )
        )
        return SimpleNamespace(
            state="succeeded",
            reminder_id=reminder_id,
            reason=None,
            time_state="valid_future",
            fact={},
        )

    def clear_trigger_time(self, owner_account_id, reminder_id):
        self.calls.append(
            (
                "clear_trigger_time",
                {"owner_account_id": owner_account_id, "reminder_id": reminder_id},
            )
        )
        return SimpleNamespace(
            state="succeeded",
            reminder_id=reminder_id,
            reason=None,
            time_state=None,
            fact={},
        )

    def complete_reminder(self, owner_account_id, reminder_id):
        self.calls.append(
            (
                "complete_reminder",
                {"owner_account_id": owner_account_id, "reminder_id": reminder_id},
            )
        )
        return SimpleNamespace(
            state="succeeded",
            reminder_id=reminder_id,
            reason=None,
            time_state=None,
            fact={},
        )

    def delete_reminder(self, owner_account_id, reminder_id, user_initiated=True):
        self.calls.append(
            (
                "delete_reminder",
                {
                    "owner_account_id": owner_account_id,
                    "reminder_id": reminder_id,
                    "user_initiated": user_initiated,
                },
            )
        )
        return SimpleNamespace(
            state="succeeded",
            reminder_id=reminder_id,
            reason=None,
            time_state=None,
            fact={},
        )


class ErrorService(FakeReminderService):
    def clear_trigger_time(self, owner_account_id, reminder_id):
        raise ReminderError("reminder_not_found", fact={"type": "reminder_not_found"})


def make_client(service=None):
    service = service or FakeReminderService()
    app = Flask(__name__)
    app.register_blueprint(create_reminder_blueprint(service))
    return app.test_client(), service


def test_batch_and_calendar_routes_are_thin_service_adapters():
    client, service = make_client()

    batch_response = client.post(
        "/api/reminders/batch",
        json={
            "owner_account_id": "acct_1",
            "items": [
                {
                    "operation": "create",
                    "content": "pay rent",
                    "trigger_time": "2026-05-30T13:00:00+00:00",
                    "captured_timezone": "UTC",
                }
            ],
        },
    )
    calendar_response = client.get(
        "/api/reminders/calendar"
        "?owner_account_id=acct_1"
        "&visible_start=2026-05-30T12:00:00%2B00:00"
        "&visible_end=2026-05-31T12:00:00%2B00:00"
        "&display_timezone=Asia/Tokyo"
    )

    assert batch_response.status_code == 200
    assert batch_response.get_json()["items"][0]["state"] == "succeeded"
    assert calendar_response.status_code == 200
    assert calendar_response.get_json()["entries"][0]["action_handles"] == [
        "edit",
        "complete",
        "delete",
    ]
    assert [call[0] for call in service.calls] == ["execute_batch", "calendar_entries"]


def test_calendar_command_routes_delegate_to_service_methods():
    client, service = make_client()

    assert (
        client.post(
            "/api/reminders/reminder_1/schedule-unscheduled",
            json={
                "owner_account_id": "acct_1",
                "trigger_time": "2026-05-30T13:00:00+00:00",
                "captured_timezone": "UTC",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/reminders/reminder_1/clear-trigger-time",
            json={"owner_account_id": "acct_1"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/reminders/reminder_1/complete",
            json={"owner_account_id": "acct_1"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/reminders/reminder_1/delete",
            json={"owner_account_id": "acct_1"},
        ).status_code
        == 200
    )

    assert [call[0] for call in service.calls] == [
        "schedule_unscheduled",
        "clear_trigger_time",
        "complete_reminder",
        "delete_reminder",
    ]


def test_route_errors_return_structured_error_body():
    client, _service = make_client(ErrorService())

    response = client.post(
        "/api/reminders/missing/clear-trigger-time",
        json={"owner_account_id": "acct_1"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "reminder_not_found",
            "fact": {"type": "reminder_not_found"},
        }
    }


def test_create_app_registers_reminder_blueprint_when_service_is_provided():
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        reminder_service=FakeReminderService(),
    )
    client = app.test_client()

    response = client.get(
        "/api/reminders/calendar"
        "?owner_account_id=acct_1"
        "&visible_start=2026-05-30T12:00:00%2B00:00"
        "&visible_end=2026-05-31T12:00:00%2B00:00"
        "&display_timezone=UTC"
    )

    assert response.status_code == 200
