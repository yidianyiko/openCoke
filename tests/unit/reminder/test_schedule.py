from datetime import UTC, date, datetime, time

import pytest

from agent.reminder.errors import InvalidSchedule, RRULENotSupported
from agent.reminder.models import ReminderSchedule
from agent.reminder.schedule import (
    build_schedule_from_anchor,
    compute_initial_next_fire_at,
    compute_next_fire_after_success,
    validate_timezone,
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
    assert validate_rrule_subset("FREQ=HOURLY") == "FREQ=HOURLY"

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=DAILY;BYHOUR=9")


def test_hourly_schedule_uses_first_future_occurrence():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=HOURLY",
    )

    assert compute_initial_next_fire_at(
        schedule,
        now=datetime(2026, 4, 29, 2, 30, tzinfo=UTC),
    ) == datetime(2026, 4, 29, 3, 0, tzinfo=UTC)


def test_rejects_naive_datetimes():
    with pytest.raises(InvalidSchedule):
        build_schedule_from_anchor(
            anchor_at=datetime(2026, 4, 29, 10, 0),
            timezone="Asia/Tokyo",
            rrule=None,
        )

    one_shot = ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0),
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )
    with pytest.raises(InvalidSchedule):
        compute_initial_next_fire_at(
            one_shot,
            now=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        )

    recurring = ReminderSchedule(
        anchor_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 28),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=DAILY",
    )
    with pytest.raises(InvalidSchedule):
        compute_next_fire_after_success(
            recurring,
            scheduled_for=datetime(2026, 4, 28, 1, 0),
            now=datetime(2026, 4, 28, 1, 1, tzinfo=UTC),
        )

    with pytest.raises(InvalidSchedule):
        compute_next_fire_after_success(
            recurring,
            scheduled_for=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
            now=datetime(2026, 4, 28, 1, 1),
        )


def test_rejects_invalid_timezone():
    with pytest.raises(InvalidSchedule):
        validate_timezone("Not/AZone")

    with pytest.raises(InvalidSchedule):
        build_schedule_from_anchor(
            anchor_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
            timezone="Not/AZone",
            rrule=None,
        )


@pytest.mark.parametrize(
    "modifier",
    [
        "BYHOUR=9",
        "BYMINUTE=30",
        "BYMONTH=4",
        "BYMONTHDAY=29",
        "BYSETPOS=1",
        "BYWEEKNO=17",
        "BYYEARDAY=119",
        "WKST=MO",
        "EXDATE=20260429T010000Z",
        "RDATE=20260429T010000Z",
    ],
)
def test_rejects_unsupported_rrule_modifiers(modifier):
    with pytest.raises(RRULENotSupported):
        validate_rrule_subset(f"FREQ=DAILY;{modifier}")


def test_validates_until_must_be_utc_datetime():
    assert (
        validate_rrule_subset("FREQ=DAILY;UNTIL=20260501T000000Z")
        == "FREQ=DAILY;UNTIL=20260501T000000Z"
    )

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=DAILY;UNTIL=2026-05-01")

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=DAILY;UNTIL=20260501T000000")


def test_rejects_non_weekly_or_invalid_byday():
    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=DAILY;BYDAY=MO")

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=WEEKLY;BYDAY=MONDAY")


def test_recurring_schedule_preserves_floating_local_time_across_dst():
    schedule = build_schedule_from_anchor(
        anchor_at=datetime(2026, 3, 7, 14, 0, tzinfo=UTC),
        timezone="America/New_York",
        rrule="FREQ=DAILY",
    )

    assert schedule.local_date == date(2026, 3, 7)
    assert schedule.local_time == time(9, 0)
    assert compute_initial_next_fire_at(
        schedule,
        now=datetime(2026, 3, 7, 15, 0, tzinfo=UTC),
    ) == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)


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
