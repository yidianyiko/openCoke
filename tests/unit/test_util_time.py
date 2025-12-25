# -*- coding: utf-8 -*-
"""
util/time_util.py 单元测试
"""
import time
from datetime import datetime, timedelta

import pytest

from util.time_util import (
    calculate_next_period_trigger,
    calculate_next_recurrence,
    date2str,
    format_time_friendly,
    is_time_in_past,
    is_within_time_period,
    parse_relative_time,
    str2timestamp,
    timestamp2str,
)


class TestTimestamp2Str:
    """测试时间戳转字符串"""

    def test_basic_conversion(self):
        """测试基本转换"""
        timestamp = int(datetime(2024, 12, 25, 9, 30).timestamp())
        result = timestamp2str(timestamp)
        assert "2024年12月25日09时30分" == result

    def test_with_week(self):
        """测试包含星期"""
        timestamp = int(datetime(2024, 12, 25, 9, 30).timestamp())  # 星期三
        result = timestamp2str(timestamp, week=True)
        assert "星期三" in result
        assert "2024年12月25日09时30分" in result

    def test_different_times(self):
        """测试不同时间"""
        timestamp = int(datetime(2024, 1, 1, 0, 0).timestamp())
        result = timestamp2str(timestamp)
        assert "2024年01月01日00时00分" == result


class TestStr2Timestamp:
    """测试字符串转时间戳"""

    def test_valid_format(self):
        """测试有效格式"""
        time_str = "2024年12月25日09时30分"
        result = str2timestamp(time_str)
        assert result is not None
        assert isinstance(result, int)

    def test_invalid_format(self):
        """测试无效格式"""
        assert str2timestamp("invalid") is None
        assert str2timestamp("2024-12-25") is None
        assert str2timestamp("") is None

    def test_roundtrip(self):
        """测试往返转换"""
        original_timestamp = int(datetime(2024, 12, 25, 9, 30).timestamp())
        time_str = timestamp2str(original_timestamp)
        converted_timestamp = str2timestamp(time_str)
        assert original_timestamp == converted_timestamp


class TestDate2Str:
    """测试日期转字符串"""

    def test_basic_date(self):
        """测试基本日期"""
        timestamp = int(datetime(2024, 12, 25, 9, 30).timestamp())
        result = date2str(timestamp)
        assert result == "2024年12月25日"

    def test_with_week(self):
        """测试包含星期"""
        timestamp = int(datetime(2024, 12, 25, 9, 30).timestamp())
        result = date2str(timestamp, week=True)
        assert "2024年12月25日" in result
        assert "星期三" in result


class TestParseRelativeTime:
    """测试相对时间解析"""

    def test_minutes(self):
        """测试分钟"""
        base = int(time.time())
        result = parse_relative_time("30分钟后", base)
        assert result is not None
        assert abs(result-(base + 1800)) < 10

        # 也支持带空格的格式
        result_with_space = parse_relative_time("30 分钟后", base)
        assert result_with_space is not None
        assert abs(result_with_space-(base + 1800)) < 10

    def test_hours(self):
        """测试小时"""
        base = int(time.time())
        result = parse_relative_time("2小时后", base)
        assert result is not None
        assert abs(result-(base + 7200)) < 10

        result = parse_relative_time("1个小时后", base)
        assert result is not None
        assert abs(result-(base + 3600)) < 10

    def test_days(self):
        """测试天数"""
        base = int(time.time())
        result = parse_relative_time("3天后", base)
        assert result is not None
        assert abs(result-(base + 259200)) < 10

        # 也支持带空格的格式
        result_with_space = parse_relative_time("3 天后", base)
        assert result_with_space is not None
        assert abs(result_with_space-(base + 259200)) < 10

    def test_tomorrow(self):
        """测试明天"""
        base = int(time.time())
        result = parse_relative_time("明天", base)
        assert result is not None
        assert result > base

    def test_day_after_tomorrow(self):
        """测试后天"""
        base = int(time.time())
        result = parse_relative_time("后天", base)
        assert result is not None
        assert result > base

    def test_next_week(self):
        """测试下周"""
        base = int(time.time())
        result = parse_relative_time("下周", base)
        assert result is not None
        assert result > base

    def test_invalid_input(self):
        """测试无效输入"""
        result = parse_relative_time("无效时间")
        assert result is None

        result = parse_relative_time("")
        assert result is None


class TestCalculateNextRecurrence:
    """测试周期计算"""

    def test_daily(self):
        """测试每日"""
        current = int(time.time())
        next_time = calculate_next_recurrence(current, "daily", 1)
        assert abs(next_time-(current + 86400)) < 10

    def test_daily_interval(self):
        """测试每 N 天"""
        current = int(time.time())
        next_time = calculate_next_recurrence(current, "daily", 3)
        assert abs(next_time-(current + 259200)) < 10

    def test_weekly(self):
        """测试每周"""
        current = int(time.time())
        next_time = calculate_next_recurrence(current, "weekly", 1)
        assert abs(next_time-(current + 604800)) < 10

    def test_monthly(self):
        """测试每月"""
        current = int(time.time())
        next_time = calculate_next_recurrence(current, "monthly", 1)
        assert abs(next_time-(current + 2592000)) < 86400  # 30天左右

    def test_yearly(self):
        """测试每年"""
        current = int(time.time())
        next_time = calculate_next_recurrence(current, "yearly", 1)
        assert abs(next_time-(current + 31536000)) < 86400  # 365天左右

    def test_hourly(self):
        """测试每小时"""
        current = int(time.time())
        next_time = calculate_next_recurrence(current, "hourly", 2)
        assert abs(next_time-(current + 7200)) < 10

    def test_invalid_type(self):
        """测试无效类型"""
        current = int(time.time())
        result = calculate_next_recurrence(current, "invalid", 1)
        assert result is None


class TestIsTimeInPast:
    """测试时间是否过期"""

    def test_past_time(self):
        """测试过去时间"""
        past = int(time.time())-3600
        assert is_time_in_past(past) is True

    def test_future_time(self):
        """测试未来时间"""
        future = int(time.time()) + 3600
        assert is_time_in_past(future) is False

    def test_current_time(self):
        """测试当前时间"""
        current = int(time.time())
        # 当前时间应该不算过期
        assert is_time_in_past(current) is False


class TestFormatTimeFriendly:
    """测试友好时间格式化"""

    def test_today(self):
        """测试今天"""
        now = datetime.now()
        timestamp = int((now + timedelta(hours=2)).timestamp())
        result = format_time_friendly(timestamp)
        assert "今天" in result

    def test_tomorrow(self):
        """测试明天"""
        tomorrow = datetime.now() + timedelta(days=1)
        timestamp = int(tomorrow.timestamp())
        result = format_time_friendly(timestamp)
        assert "明天" in result

    def test_day_after_tomorrow(self):
        """测试后天"""
        day_after = datetime.now() + timedelta(days=2)
        timestamp = int(day_after.timestamp())
        result = format_time_friendly(timestamp)
        assert "后天" in result

    def test_within_week(self):
        """测试一周内"""
        in_week = datetime.now() + timedelta(days=4)
        timestamp = int(in_week.timestamp())
        result = format_time_friendly(timestamp)
        assert "星期" in result

    def test_beyond_week(self):
        """测试超过一周"""
        beyond = datetime.now() + timedelta(days=10)
        timestamp = int(beyond.timestamp())
        result = format_time_friendly(timestamp)
        assert "月" in result and "日" in result


class TestIsWithinTimePeriod:
    """测试时间段判断"""

    def test_within_period(self):
        """测试在时间段内"""
        now = datetime.now().replace(hour=10, minute=0)
        timestamp = int(now.timestamp())
        result = is_within_time_period(timestamp, "09:00", "17:00")
        assert result is True

    def test_outside_period(self):
        """测试在时间段外"""
        now = datetime.now().replace(hour=20, minute=0)
        timestamp = int(now.timestamp())
        result = is_within_time_period(timestamp, "09:00", "17:00")
        assert result is False

    def test_boundary_start(self):
        """测试开始边界"""
        now = datetime.now().replace(hour=9, minute=0)
        timestamp = int(now.timestamp())
        result = is_within_time_period(timestamp, "09:00", "17:00")
        assert result is True

    def test_boundary_end(self):
        """测试结束边界"""
        now = datetime.now().replace(hour=17, minute=0)
        timestamp = int(now.timestamp())
        result = is_within_time_period(timestamp, "09:00", "17:00")
        assert result is True

    def test_active_days(self):
        """测试指定生效日期"""
        # 获取今天是星期几
        now = datetime.now()
        weekday = now.isoweekday()
        timestamp = int(now.replace(hour=10, minute=0).timestamp())

        # 今天在生效日期内
        result = is_within_time_period(
            timestamp, "09:00", "17:00", active_days=[weekday]
        )
        assert result is True

        # 今天不在生效日期内
        other_day = (weekday % 7) + 1
        result = is_within_time_period(
            timestamp, "09:00", "17:00", active_days=[other_day]
        )
        assert result is False


class TestCalculateNextPeriodTrigger:
    """测试时间段提醒的下次触发时间"""

    def test_within_period_next_trigger(self):
        """测试在时间段内的下次触发"""
        now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        current_time = int(now.timestamp())

        next_trigger = calculate_next_period_trigger(
            current_time, 30, "09:00", "17:00"
        )

        assert next_trigger is not None
        assert next_trigger > current_time
        # 应该是 30 分钟后
        assert abs(next_trigger-(current_time + 1800)) < 60

    def test_outside_period_next_day(self):
        """测试在时间段外，返回下一个时间段开始"""
        now = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
        current_time = int(now.timestamp())

        next_trigger = calculate_next_period_trigger(
            current_time, 30, "09:00", "17:00"
        )

        assert next_trigger is not None
        assert next_trigger > current_time

    def test_with_active_days(self):
        """测试指定生效日期"""
        now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        current_time = int(now.timestamp())
        weekday = now.isoweekday()

        next_trigger = calculate_next_period_trigger(
            current_time, 30, "09:00", "17:00", active_days=[weekday]
        )

        assert next_trigger is not None
        assert next_trigger > current_time
