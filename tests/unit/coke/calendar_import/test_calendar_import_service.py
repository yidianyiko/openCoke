from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import count
from types import SimpleNamespace

import pytest

from coke.domains.calendar_import.google import GoogleCalendarClientPort
from coke.domains.calendar_import.models import (
    CalendarImportError,
    CalendarOccurrence,
    CalendarSourceEvent,
)
from coke.domains.calendar_import.service import (
    CalendarImportService,
    InMemoryCalendarImportRepository,
)
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
VISIBLE_END = NOW + timedelta(days=30)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


class FakeGoogleCalendarClient(GoogleCalendarClientPort):
    def __init__(self, events: list[CalendarSourceEvent]) -> None:
        self.events = events
        self.list_calls: list[tuple[str, datetime, datetime]] = []
        self.revoked_handles: list[str] = []

    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]:
        self.list_calls.append((auth_handle, visible_start, visible_end))
        return list(self.events)

    def revoke_authorization(self, auth_handle: str) -> None:
        self.revoked_handles.append(auth_handle)


class FakeAccessGate:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str]] = []

    def check_access_for_action(self, account_id: str, action: str):
        self.calls.append((account_id, action))
        return SimpleNamespace(
            allowed=self.allowed,
            fact={
                "type": "account_access_denied",
                "account_id": account_id,
                "denial_reason": "subscription_inactive",
                "checkout_url": None,
            },
        )


def make_service(events: list[CalendarSourceEvent], access_gate=None):
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=sequence_factory("reminder"),
    )
    calendar_repository = InMemoryCalendarImportRepository()
    google_client = FakeGoogleCalendarClient(events)
    if access_gate is None:
        access_gate = FakeAccessGate(allowed=True)
    service = CalendarImportService(
        repository=calendar_repository,
        google_client=google_client,
        reminder_service=reminder_service,
        now=lambda: NOW,
        id_factory=sequence_factory("calendar"),
        access_gate=access_gate,
    )
    return service, calendar_repository, reminder_repository, google_client


def event(
    source_event_id: str,
    start: datetime,
    end: datetime | None = None,
    *,
    title: str = "Team sync",
    description: str = "Discuss launch",
    provider_calendar_id: str = "primary",
    all_day: bool = False,
    recurrence_rule: dict | None = None,
    recurrence_expressible: bool = False,
    occurrences: list[CalendarOccurrence] | None = None,
) -> CalendarSourceEvent:
    return CalendarSourceEvent(
        provider_calendar_id=provider_calendar_id,
        source_event_id=source_event_id,
        title=title,
        description=description,
        start=start,
        end=end,
        all_day=all_day,
        recurrence_rule=recurrence_rule or {},
        recurrence_expressible=recurrence_expressible,
        occurrences=occurrences or [],
        source_metadata={"etag": f"etag-{source_event_id}"},
    )


def import_calendar(service: CalendarImportService):
    return service.import_google_calendar(
        account_id="acct_1",
        auth_handle="google-oauth-token",
        provider_account_id="google-user",
        visible_start=NOW,
        visible_end=VISIBLE_END,
        captured_timezone="UTC",
    )


def test_future_one_time_event_imports_through_reminder_domain():
    start = NOW + timedelta(hours=2)
    service, repository, reminder_repository, google_client = make_service(
        [event("event_1", start, start + timedelta(minutes=45))]
    )

    summary = import_calendar(service)

    assert google_client.list_calls == [("google-oauth-token", NOW, VISIBLE_END)]
    assert summary.imported_count == 1
    assert summary.skipped_count == 0
    assert summary.downgraded_count == 0
    assert summary.failed_count == 0
    assert [item.status for item in summary.items] == ["imported"]
    assert repository.get_run(summary.run_id).imported_count == 1

    reminders = reminder_repository.list_active_reminders("acct_1")
    assert len(reminders) == 1
    assert reminders[0].content == "Team sync\n\nDiscuss launch"
    assert reminders[0].kind == "timed"
    assert reminders[0].next_fire_at == start
    assert reminders[0].duration_minutes == 45
    assert summary.items[0].reminder_id == reminders[0].id


def test_access_denied_account_fails_closed_before_calendar_read():
    access_gate = FakeAccessGate(allowed=False)
    service, repository, reminder_repository, google_client = make_service(
        [event("event_1", NOW + timedelta(hours=2))],
        access_gate=access_gate,
    )

    with pytest.raises(CalendarImportError) as error:
        import_calendar(service)

    assert error.value.code == "access_denied"
    assert error.value.fact == {
        "type": "account_access_denied",
        "account_id": "acct_1",
        "denial_reason": "subscription_inactive",
        "checkout_url": None,
    }
    assert access_gate.calls == [("acct_1", "calendar_import")]
    assert google_client.list_calls == []
    assert repository.runs_by_id == {}
    assert reminder_repository.list_active_reminders("acct_1") == []


def test_access_allowed_account_proceeds_to_calendar_read():
    access_gate = FakeAccessGate(allowed=True)
    service, _repository, _reminder_repository, google_client = make_service(
        [event("event_1", NOW + timedelta(hours=2))],
        access_gate=access_gate,
    )

    summary = import_calendar(service)

    assert access_gate.calls == [("acct_1", "calendar_import")]
    assert google_client.list_calls == [("google-oauth-token", NOW, VISIBLE_END)]
    assert summary.imported_count == 1


def test_historical_events_are_recorded_but_not_imported():
    service, repository, reminder_repository, _google_client = make_service(
        [
            event(
                "past_event",
                NOW - timedelta(days=1),
                NOW - timedelta(days=1, minutes=-30),
            )
        ]
    )

    summary = import_calendar(service)

    assert summary.imported_count == 0
    assert summary.skipped_count == 1
    assert summary.items[0].status == "historical_skipped"
    assert summary.items[0].reason == "historical_event"
    assert reminder_repository.list_active_reminders("acct_1") == []
    assert repository.list_items_for_run(summary.run_id)[0].reminder_id is None


def test_all_day_and_missing_duration_mapping_use_midnight_and_default_duration():
    service, _repository, reminder_repository, _google_client = make_service(
        [
            event(
                "all_day_event",
                datetime(2026, 6, 3, 9, 30, tzinfo=UTC),
                None,
                title="Holiday",
                description="",
                all_day=True,
                occurrences=[
                    CalendarOccurrence(
                        recurrence_instance_key="2026-06-03",
                        start=date(2026, 6, 3),
                        end=None,
                        all_day=True,
                    )
                ],
            )
        ]
    )

    summary = import_calendar(service)

    reminders = reminder_repository.list_active_reminders("acct_1")
    assert summary.imported_count == 1
    assert reminders[0].content == "Holiday"
    assert reminders[0].next_fire_at == datetime(2026, 6, 3, 0, 0, tzinfo=UTC)
    assert reminders[0].duration_minutes == 15


def test_expressible_recurrence_is_preserved_as_recurring_reminder():
    start = NOW + timedelta(days=1)
    service, _repository, reminder_repository, _google_client = make_service(
        [
            event(
                "recurring_event",
                start,
                start + timedelta(minutes=30),
                recurrence_rule={"frequency": "weekly", "interval": 1},
                recurrence_expressible=True,
            )
        ]
    )

    summary = import_calendar(service)

    reminders = reminder_repository.list_active_reminders("acct_1")
    assert summary.imported_count == 1
    assert summary.downgraded_items == []
    assert reminders[0].kind == "recurring"
    assert reminders[0].recurrence_rule == {"frequency": "weekly", "interval": 1}


def test_non_expressible_recurrence_downgrades_visible_future_occurrences():
    past = CalendarOccurrence(
        recurrence_instance_key="2026-05-29T13:00:00+00:00",
        start=NOW - timedelta(days=1),
        end=NOW - timedelta(days=1) + timedelta(minutes=30),
    )
    future_1 = CalendarOccurrence(
        recurrence_instance_key="2026-06-01T13:00:00+00:00",
        start=NOW + timedelta(days=2),
        end=NOW + timedelta(days=2, minutes=30),
    )
    future_2 = CalendarOccurrence(
        recurrence_instance_key="2026-06-08T13:00:00+00:00",
        start=NOW + timedelta(days=9),
        end=NOW + timedelta(days=9, minutes=30),
    )
    service, _repository, reminder_repository, _google_client = make_service(
        [
            event(
                "unsupported_rrule",
                future_1.start,
                future_1.end,
                recurrence_rule={"raw": "FREQ=SECONDLY"},
                recurrence_expressible=False,
                occurrences=[past, future_1, future_2],
            )
        ]
    )

    summary = import_calendar(service)

    assert summary.imported_count == 0
    assert summary.downgraded_count == 2
    assert summary.skipped_count == 1
    assert [item.status for item in summary.items] == [
        "historical_skipped",
        "downgraded",
        "downgraded",
    ]
    assert [item.reason for item in summary.downgraded_items] == [
        "recurrence_rule_not_expressible",
        "recurrence_rule_not_expressible",
    ]
    reminders = reminder_repository.list_active_reminders("acct_1")
    assert [reminder.kind for reminder in reminders] == ["timed", "timed"]


def test_repeat_import_skips_existing_occurrences_without_duplicate_reminders():
    start = NOW + timedelta(hours=3)
    service, repository, reminder_repository, _google_client = make_service(
        [event("event_1", start, start + timedelta(minutes=20))]
    )
    first = import_calendar(service)

    second = import_calendar(service)

    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert second.items[0].status == "skipped_duplicate"
    assert second.items[0].reminder_id == first.items[0].reminder_id
    assert len(reminder_repository.list_active_reminders("acct_1")) == 1
    assert len(repository.list_source_occurrence_items()) == 1


def test_result_counts_are_derived_from_items_and_failed_items_are_listed():
    future = CalendarOccurrence(
        recurrence_instance_key="future",
        start=NOW + timedelta(days=3),
        end=NOW + timedelta(days=3, minutes=30),
    )
    service, repository, _reminder_repository, _google_client = make_service(
        [
            event("good", NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
            event(
                "bad",
                NOW + timedelta(hours=1),
                NOW + timedelta(hours=2),
                title="Team sync",
                description="Discuss launch",
            ),
            event(
                "downgrade",
                future.start,
                future.end,
                recurrence_rule={"raw": "FREQ=SECONDLY"},
                occurrences=[future],
            ),
        ]
    )

    summary = import_calendar(service)
    run = repository.get_run(summary.run_id)
    persisted_items = repository.list_items_for_run(summary.run_id)

    assert [item.status for item in persisted_items] == [
        "imported",
        "failed",
        "downgraded",
    ]
    assert (
        run.imported_count,
        run.skipped_count,
        run.downgraded_count,
        run.failed_count,
    ) == (
        1,
        0,
        1,
        1,
    )
    assert summary.failed_items[0].source_event_id == "bad"
    assert summary.failed_items[0].reason == "duplicate_reminder"


def test_stop_and_revoke_authorization_blocks_future_reads_without_deleting_reminders():
    start = NOW + timedelta(hours=2)
    service, _repository, reminder_repository, google_client = make_service(
        [event("event_1", start, start + timedelta(minutes=45))]
    )
    imported = import_calendar(service)

    stopped = service.stop_authorization(
        account_id="acct_1", auth_handle="google-oauth-token"
    )
    revoked = service.revoke_authorization(
        account_id="acct_1", auth_handle="google-oauth-token"
    )

    assert stopped.state == "stopped"
    assert revoked.state == "revoked"
    assert google_client.revoked_handles == ["google-oauth-token"]
    with pytest.raises(CalendarImportError) as error:
        import_calendar(service)
    assert error.value.code == "calendar_authorization_inactive"
    assert len(reminder_repository.list_active_reminders("acct_1")) == 1
    assert (
        imported.items[0].reminder_id
        == reminder_repository.list_active_reminders("acct_1")[0].id
    )
