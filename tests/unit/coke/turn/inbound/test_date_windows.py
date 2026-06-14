from __future__ import annotations

from datetime import UTC, datetime

from coke.turn.inbound.date_windows import resolve_date_phrase_window

NOW = datetime(2026, 6, 14, 13, 26, tzinfo=UTC)


def test_resolve_date_phrase_window_maps_tomorrow_to_user_local_day() -> None:
    window = resolve_date_phrase_window(
        "明天",
        timezone_name="Asia/Shanghai",
        now=lambda: NOW,
    )

    assert window is not None
    assert window.local_start.isoformat() == "2026-06-15T00:00:00"
    assert window.local_end.isoformat() == "2026-06-16T00:00:00"
    assert window.trigger_after == datetime(2026, 6, 14, 16, 0, tzinfo=UTC)
    assert window.trigger_before == datetime(2026, 6, 15, 16, 0, tzinfo=UTC)


def test_resolve_date_phrase_window_maps_weekday_and_date_deterministically() -> None:
    monday = resolve_date_phrase_window(
        "周一",
        timezone_name="Asia/Shanghai",
        now=lambda: NOW,
    )
    explicit = resolve_date_phrase_window(
        "2026-06-15",
        timezone_name="Asia/Shanghai",
        now=lambda: NOW,
    )

    assert monday is not None
    assert explicit is not None
    assert monday.trigger_after == explicit.trigger_after
    assert monday.trigger_before == explicit.trigger_before
