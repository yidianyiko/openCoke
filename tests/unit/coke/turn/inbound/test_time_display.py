from __future__ import annotations

from datetime import UTC, datetime

from coke.turn.inbound.time_display import (
    attach_time_display_fields,
    format_time_friendly,
)


def test_format_time_friendly_renders_tomorrow_from_trusted_now() -> None:
    now = datetime.fromisoformat("2026-06-14T21:17:00+08:00")
    value = datetime(2026, 6, 15, 6, 0)

    assert (
        format_time_friendly(value, now=now, timezone_name="Asia/Shanghai")
        == "明天上午6点"
    )


def test_format_time_friendly_converts_utc_instant_to_user_timezone() -> None:
    now = datetime.fromisoformat("2026-06-14T21:17:00+08:00")
    value = datetime(2026, 6, 14, 22, 0, tzinfo=UTC)

    assert (
        format_time_friendly(value, now=now, timezone_name="Asia/Shanghai")
        == "明天上午6点"
    )


def test_format_time_friendly_uses_weekday_within_seven_days() -> None:
    now = datetime.fromisoformat("2026-06-14T21:17:00+08:00")
    value = datetime(2026, 6, 18, 15, 30)

    assert (
        format_time_friendly(value, now=now, timezone_name="Asia/Shanghai")
        == "星期四下午3点30分"
    )


def test_format_time_friendly_uses_month_day_after_week_window() -> None:
    now = datetime.fromisoformat("2026-06-14T21:17:00+08:00")
    value = datetime(2026, 6, 22, 20, 5)

    assert (
        format_time_friendly(value, now=now, timezone_name="Asia/Shanghai")
        == "6月22日晚上8点5分"
    )


def test_attach_time_display_fields_decorates_availability_windows() -> None:
    decorated = attach_time_display_fields(
        {
            "availability": [
                {
                    "friend_display_name": "Oliver",
                    "windows": [
                        {
                            "state": "free",
                            "start": "2026-06-15T09:00:00",
                            "end": "2026-06-15T10:30:00",
                        }
                    ],
                }
            ],
        },
        now="2026-06-14T21:17:00+08:00",
        timezone_name="Asia/Shanghai",
    )

    window = decorated["availability"][0]["windows"][0]
    assert window["start"] == "2026-06-15T09:00:00"
    assert window["start_display"] == "明天上午9点"
    assert window["end_display"] == "明天上午10点30分"
