from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from dateutil.rrule import rrulestr


def _ensure_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def parse_rrule(dtstart: datetime, rrule: str):
    _ensure_aware(dtstart, "dtstart")
    return rrulestr(rrule, dtstart=dtstart)


def compute_initial_next_run_at(action: dict[str, Any], now: datetime) -> datetime | None:
    now = _ensure_aware(now, "now")
    dtstart = _ensure_aware(action["dtstart"], "dtstart")
    recurrence = action.get("rrule")

    if not recurrence:
        return dtstart if dtstart > now else now

    rule = parse_rrule(dtstart, recurrence)
    if rule.before(now, inc=True) is not None:
        return now
    return rule.after(now, inc=True)


def compute_next_run_after_success(
    action: dict[str, Any],
    scheduled_for: datetime,
    now: datetime,
) -> datetime | None:
    scheduled_for = _ensure_aware(scheduled_for, "scheduled_for")
    now = _ensure_aware(now, "now")

    recurrence = action.get("rrule")
    if not recurrence:
        return None

    run_count = action.get("run_count", 0)
    max_runs = action.get("max_runs")
    if max_runs is not None and run_count + 1 >= max_runs:
        return None

    dtstart = _ensure_aware(action["dtstart"], "dtstart")
    rule = parse_rrule(dtstart, recurrence)
    effective_time = max(scheduled_for, now)
    next_occurrence = rule.after(effective_time, inc=False)
    if next_occurrence is None:
        return None

    expires_at = action.get("expires_at")
    if expires_at is not None:
        expires_at = _ensure_aware(expires_at, "expires_at")
        if next_occurrence > expires_at:
            return None

    return next_occurrence


def compute_retry_at(
    action: dict[str, Any],
    attempt_count: int,
    now: datetime,
) -> datetime:
    now = _ensure_aware(now, "now")
    retry_policy = action["retry_policy"]
    base_backoff = retry_policy["base_backoff_seconds"]
    max_backoff = retry_policy["max_backoff_seconds"]
    backoff_seconds = min(base_backoff * (2 ** max(attempt_count - 1, 0)), max_backoff)
    return now + timedelta(seconds=backoff_seconds)


def should_terminally_fail_occurrence(action: dict[str, Any], attempt_count: int) -> bool:
    retry_policy = action["retry_policy"]
    return attempt_count >= retry_policy["max_attempts_per_occurrence"]
