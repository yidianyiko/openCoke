from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from coke.llm.reminder_detector import LLMOutputError, SiliconFlowReminderDetector


class FakeJSONClient:
    def __init__(self, output) -> None:
        self.output = output
        self.calls = []

    def complete_json(self, *, system: str, user: dict, schema_name: str):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        return self.output


def test_extract_maps_structured_model_output_to_detected_reminder_fields():
    client = FakeJSONClient(
        {
            "content": "pay rent",
            "trigger_time": "2026-06-01T09:00:00+09:00",
            "recurrence_rule": {"frequency": "monthly", "interval": 1},
            "duration_minutes": 30,
            "kind": "recurring",
        }
    )
    detector = SiliconFlowReminderDetector(client)
    now = datetime(2026, 5, 30, 10, 0, tzinfo=UTC)

    fields = detector.extract("remind me to pay rent monthly", "Asia/Tokyo", now)

    assert fields.content == "pay rent"
    assert fields.trigger_time == datetime.fromisoformat("2026-06-01T09:00:00+09:00")
    assert fields.recurrence_rule == {"frequency": "monthly", "interval": 1}
    assert fields.duration_minutes == 30
    assert fields.kind == "recurring"
    assert client.calls[0]["schema_name"] == "detected_reminder_fields"
    assert client.calls[0]["user"]["captured_timezone"] == "Asia/Tokyo"


def test_extract_rejects_rrule_style_model_rule_without_runtime_repair():
    client = FakeJSONClient(
        {
            "content": "看一下项目进展",
            "trigger_time": "2026-06-15T09:00:00+08:00",
            "recurrence_rule": {
                "freq": "WEEKLY",
                "byday": ["MO"],
                "hour": 9,
                "minute": 0,
            },
            "duration_minutes": 20,
            "kind": "recurring",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    with pytest.raises(LLMOutputError, match="invalid recurrence_rule"):
        detector.extract(
            "每周一早上9点提醒我看一下项目进展",
            "Asia/Shanghai",
            datetime(2026, 6, 12, 13, 44, tzinfo=ZoneInfo("Asia/Shanghai")),
        )


def test_extract_accepts_weekly_model_rule_with_next_concrete_trigger():
    client = FakeJSONClient(
        {
            "content": "看一下项目进展",
            "trigger_time": "2026-06-15T09:00:00+08:00",
            "recurrence_rule": {"frequency": "weekly", "interval": 1},
            "duration_minutes": 20,
            "kind": "recurring",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    fields = detector.extract(
        "每周一早上9点提醒我看一下项目进展",
        "Asia/Shanghai",
        datetime(2026, 6, 12, 13, 44, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert fields.trigger_time == datetime.fromisoformat("2026-06-15T09:00:00+08:00")
    assert fields.recurrence_rule == {"frequency": "weekly", "interval": 1}
    assert fields.duration_minutes == 20
    assert fields.kind == "recurring"


def test_extract_rejects_recurring_output_without_first_trigger_time():
    client = FakeJSONClient(
        {
            "content": "看一下项目进展",
            "trigger_time": None,
            "recurrence_rule": {"frequency": "weekly", "interval": 1},
            "duration_minutes": 20,
            "kind": "recurring",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    with pytest.raises(LLMOutputError, match="invalid recurring trigger_time"):
        detector.extract(
            "每周一早上9点提醒我看一下项目进展",
            "Asia/Shanghai",
            datetime(2026, 6, 12, 13, 44, tzinfo=ZoneInfo("Asia/Shanghai")),
        )


def test_extract_prompt_requires_empty_recurrence_object_for_non_recurring_items():
    client = FakeJSONClient(
        {
            "content": "pay rent",
            "trigger_time": "2026-06-01T09:00:00+09:00",
            "recurrence_rule": {},
            "duration_minutes": None,
            "kind": "timed",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    detector.extract(
        "remind me to pay rent", "Asia/Tokyo", datetime(2026, 5, 30, 10, 0, tzinfo=UTC)
    )

    assert "Use {} for one-time or non-recurring reminders" in client.calls[0]["system"]
    assert "Recurring reminders must include the first concrete trigger_time" in (
        client.calls[0]["system"]
    )
    assert client.calls[0]["user"]["schema"]["recurrence_rule"] == (
        "object; use {} for non-recurring reminders; recurring shape is "
        "{'frequency':'hourly|daily|weekly|monthly|yearly','interval':positive integer}; never null"
    )


def test_extract_prompt_requires_full_local_wall_clock_time_in_captured_timezone():
    client = FakeJSONClient(
        {
            "content": "跑步",
            "trigger_time": "2026-05-31T09:00:00+09:00",
            "recurrence_rule": {},
            "duration_minutes": None,
            "kind": "timed",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    detector.extract(
        "提醒我明天早上9点跑步",
        "Asia/Tokyo",
        datetime(2026, 5, 30, 10, 10, tzinfo=UTC),
    )

    assert "Preserve explicit hour and minute" in client.calls[0]["system"]
    assert client.calls[0]["user"]["schema"]["trigger_time"] == (
        "full ISO-8601 local wall-clock datetime in captured_timezone, including explicit hour/minute"
    )


class ExplicitPeriodAuthoritativeClient:
    def __init__(self) -> None:
        self.calls = []

    def complete_json(self, *, system: str, user: dict, schema_name: str):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        assert user["text"] == "明天晚上六点开会"
        assert "晚上六点" in user["text"]
        hour = 18 if "Explicit period-of-day markers are authoritative" in system else 6
        return {
            "content": "开会",
            "trigger_time": datetime(
                2026,
                6,
                15,
                hour,
                0,
                tzinfo=ZoneInfo(user["captured_timezone"]),
            ).isoformat(),
            "recurrence_rule": {},
            "duration_minutes": 30,
            "kind": "shared_projection",
        }


def test_extract_honors_explicit_evening_marker_over_near_future_heuristic():
    detector = SiliconFlowReminderDetector(ExplicitPeriodAuthoritativeClient())

    fields = detector.extract(
        "明天晚上六点开会",
        "Asia/Shanghai",
        datetime(2026, 6, 14, 18, 3, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert fields.trigger_time == datetime(
        2026, 6, 15, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )


def test_extract_prompt_includes_field_specific_few_shot_boundaries():
    client = FakeJSONClient(
        {
            "content": "跑步",
            "trigger_time": None,
            "recurrence_rule": {},
            "duration_minutes": None,
            "kind": "no_trigger_time",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    detector.extract(
        "提醒我待会跑步",
        "Asia/Tokyo",
        datetime(2026, 5, 30, 10, 10, tzinfo=UTC),
    )

    system = client.calls[0]["system"]
    assert "待会/晚点/过一会" in system
    assert "must not become a concrete trigger_time" in system
    assert "batch" in system
    assert "a follow-up that only supplies the missing time" in system
    assert "new topic does not reopen" in system
    assert "Positive examples" in system
    assert "Negative examples" in system


class GroundedRelativeClient:
    def __init__(self) -> None:
        self.calls = []

    def complete_json(self, *, system: str, user: dict, schema_name: str):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        assert "authoritative current datetime" in system
        assert "Relative expressions" in system
        assert user["captured_timezone"] == "Asia/Shanghai"
        assert user["now"] == "2026-05-31T11:44:00+08:00"
        assert user["current_local_date"] == "2026-05-31"
        assert user["current_local_time"] == "11:44:00"
        tomorrow = datetime.combine(
            datetime.fromisoformat(user["current_local_date"]).date()
            + timedelta(days=1),
            time(12, 0) if "中午" in user["text"] else time(9, 0),
            tzinfo=ZoneInfo(user["captured_timezone"]),
        )
        return {
            "content": "午餐" if "午餐" in user["text"] else "跑步",
            "trigger_time": tomorrow.isoformat(),
            "recurrence_rule": {},
            "duration_minutes": None,
            "kind": "timed",
        }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "和我的好友约一个明天中午的午餐",
            datetime(2026, 6, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        ),
        (
            "提醒我明天早上9点跑步",
            datetime(2026, 6, 1, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        ),
    ],
)
def test_extract_grounds_relative_times_against_authoritative_local_now(text, expected):
    detector = SiliconFlowReminderDetector(GroundedRelativeClient())
    now = datetime(2026, 5, 31, 11, 44, tzinfo=ZoneInfo("Asia/Shanghai"))

    fields = detector.extract(text, "Asia/Shanghai", now)

    assert fields.trigger_time == expected


def test_extract_rejects_invalid_output_without_regex_recovery():
    client = FakeJSONClient(
        {
            "content": "pay rent at 9",
            "trigger_time": "tomorrow 9",
            "recurrence_rule": {},
            "duration_minutes": "30 minutes",
            "kind": "timed",
        }
    )
    detector = SiliconFlowReminderDetector(client)

    with pytest.raises(LLMOutputError, match="invalid trigger_time"):
        detector.extract(
            "remind me tomorrow at 9",
            "Asia/Tokyo",
            datetime(2026, 5, 30, 10, 0, tzinfo=UTC),
        )
