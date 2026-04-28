from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderFireResult,
    ReminderSchedule,
)
from agent.runner.reminder_scheduler import ReminderScheduler


def build_schedule(*, rrule=None):
    return ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 29),
        local_time=time(1, 0),
        timezone="UTC",
        rrule=rrule,
    )


def build_reminder(**overrides):
    reminder = Reminder(
        id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        schedule=build_schedule(),
        agent_output_target=AgentOutputTarget("conv-1", "char-1", None),
        created_by_system="agent",
        lifecycle_state="active",
        next_fire_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        last_fired_at=None,
        last_event_ack_at=None,
        last_error=None,
        created_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        completed_at=None,
        cancelled_at=None,
        failed_at=None,
    )
    for key, value in overrides.items():
        setattr(reminder, key, value)
    return reminder


def reminder_document(reminder):
    return {
        "_id": reminder.id,
        "owner_user_id": reminder.owner_user_id,
        "title": reminder.title,
        "schedule": {
            "anchor_at": reminder.schedule.anchor_at,
            "local_date": reminder.schedule.local_date,
            "local_time": reminder.schedule.local_time,
            "timezone": reminder.schedule.timezone,
            "rrule": reminder.schedule.rrule,
        },
        "agent_output_target": {
            "conversation_id": reminder.agent_output_target.conversation_id,
            "character_id": reminder.agent_output_target.character_id,
            "route_key": reminder.agent_output_target.route_key,
        },
        "created_by_system": reminder.created_by_system,
        "lifecycle_state": reminder.lifecycle_state,
        "next_fire_at": reminder.next_fire_at,
        "last_fired_at": reminder.last_fired_at,
        "last_event_ack_at": reminder.last_event_ack_at,
        "last_error": reminder.last_error,
        "created_at": reminder.created_at,
        "updated_at": reminder.updated_at,
        "completed_at": reminder.completed_at,
        "cancelled_at": reminder.cancelled_at,
        "failed_at": reminder.failed_at,
    }


def fire_result(ok=True, fire_id="rem-1:2026-04-29T01:00:00+00:00"):
    return ReminderFireResult(
        ok=ok,
        fire_id=fire_id,
        output_reference="out-1" if ok else None,
        error_code=None if ok else "OutputFailed",
        error_message=None if ok else "output failed",
    )


def test_startup_scans_active_reminders_and_registers_jobs():
    reminder = build_reminder()
    dao = Mock(list_due_active=Mock(return_value=[reminder_document(reminder)]))
    scheduler = ReminderScheduler(
        reminder_dao=dao,
        fire_event_handler=AsyncMock(),
        scheduler=Mock(start=Mock()),
        now_provider=lambda: datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
    )
    scheduler.register_reminder = Mock()

    scheduler.start()

    scheduler.scheduler.start.assert_called_once()
    dao.list_due_active.assert_called_once()
    scheduler.register_reminder.assert_called_once_with(reminder_document(reminder))


def test_register_reminder_uses_stable_job_id_and_payload():
    next_fire_at = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    scheduler_backend = Mock()
    scheduler = ReminderScheduler(
        reminder_dao=Mock(),
        fire_event_handler=AsyncMock(),
        scheduler=scheduler_backend,
        now_provider=lambda: datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
    )

    scheduler.register_reminder(build_reminder(next_fire_at=next_fire_at))

    scheduler_backend.add_job.assert_called_once()
    _, kwargs = scheduler_backend.add_job.call_args
    assert kwargs["id"] == "reminder:rem-1"
    assert kwargs["replace_existing"] is True
    assert kwargs["run_date"] == next_fire_at
    assert kwargs["kwargs"] == {
        "reminder_id": "rem-1",
        "next_fire_at": next_fire_at,
    }


@pytest.mark.asyncio
async def test_stale_wakeup_does_not_emit_event():
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    stored_reminder = reminder_document(
        build_reminder(next_fire_at=scheduled_for + timedelta(minutes=5))
    )
    dao = Mock(get_reminder=Mock(return_value=stored_reminder))
    handler = AsyncMock()
    scheduler = ReminderScheduler(
        reminder_dao=dao,
        fire_event_handler=handler,
        scheduler=Mock(),
        now_provider=lambda: scheduled_for,
    )

    await scheduler._execute_job("rem-1", scheduled_for)

    handler.assert_not_called()
    dao.atomic_apply_fire_success.assert_not_called()
    dao.atomic_apply_fire_failure.assert_not_called()


@pytest.mark.asyncio
async def test_successful_one_shot_completes_reminder_and_clears_next_fire_at():
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    finished_at = datetime(2026, 4, 29, 1, 0, 3, tzinfo=UTC)
    stored_reminder = reminder_document(build_reminder(next_fire_at=scheduled_for))
    dao = Mock(
        get_reminder=Mock(return_value=stored_reminder),
        atomic_apply_fire_success=Mock(return_value=True),
    )
    scheduler = ReminderScheduler(
        reminder_dao=dao,
        fire_event_handler=AsyncMock(return_value=fire_result()),
        scheduler=Mock(remove_job=Mock()),
        now_provider=lambda: finished_at,
    )
    scheduler.remove_reminder = Mock()

    await scheduler._execute_job("rem-1", scheduled_for)

    _, _, updates = dao.atomic_apply_fire_success.call_args.args
    assert updates["lifecycle_state"] == "completed"
    assert updates["next_fire_at"] is None
    assert updates["last_fired_at"] == finished_at
    assert updates["last_event_ack_at"] == finished_at
    assert updates["last_error"] is None
    scheduler.remove_reminder.assert_called_once_with("rem-1")


@pytest.mark.asyncio
async def test_successful_recurring_event_advances_next_fire_at():
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    finished_at = datetime(2026, 4, 29, 1, 0, 3, tzinfo=UTC)
    reminder = build_reminder(
        schedule=build_schedule(rrule="FREQ=DAILY;COUNT=2"),
        next_fire_at=scheduled_for,
    )
    dao = Mock(
        get_reminder=Mock(return_value=reminder_document(reminder)),
        atomic_apply_fire_success=Mock(return_value=True),
    )
    scheduler = ReminderScheduler(
        reminder_dao=dao,
        fire_event_handler=AsyncMock(return_value=fire_result()),
        scheduler=Mock(),
        now_provider=lambda: finished_at,
    )
    scheduler.reschedule_reminder = Mock()

    await scheduler._execute_job("rem-1", scheduled_for)

    _, _, updates = dao.atomic_apply_fire_success.call_args.args
    assert updates["lifecycle_state"] == "active"
    assert updates["next_fire_at"] == datetime(2026, 4, 30, 1, 0, tzinfo=UTC)
    scheduler.reschedule_reminder.assert_called_once()
    assert scheduler.reschedule_reminder.call_args.args[0]["next_fire_at"] == datetime(
        2026, 4, 30, 1, 0, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_failed_fire_result_marks_reminder_failed_and_clears_next_fire_at():
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    finished_at = datetime(2026, 4, 29, 1, 0, 3, tzinfo=UTC)
    dao = Mock(
        get_reminder=Mock(return_value=reminder_document(build_reminder())),
        atomic_apply_fire_failure=Mock(return_value=True),
    )
    scheduler = ReminderScheduler(
        reminder_dao=dao,
        fire_event_handler=AsyncMock(return_value=fire_result(ok=False)),
        scheduler=Mock(),
        now_provider=lambda: finished_at,
    )
    scheduler.remove_reminder = Mock()

    await scheduler._execute_job("rem-1", scheduled_for)

    _, _, updates = dao.atomic_apply_fire_failure.call_args.args
    assert updates["lifecycle_state"] == "failed"
    assert updates["next_fire_at"] is None
    assert updates["failed_at"] == finished_at
    assert updates["last_error"] == "output failed"
    scheduler.remove_reminder.assert_called_once_with("rem-1")
