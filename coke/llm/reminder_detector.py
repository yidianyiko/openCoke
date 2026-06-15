from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.models import DetectedReminderFields, ReminderKind
from coke.domains.reminder.temporal import (
    ReminderTemporalError,
    canonical_recurrence_rule,
    positive_duration_minutes,
)
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
        fields = self.extract_many(text, captured_timezone, now)
        if len(fields) == 1:
            return fields[0]
        raise LLMOutputError("invalid detected_reminder_fields shape")

    def extract_many(
        self,
        text: str,
        captured_timezone: str,
        now: datetime,
    ) -> list[DetectedReminderFields]:
        try:
            zone = ZoneInfo(captured_timezone)
        except ZoneInfoNotFoundError as error:
            raise LLMOutputError("invalid captured_timezone") from error
        local_now = (
            now.astimezone(zone) if now.tzinfo is not None else now.replace(tzinfo=zone)
        )
        payloads = _complete_payloads(
            self.client,
            system=_system_prompt(),
            user={
                "text": text,
                "captured_timezone": captured_timezone,
                "now": local_now.isoformat(),
                "current_local_date": local_now.date().isoformat(),
                "current_local_time": local_now.time()
                .replace(microsecond=0)
                .isoformat(),
                "allowed_kind": sorted(REMINDER_KINDS),
                "schema": _schema_prompt(),
            },
        )
        return [_detected_fields_from_payload(payload) for payload in payloads]


def _complete_payloads(
    client: JSONCompletionClient,
    *,
    system: str,
    user: dict,
) -> list[Mapping[str, Any]]:
    complete_json_list = getattr(client, "complete_json_list", None)
    if callable(complete_json_list):
        payloads = complete_json_list(
            system=system,
            user=user,
            schema_name="detected_reminder_fields",
        )
    else:
        payloads = [
            client.complete_json(
                system=system,
                user=user,
                schema_name="detected_reminder_fields",
            )
        ]
    if not payloads:
        raise LLMOutputError("invalid detected_reminder_fields shape")
    return list(payloads)


def _detected_fields_from_payload(payload: Mapping[str, Any]) -> DetectedReminderFields:
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


def _system_prompt() -> str:
    return (
        "Extract precise reminder fields for Coke. Return only trusted JSON. "
        "Return exactly one of these top-level JSON shapes and nothing else: "
        "a single JSON object for one reminder, or a JSON array of reminder "
        "objects for multiple reminders. Do not return scalar values. "
        "Do not add wrapper keys such as reminders or data. Do not include "
        "prose or markdown fences. "
        "Use {} for one-time or non-recurring reminders; recurrence_rule must never be null. "
        "Interpret reminder dates and times in captured_timezone. The provided "
        "now value is the authoritative current datetime in captured_timezone. "
        "Relative expressions such as 明天, 后天, 下周, 中午, 早上, 晚上, "
        "tomorrow, next week, noon, morning, and evening must be computed from "
        "that authoritative local now; never invent dates from model priors. "
        "A determinate relative offset such as 过N分钟/小时, N分钟后/小时后, "
        "半小时后, or in N minutes/hours is always computable from the provided "
        "now: set trigger_time to the authoritative local now plus the stated "
        "offset, preserving captured_timezone, and never ask the user to restate "
        "the start time. "
        "Chinese week expressions use Monday as the first day of the week, "
        "never Sunday. For 下周/next-week weekday phrases, compute the target "
        "weekday in the next Monday-start calendar week from authoritative "
        "local now: 下周一 from a Sunday local now means tomorrow, not the "
        "Monday eight days later. Example: with now=2026-06-14T13:28:00+08:00 "
        "in Asia/Shanghai, 下周一早上9点 means 2026-06-15T09:00:00+08:00. "
        "Explicit period-of-day markers are authoritative: 晚上/下午 and "
        "evening/afternoon mean PM; 早上/上午 and morning mean AM; 中午/noon "
        "means 12:00/noon. When such a marker is present, do not use the "
        "near-future heuristic to flip AM/PM; preserve the marker's AM/PM "
        "even if another reading would be sooner. "
        "Preserve explicit hour and minute from the user's request; for example, "
        "tomorrow 9 AM must return tomorrow at 09:00 in captured_timezone, not midnight. "
        "When the user gives an ambiguous hour or hour-range without AM/PM (for "
        "example 8-9, 8点, 8到9点), choose the plausible near-future local time "
        "relative to the authoritative local now: if the morning reading is already "
        "past and an evening reading is plausible, prefer the evening reading. For "
        "example, at 14:52 local '今天8-9运动' means today 20:00-21:00, not "
        "08:00-09:00. Only return a time earlier than now when the user clearly "
        "meant the past (for example 今天早上8点); the domain will then ask the user "
        "to confirm the past time. "
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
        "For every timed or recurring reminder with a concrete trigger_time, "
        "duration_minutes must be a positive integer and must never be null. "
        "Use an explicit duration or time range when present; when the user "
        "omits duration, infer a reasonable approximate duration from the task "
        "content and context instead of leaving it null or using a fixed "
        "default. When trigger_time is null because the time phrase is vague, "
        "keep duration_minutes null so the domain clarifies time instead of "
        "duration. Do not repair output with regex, hardcode duration defaults, "
        "or rewrite past/incomplete times."
    )


def _schema_prompt() -> dict[str, str]:
    return {
        "content": "string|null",
        "trigger_time": "full ISO-8601 local wall-clock datetime in captured_timezone, including explicit hour/minute",
        "recurrence_rule": (
            "object; use {} for non-recurring reminders; recurring shape is "
            "{'frequency':'hourly|daily|weekly|monthly|yearly','interval':positive integer}; never null"
        ),
        "duration_minutes": (
            "positive integer estimated minutes for timed or recurring reminder tasks "
            "with concrete trigger_time; null only when no concrete trigger_time or "
            "no reminder item is present"
        ),
        "kind": "timed|no_trigger_time|recurring|proactive|shared_projection|null",
    }


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
    try:
        return canonical_recurrence_rule(value)
    except ReminderTemporalError as error:
        raise LLMOutputError("invalid recurrence_rule") from error


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
    if isinstance(value, bool) or not isinstance(value, int):
        raise LLMOutputError(f"invalid {field}")
    try:
        return positive_duration_minutes(value)
    except ReminderTemporalError as error:
        raise LLMOutputError(f"invalid {field}") from error


def _optional_kind(value: Any) -> ReminderKind | None:
    if value is None:
        return None
    if value in REMINDER_KINDS:
        return value
    raise LLMOutputError("invalid kind")
