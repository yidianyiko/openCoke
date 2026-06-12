from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.models import ReminderKind

SUPPORTED_RECURRENCE_FREQUENCIES = {"hourly", "daily", "weekly", "monthly", "yearly"}
SUPPORTED_REMINDER_KINDS: set[ReminderKind] = {
    "timed",
    "no_trigger_time",
    "recurring",
    "proactive",
    "shared_projection",
}
_RECURRENCE_KEYS = {"frequency", "interval", "window_start", "window_end"}
_INTERNAL_STORAGE_DURATION_MINUTES = 15


class ReminderTemporalError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReminderTemporalFields:
    kind: ReminderKind
    trigger_time: datetime | None
    recurrence_rule: dict[str, Any]
    duration_minutes: int


def canonical_recurrence_rule(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReminderTemporalError("invalid_recurrence_rule")
    if not value:
        return {}
    if set(value) - _RECURRENCE_KEYS:
        raise ReminderTemporalError("invalid_recurrence_rule")
    frequency = value.get("frequency")
    if not isinstance(frequency, str):
        raise ReminderTemporalError("invalid_recurrence_rule")
    normalized_frequency = frequency.strip().lower()
    if normalized_frequency not in SUPPORTED_RECURRENCE_FREQUENCIES:
        raise ReminderTemporalError("invalid_recurrence_rule")
    rule: dict[str, Any] = {
        "frequency": normalized_frequency,
        "interval": positive_int(value.get("interval", 1), "invalid_recurrence_rule"),
    }
    if "window_start" in value:
        rule["window_start"] = canonical_window_time(value["window_start"])
    if "window_end" in value:
        rule["window_end"] = canonical_window_time(value["window_end"])
    return rule


def positive_duration_minutes(value: Any) -> int:
    return positive_int(value, "invalid_duration_minutes")


def positive_int(value: Any, code: str) -> int:
    if isinstance(value, bool):
        raise ReminderTemporalError(code)
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ReminderTemporalError(code)
    if number < 1:
        raise ReminderTemporalError(code)
    return number


def canonical_window_time(value: Any) -> str:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0).strftime("%H:%M")
    if not isinstance(value, str):
        raise ReminderTemporalError("invalid_recurrence_rule")
    try:
        hour, minute = value.split(":", 1)
        hour_number = int(hour)
        minute_number = int(minute)
    except ValueError as error:
        raise ReminderTemporalError("invalid_recurrence_rule") from error
    if not (0 <= hour_number <= 23 and 0 <= minute_number <= 59):
        raise ReminderTemporalError("invalid_recurrence_rule")
    return f"{hour_number:02d}:{minute_number:02d}"


def normalize_create_temporal(
    *,
    trigger_time: datetime | None,
    recurrence_rule: Any,
    duration_minutes: Any | None,
    kind: Any | None,
) -> ReminderTemporalFields:
    canonical_rule = canonical_recurrence_rule(recurrence_rule)
    resolved_kind = _resolve_create_kind(kind, trigger_time, canonical_rule)

    if resolved_kind == "recurring":
        if not canonical_rule:
            raise ReminderTemporalError("missing_recurrence_rule")
        if trigger_time is None:
            raise ReminderTemporalError("missing_recurring_trigger_time")
    elif canonical_rule:
        raise ReminderTemporalError("invalid_recurrence_rule")

    if resolved_kind == "timed" and trigger_time is None:
        raise ReminderTemporalError("missing_trigger_time")
    if resolved_kind == "no_trigger_time" and trigger_time is not None:
        raise ReminderTemporalError("invalid_trigger_time")

    parsed_duration = (
        positive_duration_minutes(duration_minutes)
        if duration_minutes is not None
        else None
    )
    if _calendar_visible_create(resolved_kind, trigger_time):
        if parsed_duration is None:
            raise ReminderTemporalError("missing_duration_minutes")
        storage_duration = parsed_duration
    else:
        storage_duration = (
            parsed_duration
            if parsed_duration is not None
            else _INTERNAL_STORAGE_DURATION_MINUTES
        )

    return ReminderTemporalFields(
        kind=resolved_kind,
        trigger_time=trigger_time,
        recurrence_rule=canonical_rule,
        duration_minutes=storage_duration,
    )


def trigger_time_to_utc(
    trigger_time: datetime | None,
    captured_timezone: str,
) -> datetime | None:
    if trigger_time is None:
        return None
    try:
        zone = ZoneInfo(captured_timezone)
    except ZoneInfoNotFoundError as error:
        raise ReminderTemporalError("invalid_captured_timezone") from error
    if trigger_time.tzinfo is None:
        trigger_time = trigger_time.replace(tzinfo=zone)
    return trigger_time.astimezone(UTC)


def _resolve_create_kind(
    kind: Any | None,
    trigger_time: datetime | None,
    recurrence_rule: Mapping[str, Any],
) -> ReminderKind:
    if kind is not None:
        if kind not in SUPPORTED_REMINDER_KINDS:
            raise ReminderTemporalError("invalid_reminder_kind")
        return kind
    if recurrence_rule:
        return "recurring"
    if trigger_time is None:
        return "no_trigger_time"
    return "timed"


def _calendar_visible_create(
    kind: ReminderKind,
    trigger_time: datetime | None,
) -> bool:
    return kind not in {"no_trigger_time", "proactive"} and trigger_time is not None
