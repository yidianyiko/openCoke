from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.models import DetectedReminderFields, ReminderKind
from coke.llm.json_completion import (
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
        try:
            zone = ZoneInfo(captured_timezone)
        except ZoneInfoNotFoundError as error:
            raise LLMOutputError("invalid captured_timezone") from error
        local_now = (
            now.astimezone(zone) if now.tzinfo is not None else now.replace(tzinfo=zone)
        )
        payload = self.client.complete_json(
            system=(
                "Extract precise reminder fields for Coke. Return only trusted JSON. "
                "Use {} for one-time or non-recurring reminders; recurrence_rule must never be null. "
                "Interpret reminder dates and times in captured_timezone. The provided "
                "now value is the authoritative current datetime in captured_timezone. "
                "Relative expressions such as 明天, 后天, 下周, 中午, 早上, 晚上, "
                "tomorrow, next week, noon, morning, and evening must be computed from "
                "that authoritative local now; never invent dates from model priors. "
                "Preserve explicit hour and minute from the user's request; for example, "
                "tomorrow 9 AM must return tomorrow at 09:00 in captured_timezone, not midnight. "
                "Field-specific examples: Positive examples include explicit times like "
                "'明天早上9点跑步' -> timed with trigger_time, and batch requests like "
                "'提醒我买牛奶，也提醒我给妈妈打电话' -> separate batch items at the tool "
                "caller layer while each item keeps its own fields. Negative examples: "
                "vague time expressions 待会/晚点/过一会 must not become a concrete "
                "trigger_time; return missing trigger_time so the domain can request "
                "needs_time clarification. In a follow-up loop, a follow-up that only "
                "supplies the missing time may complete the recently requested reminder; "
                "a new topic does not reopen an already-confirmed reminder. "
                "Do not repair output with regex, normalize guessed durations, or "
                "rewrite past/incomplete times."
            ),
            user={
                "text": text,
                "captured_timezone": captured_timezone,
                "now": local_now.isoformat(),
                "current_local_date": local_now.date().isoformat(),
                "current_local_time": local_now.time()
                .replace(microsecond=0)
                .isoformat(),
                "allowed_kind": sorted(REMINDER_KINDS),
                "schema": {
                    "content": "string|null",
                    "trigger_time": "full ISO-8601 local wall-clock datetime in captured_timezone, including explicit hour/minute",
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
