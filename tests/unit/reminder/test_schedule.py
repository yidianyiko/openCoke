from datetime import UTC, date, datetime, time

import pytest

from agent.reminder.errors import InvalidSchedule, RRULENotSupported
from agent.reminder.models import ReminderSchedule
from agent.reminder.schedule import (
    build_schedule_from_anchor,
    compute_initial_next_fire_at,
    compute_next_fire_after_success,
    validate_rrule_subset,
)


def test_build_schedule_snapshots_local_intent_from_timezone():
    schedule = build_schedule_from_anchor(
        anchor_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        timezone="Asia/Tokyo",
        rrule=None,
    )

    assert schedule.anchor_at == datetime(2026, 4, 29, 10, 0, tzinfo=UTC)
    assert schedule.local_date == date(2026, 4, 29)
    assert schedule.local_time == time(19, 0)
    assert schedule.timezone == "Asia/Tokyo"


def test_one_shot_next_fire_must_be_future():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )

    assert compute_initial_next_fire_at(
        schedule,
        now=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
    ) == datetime(2026, 4, 29, 1, 0, tzinfo=UTC)

    with pytest.raises(InvalidSchedule):
        compute_initial_next_fire_at(
            schedule,
            now=datetime(2026, 4, 30, 1, 0, tzinfo=UTC),
        )


def test_recurring_schedule_uses_first_future_occurrence():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 20, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 20),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=DAILY",
    )

    assert compute_initial_next_fire_at(
        schedule,
        now=datetime(2026, 4, 28, 2, 0, tzinfo=UTC),
    ) == datetime(2026, 4, 29, 1, 0, tzinfo=UTC)


def test_supported_and_rejected_rrule_subset():
    assert (
        validate_rrule_subset("FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2")
        == "FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2"
    )

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=HOURLY")

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=DAILY;BYHOUR=9")


def test_next_fire_after_success_returns_none_for_exhausted_recurrence():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 28),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=DAILY;COUNT=1",
    )

    assert (
        compute_next_fire_after_success(
            schedule,
            scheduled_for=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
            now=datetime(2026, 4, 28, 1, 1, tzinfo=UTC),
        )
        is None
    )
