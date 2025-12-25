# -*- coding: utf-8 -*-
"""
时间段提醒功能测试

测试场景：
1. 创建时间段提醒
2. 时间段内触发
3. 时间段外跳过并重新计算
4. 工作日限制
"""

import sys

sys.path.append(".")

import time
import unittest
from datetime import datetime, timedelta

from dao.reminder_dao import ReminderDAO
from util.time_util import calculate_next_period_trigger, is_within_time_period


class TestTimePeriodReminder(unittest.TestCase):
    """测试时间段提醒功能"""

    def setUp(self):
        """测试前准备"""
        self.dao = ReminderDAO()

    def tearDown(self):
        """测试后清理"""
        self.dao.close()

    def test_is_within_time_period(self):
        """测试时间段判断"""
        # 创建一个测试时间：今天下午3点
        now = datetime.now()
        test_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
        timestamp = int(test_time.timestamp())

        # 测试1：在时间段内（9:00-18:00）
        result = is_within_time_period(timestamp, "09:00", "18:00")
        self.assertTrue(result, "下午3点应该在9:00-18:00时间段内")

        # 测试2：不在时间段内（19:00-22:00）
        result = is_within_time_period(timestamp, "19:00", "22:00")
        self.assertFalse(result, "下午3点不应该在19:00-22:00时间段内")

        # 测试3：工作日限制
        weekday = test_time.isoweekday()  # 1=周一, 7=周日
        if weekday <= 5:
            # 工作日
            result = is_within_time_period(timestamp, "09:00", "18:00", [1, 2, 3, 4, 5])
            self.assertTrue(result, "工作日应该在工作日时间段内")
        else:
            # 周末
            result = is_within_time_period(timestamp, "09:00", "18:00", [1, 2, 3, 4, 5])
            self.assertFalse(result, "周末不应该在工作日时间段内")

    def test_calculate_next_period_trigger(self):
        """测试时间段提醒的下次触发时间计算"""
        now = datetime.now()

        # 测试1：当前在时间段内，下次触发应该是30分钟后
        test_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        timestamp = int(test_time.timestamp())

        next_time = calculate_next_period_trigger(
            timestamp, interval_minutes=30, start_time="09:00", end_time="18:00"
        )

        self.assertIsNotNone(next_time, "应该能计算出下次触发时间")
        expected_time = timestamp + 30 * 60
        self.assertEqual(next_time, expected_time, "下次触发时间应该是30分钟后")

        # 测试2：当前在时间段外（早于开始时间），下次触发应该是时间段开始时间
        test_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        timestamp = int(test_time.timestamp())

        next_time = calculate_next_period_trigger(
            timestamp, interval_minutes=30, start_time="09:00", end_time="18:00"
        )

        self.assertIsNotNone(next_time, "应该能计算出下次触发时间")
        expected_start = test_time.replace(hour=9, minute=0)
        self.assertEqual(
            next_time,
            int(expected_start.timestamp()),
            "下次触发时间应该是时间段开始时间",
        )

    def test_create_time_period_reminder(self):
        """测试创建时间段提醒"""
        # 创建一个时间段提醒：工作时间每30分钟提醒喝水
        now = int(time.time())
        tomorrow = datetime.fromtimestamp(now) + timedelta(days=1)
        trigger_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        reminder_doc = {
            "user_id": "test_user_period",
            "conversation_id": "test_conv_period",
            "character_id": "test_char_period",
            "title": "喝水",
            "action_template": "记得喝水",
            "next_trigger_time": int(trigger_time.timestamp()),
            "time_original": "明天09时00分",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": True, "type": "interval", "interval": 30},
            "time_period": {
                "enabled": True,
                "start_time": "09:00",
                "end_time": "18:00",
                "active_days": [1, 2, 3, 4, 5],
                "timezone": "Asia/Shanghai",
            },
            "period_state": {
                "today_first_trigger": None,
                "today_last_trigger": None,
                "today_trigger_count": 0,
            },
            "status": "confirmed",
        }

        # 创建提醒
        reminder_id = self.dao.create_reminder(reminder_doc)
        self.assertIsNotNone(reminder_id, "应该能成功创建时间段提醒")

        # 查询验证
        reminder = self.dao.get_reminder_by_id(reminder_doc["reminder_id"])
        self.assertIsNotNone(reminder, "应该能查询到创建的提醒")
        self.assertTrue(reminder["time_period"]["enabled"], "时间段配置应该启用")
        self.assertEqual(reminder["time_period"]["start_time"], "09:00")
        self.assertEqual(reminder["time_period"]["end_time"], "18:00")
        self.assertEqual(reminder["recurrence"]["type"], "interval")
        self.assertEqual(reminder["recurrence"]["interval"], 30)

        # 清理
        self.dao.delete_reminder(reminder_doc["reminder_id"])
        print("✓ 时间段提醒创建测试通过")


if __name__ == "__main__":
    unittest.main()
