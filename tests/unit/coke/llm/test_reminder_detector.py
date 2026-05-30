from __future__ import annotations

from datetime import UTC, datetime

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
            "recurrence_rule": {"freq": "monthly", "interval": 1},
            "duration_minutes": 30,
            "kind": "recurring",
        }
    )
    detector = SiliconFlowReminderDetector(client)
    now = datetime(2026, 5, 30, 10, 0, tzinfo=UTC)

    fields = detector.extract("remind me to pay rent monthly", "Asia/Tokyo", now)

    assert fields.content == "pay rent"
    assert fields.trigger_time == datetime.fromisoformat("2026-06-01T09:00:00+09:00")
    assert fields.recurrence_rule == {"freq": "monthly", "interval": 1}
    assert fields.duration_minutes == 30
    assert fields.kind == "recurring"
    assert client.calls[0]["schema_name"] == "detected_reminder_fields"
    assert client.calls[0]["user"]["captured_timezone"] == "Asia/Tokyo"


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
