from datetime import UTC, datetime, timedelta

from tools.agent_smoke._runner_phase_recurring_reminder import (
    DELIVERY_GAP_NOTE,
    _validate_recurring_reminder,
)


def test_validate_recurring_reminder_accepts_daily_shape():
    now = datetime(2026, 5, 25, 1, 0, tzinfo=UTC)
    reminder = {
        "title": "喝杯水",
        "lifecycle_state": "active",
        "schedule": {
            "local_time": "08:00:00",
            "timezone": "Asia/Shanghai",
            "rrule": "FREQ=DAILY",
        },
        "next_fire_at": now + timedelta(days=1),
    }

    problems, notes = _validate_recurring_reminder(reminder, now=now)

    assert problems == []
    assert DELIVERY_GAP_NOTE in notes


def test_validate_recurring_reminder_rejects_non_recurring_or_stale_schedule():
    now = datetime(2026, 5, 25, 1, 0, tzinfo=UTC)
    reminder = {
        "title": "喝杯水",
        "lifecycle_state": "active",
        "schedule": {
            "local_time": "08:00:00",
            "timezone": "Asia/Tokyo",
        },
        "next_fire_at": now - timedelta(minutes=1),
    }

    problems, _ = _validate_recurring_reminder(reminder, now=now)

    assert "recurrence_missing_daily" in problems
    assert "timezone_mismatch: Asia/Tokyo" in problems
    assert "next_fire_at_not_future" in problems
