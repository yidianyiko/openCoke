from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class DateWindow:
    local_start: datetime
    local_end: datetime
    trigger_after: datetime
    trigger_before: datetime


_RELATIVE_DAY_OFFSETS: tuple[tuple[str, int], ...] = (
    ("day after tomorrow", 2),
    ("后天", 2),
    ("tomorrow", 1),
    ("明天", 1),
    ("today", 0),
    ("今天", 0),
    ("今日", 0),
)

_CHINESE_WEEKDAYS = {
    "一": 0,
    "1": 0,
    "二": 1,
    "2": 1,
    "三": 2,
    "3": 2,
    "四": 3,
    "4": 3,
    "五": 4,
    "5": 4,
    "六": 5,
    "6": 5,
    "日": 6,
    "天": 6,
    "7": 6,
}

_ENGLISH_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def resolve_date_phrase_window(
    value: Any,
    *,
    timezone_name: str,
    now: Callable[[], datetime],
) -> DateWindow | None:
    if not isinstance(value, str):
        return None
    phrase = value.strip()
    if not phrase:
        return None
    zone = _zoneinfo_or_utc(timezone_name)
    current = _aware_now(now()).astimezone(zone)
    target_date = _date_from_phrase(phrase, current.date())
    if target_date is None:
        return None
    return _date_window(target_date, zone)


def _date_from_phrase(phrase: str, today: date) -> date | None:
    normalized = phrase.lower()
    for token, offset in _RELATIVE_DAY_OFFSETS:
        if token in normalized:
            return today + timedelta(days=offset)
    explicit_date = _explicit_date(normalized, today)
    if explicit_date is not None:
        return explicit_date
    weekday = _weekday(normalized)
    if weekday is None:
        return None
    return _next_weekday(
        today, weekday, force_future_week=_force_future_week(normalized)
    )


def _explicit_date(phrase: str, today: date) -> date | None:
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", phrase)
    if iso_match is not None:
        return _date_or_none(
            int(iso_match.group(1)),
            int(iso_match.group(2)),
            int(iso_match.group(3)),
        )
    chinese_match = re.search(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})(?:日|号)?",
        phrase,
    )
    if chinese_match is None:
        return None
    year = int(chinese_match.group(1) or today.year)
    return _date_or_none(
        year,
        int(chinese_match.group(2)),
        int(chinese_match.group(3)),
    )


def _weekday(phrase: str) -> int | None:
    chinese_match = re.search(r"(?:星期|礼拜|周)([一二三四五六日天1-7])", phrase)
    if chinese_match is not None:
        return _CHINESE_WEEKDAYS[chinese_match.group(1)]
    for token, weekday in _ENGLISH_WEEKDAYS.items():
        if re.search(rf"\b{token}\b", phrase):
            return weekday
    return None


def _next_weekday(today: date, weekday: int, *, force_future_week: bool) -> date:
    offset = (weekday - today.weekday()) % 7
    if force_future_week and offset == 0:
        offset = 7
    return today + timedelta(days=offset)


def _force_future_week(phrase: str) -> bool:
    return "下周" in phrase or "next " in phrase


def _date_window(target_date: date, zone: ZoneInfo) -> DateWindow:
    local_start_aware = datetime.combine(target_date, time.min, tzinfo=zone)
    local_end_aware = datetime.combine(
        target_date + timedelta(days=1),
        time.min,
        tzinfo=zone,
    )
    return DateWindow(
        local_start=local_start_aware.replace(tzinfo=None),
        local_end=local_end_aware.replace(tzinfo=None),
        trigger_after=local_start_aware.astimezone(UTC),
        trigger_before=local_end_aware.astimezone(UTC),
    )


def _aware_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _zoneinfo_or_utc(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _date_or_none(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
