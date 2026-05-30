from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.recurrence import next_occurrence_after
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.scheduler import ReminderScheduler
from coke.domains.reminder.service import ReminderService

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


def make_service() -> ReminderService:
    return ReminderService(
        repository=InMemoryReminderRepository(),
        now=lambda: NOW,
        id_factory=sequence_factory("scheduler"),
    )


def test_recurrence_expands_using_captured_timezone_not_current_display_timezone():
    start = datetime(2026, 5, 30, 0, 30, tzinfo=UTC)
    rule = {"frequency": "daily", "interval": 1}

    next_fire = next_occurrence_after(
        recurrence_rule=rule,
        previous_fire_at=start,
        captured_timezone="America/New_York",
    )

    assert next_fire == datetime(2026, 5, 31, 0, 30, tzinfo=UTC)


def test_same_owner_same_due_time_is_one_grouped_fire_turn_with_ordered_fire_ids():
    service = make_service()
    due_at = NOW + timedelta(minutes=30)
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="first",
                trigger_time=due_at,
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="second",
                trigger_time=due_at,
                captured_timezone="UTC",
            ),
        ],
    )
    scheduler = ReminderScheduler(service=service, jobstore="memory")

    groups = scheduler.collect_due_fire_turns(due_at)

    assert len(groups) == 1
    assert groups[0].owner_account_id == "acct_1"
    assert groups[0].due_at == due_at
    assert groups[0].trigger_id == f"reminder_fire:acct_1:{due_at.isoformat()}"
    assert groups[0].fire_ids == [
        service.repository.get_fire_by_occurrence(
            created.items[0].reminder_id, due_at.isoformat()
        ).id,
        service.repository.get_fire_by_occurrence(
            created.items[1].reminder_id, due_at.isoformat()
        ).id,
    ]


def test_restart_catch_up_keeps_personal_and_shared_but_discards_missed_proactive():
    service = make_service()
    missed = NOW - timedelta(hours=1)
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="personal",
                trigger_time=missed,
                captured_timezone="UTC",
                time_state="valid_future",
            ),
            ReminderBatchItem(
                operation="create",
                content="shared projection",
                trigger_time=missed,
                captured_timezone="UTC",
                kind="shared_projection",
                time_state="valid_future",
            ),
            ReminderBatchItem(
                operation="create",
                content="proactive",
                trigger_time=missed,
                captured_timezone="UTC",
                kind="proactive",
                time_state="valid_future",
            ),
        ],
    )
    scheduler = ReminderScheduler(service=service, jobstore="memory")

    catch_up = scheduler.catch_up_missed(now=NOW)

    assert [(group.owner_account_id, group.due_at) for group in catch_up] == [
        ("acct_1", missed)
    ]
    assert len(catch_up[0].fire_ids) == 2
    proactive_fire = service.repository.get_fire_by_occurrence(
        created.items[2].reminder_id,
        missed.isoformat(),
    )
    assert proactive_fire.fire_state == "discarded"
    assert proactive_fire.missed_catch_up is True


def test_nightly_summary_uses_twenty_hundred_in_owner_current_timezone():
    service = make_service()
    service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="unscheduled one",
                captured_timezone="UTC",
            )
        ],
    )
    scheduler = ReminderScheduler(
        service=service,
        jobstore="memory",
        account_timezone=lambda account_id: "Asia/Tokyo",
    )

    summary = scheduler.nightly_summary_turn(
        owner_account_id="acct_1",
        local_date=datetime(2026, 5, 31, tzinfo=UTC).date(),
    )

    assert summary.local_scheduled_at.isoformat() == "2026-05-31T20:00:00+09:00"
    assert summary.owner_account_id == "acct_1"
    assert summary.reminder_ids == [
        service.repository.list_active_reminders("acct_1")[0].id
    ]
