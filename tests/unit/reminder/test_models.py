from datetime import UTC, date, datetime, time

from agent.reminder.errors import InvalidArgument, ReminderError
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderBatchCommandEnvelope,
    ReminderCommand,
    ReminderCommandEnvelope,
    ReminderFiredEvent,
    ReminderFireResult,
    ReminderSchedule,
)


def test_reminder_model_contains_protocol_boundary_fields():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )
    target = AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="wechat_personal:primary",
    )
    reminder = Reminder(
        id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        schedule=schedule,
        agent_output_target=target,
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

    assert reminder.agent_output_target.conversation_id == "conv-1"
    assert reminder.next_fire_at == schedule.anchor_at
    assert reminder.created_by_system == "agent"


def test_command_envelope_carries_trusted_owner_context():
    command = ReminderCommand(action="list")
    envelope = ReminderCommandEnvelope(owner_user_id="user-1", command=command)
    batch = ReminderBatchCommandEnvelope(owner_user_id="user-1", commands=[command])

    assert envelope.owner_user_id == "user-1"
    assert batch.commands == [command]


def test_fired_event_and_result_use_fire_id_boundary():
    event = ReminderFiredEvent(
        event_type="reminder.fired",
        event_id="evt-1",
        fire_id="rem-1:2026-04-29T01:00:00+00:00",
        reminder_id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        fire_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        scheduled_for=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        agent_output_target=AgentOutputTarget("conv-1", "char-1", None),
    )
    result = ReminderFireResult(
        ok=True,
        fire_id=event.fire_id,
        output_reference="output-1",
        error_code=None,
        error_message=None,
    )

    assert result.fire_id == event.fire_id
    assert result.ok is True


def test_reminder_error_exposes_stable_code_and_detail():
    err = InvalidArgument("bad shape", detail={"field": "title"})

    assert isinstance(err, ReminderError)
    assert err.code == "InvalidArgument"
    assert err.user_message == "bad shape"
    assert err.detail == {"field": "title"}
