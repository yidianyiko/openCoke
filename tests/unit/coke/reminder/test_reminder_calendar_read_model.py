from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from coke.domains.reminder.calendar_read_model import ReminderCalendarReadModel
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


def make_service() -> ReminderService:
    return ReminderService(
        repository=InMemoryReminderRepository(),
        now=lambda: NOW,
        id_factory=sequence_factory("calendar"),
    )


def test_calendar_returns_typed_entries_and_type_specific_action_handles():
    service = make_service()
    due = NOW + timedelta(hours=1)
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="one time",
                trigger_time=due,
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="daily recurring",
                trigger_time=due + timedelta(days=1),
                captured_timezone="UTC",
                recurrence_rule={"frequency": "daily", "interval": 1},
            ),
            ReminderBatchItem(
                operation="create",
                content="unscheduled",
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="shared",
                trigger_time=due + timedelta(hours=2),
                captured_timezone="UTC",
                kind="shared_projection",
                shared_reminder_id="shared_1",
            ),
        ],
    )
    read_model = ReminderCalendarReadModel(
        repository=service.repository,
        friend_identifiers=lambda shared_id, viewer_id: ["friend:alice"],
    )

    entries = read_model.query(
        owner_account_id="acct_1",
        visible_start=NOW,
        visible_end=NOW + timedelta(days=3),
        display_timezone="Asia/Tokyo",
    )
    by_type = {entry.entry_type: entry for entry in entries.entries}

    assert by_type["one_time"].action_handles == ["edit", "complete", "delete"]
    assert by_type["recurring_occurrence"].action_handles == [
        "complete_occurrence",
        "edit_series",
        "delete_series",
    ]
    assert by_type["unscheduled"].action_handles == ["edit", "complete", "delete"]
    assert by_type["shared_projection"].action_handles == [
        "complete_own_projection",
        "cancel_whole_shared_reminder",
    ]
    assert by_type["shared_projection"].friend_identifiers == ["friend:alice"]
    assert by_type["one_time"].display_start.isoformat() == "2026-05-30T22:00:00+09:00"
    assert by_type["recurring_occurrence"].reminder_id == created.items[1].reminder_id


def test_calendar_includes_undelivered_and_merged_same_time_groups():
    service = make_service()
    due = NOW + timedelta(hours=1)
    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="first",
                trigger_time=due,
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="second",
                trigger_time=due,
                captured_timezone="UTC",
            ),
        ],
    )
    fire = service.claim_due_fire(result.items[0].reminder_id, due)
    service.mark_fire_undelivered(fire.id)
    read_model = ReminderCalendarReadModel(repository=service.repository)

    entries = read_model.query(
        owner_account_id="acct_1",
        visible_start=NOW,
        visible_end=NOW + timedelta(days=1),
        display_timezone="UTC",
    )
    by_type = {entry.entry_type: entry for entry in entries.entries}

    assert by_type["merged_group"].member_reminder_ids == [
        result.items[0].reminder_id,
        result.items[1].reminder_id,
    ]
    assert by_type["merged_group"].action_handles == ["expand"]
    assert by_type["undelivered"].fire_id == fire.id
    assert by_type["undelivered"].action_handles == ["complete", "delete"]


def test_reminder_service_calendar_uses_shared_friend_identifier_resolver():
    service = ReminderService(
        repository=InMemoryReminderRepository(),
        now=lambda: NOW,
        id_factory=sequence_factory("service_calendar"),
        friend_identifiers=lambda shared_id, viewer_id: [
            f"{viewer_id}:{shared_id}:Alice Push"
        ],
    )
    due = NOW + timedelta(hours=1)
    service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="shared",
                trigger_time=due,
                captured_timezone="UTC",
                kind="shared_projection",
                shared_reminder_id="shared_1",
            )
        ],
    )

    entries = service.calendar_entries(
        owner_account_id="acct_1",
        visible_start=NOW,
        visible_end=NOW + timedelta(days=1),
        display_timezone="UTC",
    )

    shared = next(
        entry for entry in entries.entries if entry.entry_type == "shared_projection"
    )
    assert shared.friend_identifiers == ["acct_1:shared_1:Alice Push"]
