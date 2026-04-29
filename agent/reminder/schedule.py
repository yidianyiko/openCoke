from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr

from agent.reminder.errors import InvalidSchedule, RRULENotSupported
from agent.reminder.models import ReminderSchedule

_SUPPORTED_FREQS = {"MINUTELY", "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
_SUPPORTED_KEYS = {
    "FREQ",
    "COUNT",
    "UNTIL",
    "INTERVAL",
    "BYDAY",
    "BYHOUR",
    "BYMINUTE",
}
_SUPPORTED_BYDAY = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}
_REJECTED_KEYS = {
    "BYMONTH",
    "BYMONTHDAY",
    "BYSETPOS",
    "BYWEEKNO",
    "BYYEARDAY",
    "WKST",
    "EXDATE",
    "RDATE",
}


def build_schedule_from_anchor(
    anchor_at: datetime,
    timezone: str,
    rrule: str | None,
) -> ReminderSchedule:
    anchor_at = _ensure_aware(anchor_at, "anchor_at").astimezone(UTC)
    timezone = validate_timezone(timezone)
    rrule = validate_rrule_subset(rrule)

    local_anchor = anchor_at.astimezone(ZoneInfo(timezone))
    return ReminderSchedule(
        anchor_at=anchor_at,
        local_date=local_anchor.date(),
        local_time=local_anchor.timetz().replace(tzinfo=None),
        timezone=timezone,
        rrule=rrule,
    )


def validate_timezone(timezone: str) -> str:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise InvalidSchedule(
            "Invalid reminder timezone",
            detail={"timezone": timezone},
        ) from exc
    return timezone


def validate_rrule_subset(rrule: str | None) -> str | None:
    if rrule is None:
        return None

    parts = _parse_rrule_parts(rrule)
    freq = parts.get("FREQ")
    if freq not in _SUPPORTED_FREQS:
        raise RRULENotSupported(
            "Unsupported reminder recurrence frequency",
            detail={"rrule": rrule},
        )

    unsupported_keys = (set(parts) - _SUPPORTED_KEYS) | (set(parts) & _REJECTED_KEYS)
    if unsupported_keys:
        raise RRULENotSupported(
            "Unsupported reminder recurrence modifier",
            detail={"rrule": rrule, "keys": sorted(unsupported_keys)},
        )

    if "BYDAY" in parts:
        if freq != "WEEKLY":
            raise RRULENotSupported(
                "BYDAY is only supported for weekly reminder recurrence",
                detail={"rrule": rrule},
            )
        days = parts["BYDAY"].split(",")
        if not days or any(day not in _SUPPORTED_BYDAY for day in days):
            raise RRULENotSupported(
                "Unsupported weekly BYDAY value",
                detail={"rrule": rrule},
            )

    if "BYMINUTE" in parts:
        if freq != "HOURLY":
            raise RRULENotSupported(
                "BYMINUTE is only supported for hourly reminder recurrence",
                detail={"rrule": rrule},
            )
        _validate_byminute(parts["BYMINUTE"], rrule)

    if "BYHOUR" in parts:
        if freq != "HOURLY":
            raise RRULENotSupported(
                "BYHOUR is only supported for hourly reminder recurrence",
                detail={"rrule": rrule},
            )
        _validate_byhour(parts["BYHOUR"], rrule)

    _validate_positive_integer(parts, "COUNT", rrule)
    _validate_positive_integer(parts, "INTERVAL", rrule)
    _validate_until(parts, rrule)
    return rrule


def compute_initial_next_fire_at(
    schedule: ReminderSchedule,
    now: datetime,
) -> datetime:
    now = _ensure_aware(now, "now").astimezone(UTC)
    anchor_at = _ensure_aware(schedule.anchor_at, "schedule.anchor_at").astimezone(UTC)
    validate_timezone(schedule.timezone)
    validate_rrule_subset(schedule.rrule)

    if schedule.rrule is None:
        if anchor_at <= now:
            raise InvalidSchedule(
                "One-shot reminder schedule must be in the future",
                detail={"reason": "past_one_shot"},
            )
        return anchor_at

    next_fire_at = _next_recurrence_after(schedule, now)
    if next_fire_at is None:
        raise InvalidSchedule(
            "Recurring reminder schedule has no future fire time",
            detail={"reason": "no_future_fire_time"},
        )
    return next_fire_at


def compute_next_fire_after_success(
    schedule: ReminderSchedule,
    scheduled_for: datetime,
    now: datetime,
) -> datetime | None:
    _ensure_aware(schedule.anchor_at, "schedule.anchor_at")
    _ensure_aware(scheduled_for, "scheduled_for")
    now = _ensure_aware(now, "now").astimezone(UTC)
    validate_timezone(schedule.timezone)
    validate_rrule_subset(schedule.rrule)

    if schedule.rrule is None:
        return None

    effective_time = max(scheduled_for.astimezone(UTC), now)
    return _next_recurrence_after(schedule, effective_time)


def _ensure_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidSchedule(
            "Reminder schedule datetime must be timezone-aware",
            detail={"field": field_name},
        )
    return value


def _parse_rrule_parts(rrule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for raw_part in rrule.split(";"):
        if "=" not in raw_part:
            raise RRULENotSupported(
                "Malformed reminder recurrence rule",
                detail={"rrule": rrule},
            )
        key, value = raw_part.split("=", 1)
        key = key.upper()
        value = value.upper()
        if not key or not value or key in parts:
            raise RRULENotSupported(
                "Malformed reminder recurrence rule",
                detail={"rrule": rrule},
            )
        parts[key] = value

    if "FREQ" not in parts:
        raise RRULENotSupported(
            "Reminder recurrence rule must include FREQ",
            detail={"rrule": rrule},
        )
    return parts


def _validate_positive_integer(parts: dict[str, str], key: str, rrule: str) -> None:
    value = parts.get(key)
    if value is None:
        return
    if not value.isdigit() or int(value) < 1:
        raise RRULENotSupported(
            "Reminder recurrence integer modifier must be positive",
            detail={"rrule": rrule, "key": key},
        )


def _validate_byminute(value: str, rrule: str) -> None:
    minutes = value.split(",")
    if not minutes:
        raise RRULENotSupported(
            "Unsupported hourly BYMINUTE value",
            detail={"rrule": rrule},
        )
    for minute in minutes:
        if not minute.isdigit() or int(minute) > 59:
            raise RRULENotSupported(
                "Unsupported hourly BYMINUTE value",
                detail={"rrule": rrule},
            )


def _validate_byhour(value: str, rrule: str) -> None:
    hours = value.split(",")
    if not hours:
        raise RRULENotSupported(
            "Unsupported hourly BYHOUR value",
            detail={"rrule": rrule},
        )
    for hour in hours:
        if not hour.isdigit() or int(hour) > 23:
            raise RRULENotSupported(
                "Unsupported hourly BYHOUR value",
                detail={"rrule": rrule},
            )


def _validate_until(parts: dict[str, str], rrule: str) -> None:
    value = parts.get("UNTIL")
    if value is None:
        return
    try:
        datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise RRULENotSupported(
            "Reminder recurrence UNTIL must be a UTC datetime",
            detail={"rrule": rrule},
        ) from exc


def _next_recurrence_after(
    schedule: ReminderSchedule,
    after: datetime,
) -> datetime | None:
    timezone = ZoneInfo(schedule.timezone)
    local_start = datetime.combine(
        date=schedule.local_date,
        time=schedule.local_time,
        tzinfo=timezone,
    )
    try:
        rule = rrulestr(schedule.rrule, dtstart=local_start)
    except (TypeError, ValueError) as exc:
        raise RRULENotSupported(
            "Malformed reminder recurrence rule",
            detail={"rrule": schedule.rrule},
        ) from exc

    next_fire_at = rule.after(after.astimezone(timezone), inc=False)
    if next_fire_at is None:
        return None
    return next_fire_at.astimezone(UTC)
