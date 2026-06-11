from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from coke.domains.reminder.models import Reminder, ReminderBatchItem, ReminderKind
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


def add_existing_reminder(
    repository: InMemoryReminderRepository,
    *,
    reminder_id: str,
    owner_account_id: str,
    content: str,
    due_at: datetime,
    kind: ReminderKind = "timed",
    hidden_from_calendar: bool = False,
) -> None:
    repository.add_reminder(
        Reminder(
            id=reminder_id,
            owner_account_id=owner_account_id,
            content=content,
            content_hash=f"hash:{reminder_id}",
            kind=kind,
            next_fire_at=due_at,
            recurrence_rule={},
            captured_timezone="UTC",
            duration_minutes=15,
            lifecycle="active",
            hidden_from_calendar=hidden_from_calendar,
            shared_reminder_id="shared_1" if kind == "shared_projection" else None,
            created_at=NOW,
            updated_at=NOW,
        )
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
    add_existing_reminder(
        service.repository,
        reminder_id="existing_first",
        owner_account_id="acct_1",
        content="first",
        due_at=due_at,
    )
    add_existing_reminder(
        service.repository,
        reminder_id="existing_second",
        owner_account_id="acct_1",
        content="second",
        due_at=due_at,
    )
    scheduler = ReminderScheduler(service=service, jobstore="memory")

    groups = scheduler.collect_due_fire_turns(due_at)

    assert len(groups) == 1
    assert groups[0].owner_account_id == "acct_1"
    assert groups[0].due_at == due_at
    assert groups[0].trigger_id == f"reminder_fire:acct_1:{due_at.isoformat()}"
    assert groups[0].fire_ids == [
        service.repository.get_fire_by_occurrence(
            "existing_first", due_at.isoformat()
        ).id,
        service.repository.get_fire_by_occurrence(
            "existing_second", due_at.isoformat()
        ).id,
    ]


def test_restart_catch_up_keeps_personal_and_shared_but_discards_missed_proactive():
    service = make_service()
    missed = NOW - timedelta(hours=1)
    add_existing_reminder(
        service.repository,
        reminder_id="missed_personal",
        owner_account_id="acct_1",
        content="personal",
        due_at=missed,
    )
    add_existing_reminder(
        service.repository,
        reminder_id="missed_shared_projection",
        owner_account_id="acct_1",
        content="shared projection",
        due_at=missed,
        kind="shared_projection",
    )
    add_existing_reminder(
        service.repository,
        reminder_id="missed_proactive",
        owner_account_id="acct_1",
        content="proactive",
        due_at=missed,
        kind="proactive",
        hidden_from_calendar=True,
    )
    scheduler = ReminderScheduler(service=service, jobstore="memory")

    catch_up = scheduler.catch_up_missed(now=NOW)

    assert [(group.owner_account_id, group.due_at) for group in catch_up] == [
        ("acct_1", missed)
    ]
    assert len(catch_up[0].fire_ids) == 2
    proactive_fire = service.repository.get_fire_by_occurrence(
        "missed_proactive",
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
