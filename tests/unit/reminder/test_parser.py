# -*- coding: utf-8 -*-
"""
Unit tests for TimeParser module.

Tests the TimeParser class which handles time parsing and formatting
for reminder functionality.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agent.agno_agent.tools.reminder.parser import TimeParser


class TestTimeParserParse:
    """Test time parsing functionality."""

    def test_parse_relative_time_minutes(self):
        """Test parsing relative time in minutes."""
        # Use a fixed base timestamp for predictable results
        base_ts = int(datetime(2024, 12, 25, 9, 0, 0).timestamp())
        parser = TimeParser(base_timestamp=base_ts)

        result = parser.parse("30分钟后")
        expected = base_ts + 30 * 60  # 30 minutes later
        assert result == expected

    def test_parse_relative_time_hours(self):
        """Test parsing relative time in hours."""
        base_ts = int(datetime(2024, 12, 25, 9, 0, 0).timestamp())
        parser = TimeParser(base_timestamp=base_ts)

        result = parser.parse("2小时后")
        expected = base_ts + 2 * 3600  # 2 hours later
        assert result == expected

    def test_parse_relative_time_normalizes_millisecond_base_timestamp(self):
        """Test millisecond base timestamps are normalized before relative parsing."""
        base_ts = int(datetime(2024, 12, 25, 9, 0, 0).timestamp())
        parser = TimeParser(base_timestamp=base_ts * 1000)

        result = parser.parse("30分钟后")

        assert result == base_ts + 30 * 60

    def test_parse_absolute_time(self):
        """Test parsing absolute time."""
        parser = TimeParser()

        result = parser.parse("2024年12月25日09时00分")
        expected = int(datetime(2024, 12, 25, 9, 0, 0).timestamp())
        assert result == expected

    def test_parse_none_returns_none(self):
        """Test parsing None returns None."""
        parser = TimeParser()
        result = parser.parse(None)
        assert result is None

    def test_parse_empty_string_returns_none(self):
        """Test parsing empty string returns None."""
        parser = TimeParser()
        result = parser.parse("")
        assert result is None


class TestTimeParserFormat:
    """Test time formatting functionality."""

    _TZ = ZoneInfo("Asia/Shanghai")

    def test_format_friendly_time(self):
        """Test formatting time in friendly format."""
        # Create a timestamp for tomorrow at 9am
        tomorrow = datetime.now(tz=self._TZ) + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        ts = int(tomorrow.timestamp())

        parser = TimeParser()
        result = parser.format_friendly(ts)
        assert "明天" in result
        assert "上午" in result
        assert "9点" in result

    def test_format_with_date(self):
        """Test formatting with full date and weekday."""
        # Fixed date: 2024-12-25 (Wednesday) at 16:45
        dt = datetime(2024, 12, 25, 16, 45, 0, tzinfo=self._TZ)
        ts = int(dt.timestamp())

        parser = TimeParser()
        result = parser.format_with_date(ts)

        # Should contain date, weekday, and time
        assert "12月" in result
        assert "25日" in result
        assert "星期三" in result
        assert "下午" in result
        assert "4点" in result
        assert "45分" in result


class TestTimeParserPeriodConfig:
    """Test period configuration parsing."""

    def test_parse_period_config_simple(self):
        """Test parsing simple period config."""
        parser = TimeParser()
        result = parser.parse_period_config("09:00", "18:00", None)

        assert result is not None
        assert result["enabled"] is True
        assert result["start_time"] == "09:00"
        assert result["end_time"] == "18:00"
        assert result["active_days"] is None
        assert result["timezone"] == "Asia/Shanghai"

    def test_parse_period_config_with_days(self):
        """Test parsing period config with active days."""
        parser = TimeParser()
        result = parser.parse_period_config("09:00", "18:00", "1,2,3,4,5")

        assert result is not None
        assert result["start_time"] == "09:00"
        assert result["end_time"] == "18:00"
        assert result["active_days"] == [1, 2, 3, 4, 5]

    def test_parse_period_config_none(self):
        """Test parsing period config with None values."""
        parser = TimeParser()
        result = parser.parse_period_config(None, None, None)

        assert result is None

    def test_parse_period_config_incomplete(self):
        """Test parsing period config with only start or end."""
        parser = TimeParser()

        # Only start time
        result = parser.parse_period_config("09:00", None, None)
        assert result is None

        # Only end time
        result = parser.parse_period_config(None, "18:00", None)
        assert result is None

    def test_parse_period_config_invalid_days(self):
        """Test parsing period config with invalid days string."""
        parser = TimeParser()
        result = parser.parse_period_config("09:00", "18:00", "invalid")

        # Should still parse but active_days should be None
        assert result is not None
        assert result["active_days"] is None


class TestTimeParserInit:
    """Test TimeParser initialization."""

    def test_init_without_base_timestamp(self):
        """Test initialization without base timestamp."""
        parser = TimeParser()
        assert parser.base_timestamp is None

    def test_init_with_base_timestamp(self):
        """Test initialization with base timestamp."""
        base_ts = int(datetime(2024, 12, 25, 9, 0, 0).timestamp())
        parser = TimeParser(base_timestamp=base_ts)
        assert parser.base_timestamp == base_ts

    def test_init_normalizes_millisecond_base_timestamp(self):
        """Test initialization normalizes millisecond timestamps to seconds."""
        base_ts = int(datetime(2024, 12, 25, 9, 0, 0).timestamp())
        parser = TimeParser(base_timestamp=base_ts * 1000)
        assert parser.base_timestamp == base_ts
