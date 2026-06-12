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
RECURRENCE_FREQUENCIES = {"hourly", "daily", "weekly", "monthly", "yearly"}


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
                "For recurring reminders, recurrence_rule must use Coke's canonical "
                "runtime shape with frequency and interval, for example "
                "{'frequency':'weekly','interval':1}; do not use RRULE-style keys "
                "such as freq, byday, hour, or minute in final output. "
                "Recurring reminders must include the first concrete trigger_time "
                "computed from the authoritative local now. For expressions like "
                "每周一早上9点 or every Monday at 9 AM, choose the next matching "
                "future occurrence as trigger_time without asking which week. "
                "Field-specific examples: Positive examples include explicit times like "
                "'明天早上9点跑步' -> timed with trigger_time, and batch requests like "
                "'提醒我买牛奶，也提醒我给妈妈打电话' -> separate batch items at the tool "
                "caller layer while each item keeps its own fields. Negative examples: "
                "vague time expressions 待会/晚点/过一会 must not become a concrete "
                "trigger_time; return missing trigger_time so the domain can request "
                "needs_time clarification. In a follow-up loop, a follow-up that only "
                "supplies the missing time may complete the recently requested reminder; "
                "a new topic does not reopen an already-confirmed reminder. "
                "duration_minutes must be a positive integer estimate for reminder "
                "tasks. Use an explicit duration or time range when present; when "
                "the user omits duration, infer a reasonable approximate duration "
                "from the task content and context instead of leaving it null or "
                "using a fixed default. Do not repair output with regex, hardcode "
                "duration defaults, or "
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
                    "recurrence_rule": (
                        "object; use {} for non-recurring reminders; recurring shape is "
                        "{'frequency':'hourly|daily|weekly|monthly|yearly','interval':positive integer}; never null"
                    ),
                    "duration_minutes": "positive integer estimated minutes for reminder tasks; null only when no reminder item is present",
                    "kind": "timed|no_trigger_time|recurring|proactive|shared_projection|null",
                },
            },
            schema_name="detected_reminder_fields",
        )
        trigger_time = _optional_datetime(payload.get("trigger_time"))
        recurrence_rule = _recurrence_rule(payload.get("recurrence_rule"))
        kind = _optional_kind(payload.get("kind"))
        _validate_detected_combination(
            trigger_time=trigger_time,
            recurrence_rule=recurrence_rule,
            kind=kind,
        )
        return DetectedReminderFields(
            content=_optional_str(payload.get("content"), "content"),
            trigger_time=trigger_time,
            recurrence_rule=recurrence_rule,
            duration_minutes=_optional_int(
                payload.get("duration_minutes"),
                "duration_minutes",
            ),
            kind=kind,
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


def _recurrence_rule(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LLMOutputError("invalid recurrence_rule")
    if not value:
        return {}
    if "frequency" in value:
        frequency = _recurrence_frequency(value.get("frequency"))
    elif "freq" in value:
        frequency = _recurrence_frequency(value.get("freq"))
    else:
        raise LLMOutputError("invalid recurrence_rule")
    rule: dict[str, Any] = {
        "frequency": frequency,
        "interval": _positive_int(
            value.get("interval", 1),
            "recurrence_rule.interval",
        ),
    }
    if "window_start" in value:
        rule["window_start"] = _window_time(value.get("window_start"), "window_start")
    if "window_end" in value:
        rule["window_end"] = _window_time(value.get("window_end"), "window_end")
    return rule


def _recurrence_frequency(value: Any) -> str:
    if not isinstance(value, str):
        raise LLMOutputError("invalid recurrence_rule.frequency")
    frequency = value.strip().lower()
    if frequency in RECURRENCE_FREQUENCIES:
        return frequency
    raise LLMOutputError("invalid recurrence_rule")


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise LLMOutputError(f"invalid {field}")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise LLMOutputError(f"invalid {field}")
    if number < 1:
        raise LLMOutputError(f"invalid {field}")
    return number


def _window_time(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise LLMOutputError(f"invalid recurrence_rule.{field}")
    try:
        hour, minute = value.split(":", 1)
        if len(hour) != 2 or len(minute) != 2:
            raise ValueError
        hour_number = int(hour)
        minute_number = int(minute)
    except ValueError as error:
        raise LLMOutputError(f"invalid recurrence_rule.{field}") from error
    if not (0 <= hour_number <= 23 and 0 <= minute_number <= 59):
        raise LLMOutputError(f"invalid recurrence_rule.{field}")
    return value


def _validate_detected_combination(
    *,
    trigger_time: datetime | None,
    recurrence_rule: dict[str, Any],
    kind: ReminderKind | None,
) -> None:
    if recurrence_rule:
        if trigger_time is None:
            raise LLMOutputError("invalid recurring trigger_time")
        if kind not in (None, "recurring"):
            raise LLMOutputError("invalid recurring kind")
    elif kind == "recurring":
        raise LLMOutputError("invalid recurring recurrence_rule")


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
