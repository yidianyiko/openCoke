from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from coke.domains.reminder.models import DetectedReminderFields, ReminderKind
from coke.llm.semantic_interpreter import (
    AgnoJSONCompletionClient,
    JSONCompletionClient,
    LLMOutputError,
)

REMINDER_KINDS: set[ReminderKind] = {
    "timed",
    "no_trigger_time",
    "recurring",
    "proactive",
    "shared_projection",
}


class SiliconFlowReminderDetector:
    def __init__(self, client: JSONCompletionClient) -> None:
        self.client = client

    @classmethod
    def from_model(cls, model) -> SiliconFlowReminderDetector:
        return cls(AgnoJSONCompletionClient(model))

    def extract(
        self,
        text: str,
        captured_timezone: str,
        now: datetime,
    ) -> DetectedReminderFields:
        payload = self.client.complete_json(
            system=(
                "Extract precise reminder fields for Coke. Return only trusted JSON. "
                "Use {} for one-time or non-recurring reminders; recurrence_rule must never be null. "
                "Do not repair output with regex, normalize guessed durations, or "
                "rewrite past/incomplete times."
            ),
            user={
                "text": text,
                "captured_timezone": captured_timezone,
                "now": now.isoformat(),
                "allowed_kind": sorted(REMINDER_KINDS),
                "schema": {
                    "content": "string|null",
                    "trigger_time": "ISO-8601 datetime|null",
                    "recurrence_rule": "object; use {} for non-recurring reminders; never null",
                    "duration_minutes": "integer|null",
                    "kind": "timed|no_trigger_time|recurring|proactive|shared_projection|null",
                },
            },
            schema_name="detected_reminder_fields",
        )
        return DetectedReminderFields(
            content=_optional_str(payload.get("content"), "content"),
            trigger_time=_optional_datetime(payload.get("trigger_time")),
            recurrence_rule=_dict_field(payload.get("recurrence_rule")),
            duration_minutes=_optional_int(
                payload.get("duration_minutes"),
                "duration_minutes",
            ),
            kind=_optional_kind(payload.get("kind")),
        )


def _optional_str(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise LLMOutputError(f"invalid {field}")


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LLMOutputError("invalid trigger_time")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise LLMOutputError("invalid trigger_time") from error


def _dict_field(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raise LLMOutputError("invalid recurrence_rule")


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise LLMOutputError(f"invalid {field}")
    if isinstance(value, int):
        return value
    raise LLMOutputError(f"invalid {field}")


def _optional_kind(value: Any) -> ReminderKind | None:
    if value is None:
        return None
    if value in REMINDER_KINDS:
        return value
    raise LLMOutputError("invalid kind")
