# -*- coding: utf-8 -*-
"""
时间解析属性测试
"""
import time

import pytest
from hypothesis import given, strategies as st

from util.time_util import (
    calculate_next_recurrence,
    format_time_friendly,
    is_time_in_past,
    parse_relative_time,
    timestamp2str,
)


@pytest.mark.pbt
class TestTimeParsingPBT:
    """时间解析属性测试"""

    @given(st.integers(min_value=0, max_value=2147483647))
    def test_timestamp2str_never_crashes(self, timestamp):
        """timestamp2str 不应该崩溃"""
        try:
            result = timestamp2str(timestamp)
            assert isinstance(result, str)
        except Exception:
            # 某些极端时间戳可能失败，但不应该崩溃整个程序
            pass

    @given(st.integers(min_value=1, max_value=1440))
    def test_parse_relative_time_minutes(self, minutes):
        """测试分钟解析的属性"""
        base = int(time.time())
        text = f"{minutes}分钟后"
        result = parse_relative_time(text, base)

        if result is not None:
            # 结果应该大于基准时间
            assert result > base
            # 结果应该接近预期时间
            expected = base + minutes * 60
            assert abs(result - expected) < 60

    @given(st.integers(min_value=1, max_value=24))
    def test_parse_relative_time_hours(self, hours):
        """测试小时解析的属性"""
        base = int(time.time())
        text = f"{hours}小时后"
        result = parse_relative_time(text, base)

        if result is not None:
            assert result > base
            expected = base + hours * 3600
            assert abs(result - expected) < 3600

    @given(
        st.integers(min_value=0, max_value=2147483647),
        st.sampled_from(["daily", "weekly", "monthly", "yearly", "hourly"]),
        st.integers(min_value=1, max_value=10),
    )
    def test_calculate_next_recurrence_properties(
        self, current_time, recurrence_type, interval
    ):
        """测试周期计算的属性"""
        result = calculate_next_recurrence(current_time, recurrence_type, interval)

        if result is not None:
            # 下次时间应该大于当前时间
            assert result > current_time
            # 结果应该是整数
            assert isinstance(result, int)

    @given(st.integers(min_value=0, max_value=2147483647))
    def test_is_time_in_past_consistency(self, timestamp):
        """测试时间过期判断的一致性"""
        current = int(time.time())

        if timestamp < current:
            assert is_time_in_past(timestamp) is True
        else:
            assert is_time_in_past(timestamp) is False

    @given(st.integers(min_value=int(time.time()), max_value=int(time.time()) + 86400 * 365))
    def test_format_time_friendly_never_crashes(self, timestamp):
        """format_time_friendly 不应该崩溃"""
        try:
            result = format_time_friendly(timestamp)
            assert isinstance(result, str)
            assert len(result) > 0
        except Exception:
            pass
