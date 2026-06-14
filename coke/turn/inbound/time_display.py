from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DISPLAY_DATETIME_KEYS = {
    "local_trigger_at",
    "trigger_at",
    "trigger_time",
    "next_fire_at",
    "due_at",
    "local_start",
    "local_end",
    "time",
}
_AVAILABILITY_WINDOW_KEYS = {"start", "end"}
_WEEKDAYS = (
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
)


def format_time_friendly(
    value: datetime,
    *,
    now: datetime,
    timezone_name: str,
) -> str:
    zone = _zoneinfo_or_utc(timezone_name)
    local_value = _localize(value, zone)
    local_now = _localize(now, zone)
    days_diff = (local_value.date() - local_now.date()).days

    time_text = _time_text(local_value)
    if days_diff == 0:
        return f"今天{time_text}"
    if days_diff == 1:
        return f"明天{time_text}"
    if days_diff == 2:
        return f"后天{time_text}"
    if days_diff < 7:
        return f"{_WEEKDAYS[local_value.weekday()]}{time_text}"
    return f"{local_value.month}月{local_value.day}日{time_text}"


def attach_time_display_fields(
    value: Any,
    *,
    now: datetime | str,
    timezone_name: str,
) -> Any:
    parsed_now = _datetime_value(now)
    if parsed_now is None:
        return value
    return _attach_time_display_fields(
        value,
        now=parsed_now,
        timezone_name=timezone_name or "UTC",
    )


def _attach_time_display_fields(
    value: Any,
    *,
    now: datetime,
    timezone_name: str,
) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _attach_time_display_fields(
            asdict(value),
            now=now,
            timezone_name=timezone_name,
        )
    if isinstance(value, Mapping):
        item_timezone = _mapping_timezone(value, timezone_name)
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = _attach_time_display_fields(
                item,
                now=now,
                timezone_name=item_timezone,
            )
            if _should_display_key(key_text, value):
                parsed_value = _datetime_value(item)
                if parsed_value is not None:
                    result[f"{key_text}_display"] = format_time_friendly(
                        parsed_value,
                        now=now,
                        timezone_name=item_timezone,
                    )
        return result
    if isinstance(value, tuple | list):
        return [
            _attach_time_display_fields(
                item,
                now=now,
                timezone_name=timezone_name,
            )
            for item in value
        ]
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _time_text(value: datetime) -> str:
    hour = value.hour
    minute = value.minute
    if hour < 12:
        period = "上午"
    elif hour < 18:
        period = "下午"
        if hour > 12:
            hour -= 12
    else:
        period = "晚上"
        if hour > 12:
            hour -= 12

    text = f"{period}{hour}点"
    if minute > 0:
        text += f"{minute}分"
    return text


def _localize(value: datetime, zone: tzinfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _mapping_timezone(value: Mapping[Any, Any], fallback: str) -> str:
    for key in (
        "captured_timezone",
        "display_timezone",
        "requester_timezone",
        "default_timezone",
        "timezone",
    ):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return fallback


def _should_display_key(key: str, value: Mapping[Any, Any]) -> bool:
    if key in _DISPLAY_DATETIME_KEYS:
        return True
    return (
        key in _AVAILABILITY_WINDOW_KEYS
        and "state" in value
        and "start" in value
        and "end" in value
    )


def _datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _zoneinfo_or_utc(timezone_name: str) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC
