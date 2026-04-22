from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_parse_visible_reminder_time_marks_absolute_delay():
    from agent.agno_agent.tools.deferred_action.time_parser import (
        parse_visible_reminder_time,
    )

    parsed = parse_visible_reminder_time(
        "3小时后",
        timezone="Asia/Tokyo",
        base_timestamp=1770000000,
    )

    assert parsed["schedule_kind"] == "absolute_delay"
    assert parsed["fixed_timezone"] is False
    assert parsed["dtstart"] == datetime.fromtimestamp(
        1770000000 + 3 * 3600,
        tz=ZoneInfo("Asia/Tokyo"),
    )


def test_parse_visible_reminder_time_marks_floating_local_for_named_time():
    from agent.agno_agent.tools.deferred_action.time_parser import (
        parse_visible_reminder_time,
    )

    base_timestamp = 1770000000
    parsed = parse_visible_reminder_time(
        "明天早上9点",
        timezone="Asia/Tokyo",
        base_timestamp=base_timestamp,
    )
    expected_day = datetime.fromtimestamp(
        base_timestamp,
        tz=ZoneInfo("Asia/Tokyo"),
    ) + timedelta(days=1)

    assert parsed["schedule_kind"] == "floating_local"
    assert parsed["fixed_timezone"] is False
    assert parsed["dtstart"] == datetime(
        expected_day.year,
        expected_day.month,
        expected_day.day,
        9,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
