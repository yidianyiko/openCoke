from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def next_occurrence_after(
    recurrence_rule: dict,
    previous_fire_at: datetime,
    captured_timezone: str,
) -> datetime:
    if not recurrence_rule:
        raise ValueError("recurrence_rule_required")
    frequency = recurrence_rule.get("frequency")
    interval = int(recurrence_rule.get("interval", 1))
    if interval < 1:
        raise ValueError("invalid_recurrence_interval")
    if frequency not in {"hourly", "daily", "weekly", "monthly", "yearly"}:
        raise ValueError("unsupported_recurrence_frequency")
    zone = ZoneInfo(captured_timezone)
    local_previous = previous_fire_at.astimezone(zone)
    local_next = _add_interval(local_previous, frequency, interval)
    if frequency == "hourly":
        local_next = _fit_hourly_window(local_next, recurrence_rule)
    return local_next.astimezone(ZoneInfo("UTC"))


def occurrences_between(
    recurrence_rule: dict,
    first_occurrence_at: datetime,
    captured_timezone: str,
    start: datetime,
    end: datetime,
    limit: int = 256,
) -> list[datetime]:
    occurrences: list[datetime] = []
    current = first_occurrence_at
    while current < start and len(occurrences) < limit:
        current = next_occurrence_after(recurrence_rule, current, captured_timezone)
    while start <= current <= end and len(occurrences) < limit:
        occurrences.append(current)
        current = next_occurrence_after(recurrence_rule, current, captured_timezone)
    return occurrences


def _add_interval(value: datetime, frequency: str, interval: int) -> datetime:
    if frequency == "hourly":
        return value + timedelta(hours=interval)
    if frequency == "daily":
        return value + timedelta(days=interval)
    if frequency == "weekly":
        return value + timedelta(weeks=interval)
    if frequency == "monthly":
        month_index = value.month - 1 + interval
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        return value.replace(year=year, month=month)
    if frequency == "yearly":
        return value.replace(year=value.year + interval)
    raise ValueError("unsupported_recurrence_frequency")


def _fit_hourly_window(value: datetime, recurrence_rule: dict) -> datetime:
    start = _rule_time(recurrence_rule.get("window_start"), time(8, 0))
    end = _rule_time(recurrence_rule.get("window_end"), time(23, 0))
    local_time = value.timetz().replace(tzinfo=None)
    if start <= local_time <= end:
        return value
    next_day = value.date() + timedelta(days=1)
    return datetime.combine(next_day, start, tzinfo=value.tzinfo)


def _rule_time(value, default: time) -> time:
    if value is None:
        return default
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute))
    raise ValueError("invalid_window_time")
