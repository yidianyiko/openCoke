# -*- coding: utf-8 -*-
"""
TimeParser module for reminder tools.

Provides time parsing and formatting utilities for reminder functionality.
Extracted from reminder_tools.py as part of the layered architecture refactor.
"""

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from util.time_util import (
    format_time_friendly,
    parse_relative_time,
    str2timestamp,
)

logger = logging.getLogger(__name__)


class TimeParser:
    """
    Time parsing and formatting utility for reminders.

    This class provides methods to:
    - Parse relative time expressions (e.g., "30分钟后", "2小时后")
    - Parse absolute time expressions (e.g., "2024年12月25日09时00分")
    - Format timestamps in friendly formats
    - Parse period configuration for time-based reminders

    Args:
        base_timestamp: Optional base timestamp for relative time calculations.
                      If None, uses current time when parsing relative times.
    """

    def __init__(self, base_timestamp: Optional[int] = None) -> None:
        """
        Initialize TimeParser with optional base timestamp.

        Args:
            base_timestamp: Base timestamp for relative time calculations.
                          If None, current time is used when parsing.
        """
        self.base_timestamp = base_timestamp

    def parse(self, time_str: Optional[str]) -> Optional[int]:
        """
        Parse a time string into a Unix timestamp.

        Handles both relative and absolute time expressions:
        - Relative: "30分钟后", "2小时后", "明天", "后天"
        - Absolute: "2024年12月25日09时00分"

        Args:
            time_str: Time string to parse. Can be None or empty.

        Returns:
            Unix timestamp as int, or None if parsing fails.
        """
        if not time_str:
            return None

        # Try relative time parsing first
        base = self.base_timestamp
        result = parse_relative_time(time_str, base_timestamp=base)
        if result is not None:
            return result

        # Try absolute time parsing
        result = str2timestamp(time_str)
        return result

    def format_friendly(self, timestamp: int) -> str:
        """
        Format a timestamp in a friendly, human-readable format.

        Examples: "今天上午9点", "明天下午3点30分", "后天晚上7点"

        Args:
            timestamp: Unix timestamp to format.

        Returns:
            Friendly time string.
        """
        return format_time_friendly(timestamp)

    def format_with_date(self, timestamp: int) -> str:
        """
        Format a timestamp with full date and weekday.

        Example: "12月30日 星期二 下午4点45分"

        Args:
            timestamp: Unix timestamp to format.

        Returns:
            Formatted date and time string with weekday.
        """
        dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Asia/Shanghai"))

        # Date part
        date_str = f"{dt.month}月{dt.day}日"

        # Weekday part
        weekdays = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        ]
        weekday_str = weekdays[dt.weekday()]

        # Time part
        hour = dt.hour
        minute = dt.minute
        if hour < 12:
            period = "上午"
        elif hour < 18:
            period = "下午"
            if hour > 12:
                hour = hour - 12
        else:
            period = "晚上"
            if hour > 12:
                hour = hour - 12

        time_str = f"{period}{hour}点"
        if minute > 0:
            time_str += f"{minute}分"

        return f"{date_str} {weekday_str} {time_str}"

    def parse_period_config(
        self,
        period_start: Optional[str],
        period_end: Optional[str],
        period_days: Optional[str],
    ) -> Optional[dict]:
        """
        Parse time period configuration for recurring reminders.

        Args:
            period_start: Start time in "HH:MM" format.
            period_end: End time in "HH:MM" format.
            period_days: Comma-separated active days (e.g., "1,2,3,4,5").
                        Days are 1-7 where 1=Monday, 7=Sunday.

        Returns:
            Dictionary with keys:
                - enabled: bool, always True
                - start_time: str, the period_start value
                - end_time: str, the period_end value
                - active_days: list[int] or None
                - timezone: str, always "Asia/Shanghai"
            Returns None if both period_start and period_end are None.
        """
        # Both start and end must be provided for a valid period
        if not (period_start and period_end):
            if period_start or period_end:
                logger.warning(
                    f"Incomplete time period config: start={period_start}, end={period_end}"
                )
            return None

        # Parse active days
        active_days = None
        if period_days:
            try:
                active_days = [int(d.strip()) for d in period_days.split(",")]
            except (ValueError, AttributeError):
                logger.warning(f"Failed to parse period_days: {period_days}")

        config = {
            "enabled": True,
            "start_time": period_start,
            "end_time": period_end,
            "active_days": active_days,
            "timezone": "Asia/Shanghai",
        }
        logger.info(f"Time period config: {config}")
        return config
