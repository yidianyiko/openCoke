from __future__ import annotations

from datetime import UTC, datetime

from agent.agno_agent.capabilities.reminder_target_resolver import (
    Clarify,
    ReminderTargetSelector,
    ResolvedOne,
    resolve_target,
)
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderQuery,
    ReminderSchedule,
)


def _schedule(
    *,
    anchor_at: datetime | None = None,
    local_date: str = "2026-05-26",
    local_time: str = "08:00:00",
    rrule: str | None = None,
) -> ReminderSchedule:
    return ReminderSchedule(
        anchor_at=anchor_at or datetime(2026, 5, 25, 23, 0, tzinfo=UTC),
        local_date=datetime.fromisoformat(local_date).date(),
        local_time=datetime.fromisoformat(f"2026-05-26T{local_time}").time(),
        timezone="Asia/Tokyo",
        rrule=rrule,
    )


def _reminder(
    reminder_id: str,
    *,
    title: str = "喝水",
    local_date: str = "2026-05-26",
    local_time: str = "08:00:00",
    rrule: str | None = None,
    conversation_id: str = "conv-1",
    updated_at: datetime | None = None,
) -> Reminder:
    now = updated_at or datetime(2026, 5, 25, 23, 0, tzinfo=UTC)
    return Reminder(
        id=reminder_id,
        owner_user_id="user-1",
        title=title,
        schedule=_schedule(local_date=local_date, local_time=local_time, rrule=rrule),
        agent_output_target=AgentOutputTarget(
            conversation_id=conversation_id,
            character_id="char-1",
            route_key="route-1",
        ),
        created_by_system="agent",
        origin="user",
        visibility="visible",
        fire_mode="notify",
        prompt=None,
        metadata={},
        lifecycle_state="active",
        next_fire_at=now,
        last_fired_at=None,
        last_event_ack_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
        cancelled_at=None,
        failed_at=None,
    )


class FakeRuntime:
    def __init__(self, reminders: list[Reminder]) -> None:
        self.reminders = reminders
        self.calls = []

    def list_visible_reminders(self, *, owner_user_id: str, query: ReminderQuery):
        self.calls.append((owner_user_id, query))
        return list(self.reminders)


def test_resolve_target_prefers_exact_reminder_id():
    runtime = FakeRuntime([_reminder("rem-1", title="喝水")])

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(reminder_id="rem-1", target_title="missing"),
        runtime,
    )

    assert isinstance(result, ResolvedOne)
    assert result.reminder_id == "rem-1"


def test_resolve_target_ignores_numeric_account_suffix_pseudo_id():
    runtime = FakeRuntime([_reminder("rem-1", title="喝水", rrule="FREQ=DAILY")])

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(
            reminder_id="25193553",
            target_title="喝水",
            target_rrule="FREQ=DAILY",
        ),
        runtime,
    )

    assert isinstance(result, ResolvedOne)
    assert result.reminder_id == "rem-1"


def test_resolve_target_title_strips_generic_reminder_suffix():
    runtime = FakeRuntime([_reminder("rem-1", title="喝水")])

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(target_title="喝水提醒"),
        runtime,
    )

    assert isinstance(result, ResolvedOne)
    assert result.reminder_id == "rem-1"


def test_resolve_target_fails_closed_on_duplicate_title():
    runtime = FakeRuntime([_reminder("rem-1"), _reminder("rem-2")])

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(target_title="喝水"),
        runtime,
    )

    assert isinstance(result, Clarify)
    assert [candidate.reminder_id for candidate in result.candidates] == [
        "rem-1",
        "rem-2",
    ]


def test_resolve_target_filters_by_local_time_and_rrule():
    runtime = FakeRuntime(
        [
            _reminder("rem-1", local_time="08:00:00", rrule="FREQ=DAILY"),
            _reminder("rem-2", local_time="09:00:00", rrule="FREQ=WEEKLY"),
        ]
    )

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(target_local_time="08:00", target_rrule="FREQ=DAILY"),
        runtime,
    )

    assert isinstance(result, ResolvedOne)
    assert result.reminder_id == "rem-1"


def test_resolve_target_recent_active_never_guesses_when_multiple_recent_match():
    runtime = FakeRuntime(
        [
            _reminder(
                "rem-1",
                conversation_id="conv-1",
                updated_at=datetime(2026, 5, 25, 23, 0, tzinfo=UTC),
            ),
            _reminder(
                "rem-2",
                conversation_id="conv-1",
                updated_at=datetime(2026, 5, 25, 23, 0, tzinfo=UTC),
            ),
        ]
    )

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(
            target_scope="recent_active",
            current_conversation_id="conv-1",
        ),
        runtime,
    )

    assert isinstance(result, Clarify)
    assert len(result.candidates) == 2


def test_resolve_target_recent_active_uses_unique_latest_candidate():
    runtime = FakeRuntime(
        [
            _reminder(
                "rem-1",
                title="喝水",
                updated_at=datetime(2026, 5, 25, 23, 0, tzinfo=UTC),
            ),
            _reminder(
                "rem-2",
                title="喝水",
                updated_at=datetime(2026, 5, 25, 23, 1, tzinfo=UTC),
            ),
        ]
    )

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(
            target_title="喝水",
            target_scope="recent_active",
        ),
        runtime,
    )

    assert isinstance(result, ResolvedOne)
    assert result.reminder_id == "rem-2"


def test_resolve_target_recent_active_resolves_single_current_conversation_match():
    runtime = FakeRuntime(
        [
            _reminder("rem-1", conversation_id="conv-1"),
            _reminder("rem-2", conversation_id="conv-2"),
        ]
    )

    result = resolve_target(
        "user-1",
        ReminderTargetSelector(
            target_scope="recent_active",
            current_conversation_id="conv-1",
        ),
        runtime,
    )

    assert isinstance(result, ResolvedOne)
    assert result.reminder_id == "rem-1"
