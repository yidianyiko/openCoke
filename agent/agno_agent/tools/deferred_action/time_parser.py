from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from util.time_util import get_default_timezone, parse_relative_time


def parse_visible_reminder_time(
    trigger_time: str,
    *,
    timezone: str | None = None,
    base_timestamp: int | None = None,
) -> datetime:
    if not trigger_time:
        raise ValueError("trigger_time is required")

    resolved_tz = ZoneInfo(timezone) if timezone else get_default_timezone()

    try:
        parsed = datetime.fromisoformat(trigger_time)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=resolved_tz)
        return parsed.astimezone(resolved_tz)
    except ValueError:
        pass

    relative_timestamp = parse_relative_time(
        trigger_time,
        base_timestamp=base_timestamp,
        tz=resolved_tz,
    )
    if relative_timestamp is not None:
        return datetime.fromtimestamp(relative_timestamp, tz=resolved_tz)

    raise ValueError(f"Unsupported trigger_time format: {trigger_time}")
