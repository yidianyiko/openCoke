from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from util.time_util import get_default_timezone, parse_relative_time


def _build_parse_result(
    dtstart: datetime,
    *,
    schedule_kind: str,
    fixed_timezone: bool = False,
) -> dict[str, object]:
    return {
        "dtstart": dtstart,
        "schedule_kind": schedule_kind,
        "fixed_timezone": fixed_timezone,
    }


def _parse_hour_minute(match: re.Match[str]) -> tuple[int, int]:
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    period = match.group("period") or ""

    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0

    return hour, minute


def _parse_named_local_time(
    trigger_time: str,
    *,
    resolved_tz: ZoneInfo,
    base_timestamp: int | None,
) -> datetime | None:
    if base_timestamp is None:
        base_dt = datetime.now(tz=resolved_tz)
    else:
        base_dt = datetime.fromtimestamp(base_timestamp, tz=resolved_tz)

    day_offsets = {
        "今天": 0,
        "今晚": 0,
        "明天": 1,
        "后天": 2,
    }
    for day_label, day_offset in day_offsets.items():
        match = re.search(
            rf"{day_label}"
            r"(?:(?P<period>凌晨|早上|上午|中午|下午|晚上))?"
            r"(?P<hour>\d{1,2})"
            r"(?:[:点时](?P<minute>\d{1,2}))?"
            r"分?",
            trigger_time,
        )
        if not match:
            continue
        hour, minute = _parse_hour_minute(match)
        target_date = base_dt.date() + timedelta(days=day_offset)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=resolved_tz,
        )
    return None


def _parse_absolute_delay(
    trigger_time: str,
    *,
    resolved_tz: ZoneInfo,
    base_timestamp: int | None,
) -> datetime | None:
    if not re.search(r"\d+\s*(分钟|小时|钟头|天)[后之]后?", trigger_time):
        return None

    relative_timestamp = parse_relative_time(
        trigger_time,
        base_timestamp=base_timestamp,
        tz=resolved_tz,
    )
    if relative_timestamp is None:
        return None
    return datetime.fromtimestamp(relative_timestamp, tz=resolved_tz)


def parse_visible_reminder_time(
    trigger_time: str,
    *,
    timezone: str | None = None,
    base_timestamp: int | None = None,
) -> dict[str, object]:
    if not trigger_time:
        raise ValueError("trigger_time is required")

    resolved_tz = ZoneInfo(timezone) if timezone else get_default_timezone()

    try:
        parsed = datetime.fromisoformat(trigger_time)
    except ValueError:
        parsed = None

    if parsed is not None:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=resolved_tz)
        else:
            parsed = parsed.astimezone(resolved_tz)
        return _build_parse_result(parsed, schedule_kind="floating_local")

    absolute_delay = _parse_absolute_delay(
        trigger_time,
        resolved_tz=resolved_tz,
        base_timestamp=base_timestamp,
    )
    if absolute_delay is not None:
        return _build_parse_result(absolute_delay, schedule_kind="absolute_delay")

    named_local = _parse_named_local_time(
        trigger_time,
        resolved_tz=resolved_tz,
        base_timestamp=base_timestamp,
    )
    if named_local is not None:
        return _build_parse_result(named_local, schedule_kind="floating_local")

    relative_timestamp = parse_relative_time(
        trigger_time,
        base_timestamp=base_timestamp,
        tz=resolved_tz,
    )
    if relative_timestamp is not None:
        return _build_parse_result(
            datetime.fromtimestamp(relative_timestamp, tz=resolved_tz),
            schedule_kind="floating_local",
        )

    raise ValueError(f"Unsupported trigger_time format: {trigger_time}")
