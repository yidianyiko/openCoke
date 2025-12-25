# -*- coding: utf-8 -*-
"""
提醒功能测试用例
"""
import sys

sys.path.append(".")

import time
import unittest
from datetime import datetime, timedelta

from dao.reminder_dao import ReminderDAO
from util.time_util import (
    calculate_next_recurrence,
    format_time_friendly,
    is_time_in_past,
    parse_relative_time,
)


class TestReminderDAO(unittest.TestCase):
    """测试 ReminderDAO"""

    def setUp(self):
        self.dao = ReminderDAO()
        self.dao.create_indexes()

    def tearDown(self):
        # 清理测试数据
        test_reminders = self.dao.find_reminders_by_user("test_user_123")
        for r in test_reminders:
            self.dao.delete_reminder(r["reminder_id"])
        self.dao.close()

    def test_create_reminder(self):
        """测试创建提醒"""
        reminder_data = {
            "conversation_id": "test_conv_123",
            "user_id": "test_user_123",
            "character_id": "test_char_456",
            "title": "测试提醒",
            "next_trigger_time": int(time.time()) + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "action_template": "这是测试提醒",
            "requires_confirmation": False,
        }

        reminder_id = self.dao.create_reminder(reminder_data)
        self.assertIsNotNone(reminder_id)

        # 验证创建成功
        reminder = self.dao.get_reminder_by_object_id(reminder_id)
        self.assertEqual(reminder["title"], "测试提醒")

    def test_find_pending_reminders(self):
        """测试查找待触发提醒"""
        # 创建一个即将触发的提醒
        reminder_data = {
            "conversation_id": "test_conv_123",
            "user_id": "test_user_123",
            "character_id": "test_char_456",
            "title": "即将触发",
            "next_trigger_time": int(time.time()) - 60,  # 1分钟前
            "time_original": "1分钟前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "action_template": "测试",
            "status": "confirmed",
        }

        self.dao.create_reminder(reminder_data)

        # 查找
        pending = self.dao.find_pending_reminders(int(time.time()))
        self.assertGreater(len(pending), 0)

    def test_reschedule_reminder(self):
        """测试重新安排提醒"""
        reminder_data = {
            "conversation_id": "test_conv_123",
            "user_id": "test_user_123",
            "character_id": "test_char_456",
            "title": "周期提醒",
            "next_trigger_time": int(time.time()) + 3600,
            "time_original": "每天",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": True, "type": "daily", "interval": 1},
            "action_template": "每日提醒",
        }

        reminder_id = self.dao.create_reminder(reminder_data)
        reminder = self.dao.get_reminder_by_object_id(reminder_id)

        # 重新安排
        new_time = int(time.time()) + 7200
        success = self.dao.reschedule_reminder(reminder["reminder_id"], new_time)
        self.assertTrue(success)

        # 验证
        updated = self.dao.get_reminder_by_id(reminder["reminder_id"])
        self.assertEqual(updated["next_trigger_time"], new_time)


class TestTimeUtils(unittest.TestCase):
    """测试时间工具函数"""

    def test_parse_relative_time(self):
        """测试相对时间解析"""
        base = int(time.time())

        # 30分钟后
        result = parse_relative_time("30分钟后", base)
        self.assertAlmostEqual(result, base + 1800, delta=5)

        # 2小时后
        result = parse_relative_time("2小时后", base)
        self.assertAlmostEqual(result, base + 7200, delta=5)

        # 明天
        result = parse_relative_time("明天", base)
        self.assertIsNotNone(result)
        self.assertGreater(result, base)

    def test_calculate_next_recurrence(self):
        """测试周期计算"""
        current = int(time.time())

        # 每天
        next_daily = calculate_next_recurrence(current, "daily", 1)
        self.assertAlmostEqual(next_daily, current + 86400, delta=5)

        # 每周
        next_weekly = calculate_next_recurrence(current, "weekly", 1)
        self.assertAlmostEqual(next_weekly, current + 604800, delta=5)

    def test_is_time_in_past(self):
        """测试时间过期判断"""
        past = int(time.time()) - 3600
        future = int(time.time()) + 3600

        self.assertTrue(is_time_in_past(past))
        self.assertFalse(is_time_in_past(future))

    def test_format_time_friendly(self):
        """测试友好时间格式化"""
        # 明天上午9点
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=9, minute=0, second=0)
        timestamp = int(tomorrow.timestamp())

        result = format_time_friendly(timestamp)
        self.assertIn("明天", result)
        self.assertIn("上午", result)


class TestReminderIntegration(unittest.TestCase):
    """集成测试"""

    def test_reminder_workflow(self):
        """测试完整的提醒工作流"""
        dao = ReminderDAO()

        # 1. 创建提醒
        reminder_data = {
            "conversation_id": "test_conv_workflow",
            "user_id": "test_user_workflow",
            "character_id": "test_char_workflow",
            "title": "工作流测试",
            "next_trigger_time": int(time.time()) + 60,
            "time_original": "1分钟后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "action_template": "工作流测试提醒",
        }

        reminder_id = dao.create_reminder(reminder_data)
        reminder = dao.get_reminder_by_object_id(reminder_id)

        # 2. 查询待触发
        pending = dao.find_reminders_by_user("test_user_workflow", "confirmed")
        self.assertEqual(len(pending), 1)

        # 3. 标记为已触发
        dao.mark_as_triggered(reminder["reminder_id"])

        # 4. 完成提醒
        dao.complete_reminder(reminder["reminder_id"])

        # 5. 验证状态
        completed = dao.get_reminder_by_id(reminder["reminder_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["triggered_count"], 1)

        # 清理
        dao.delete_reminder(reminder["reminder_id"])
        dao.close()

    def test_cancel_and_reschedule_via_ops(self):
        """模拟对话层的取消与改期逻辑（DAO层验证）"""
        dao = ReminderDAO()
        base_title = "买菜提醒"
        now = int(time.time())
        r1_id = dao.create_reminder(
            {
                "conversation_id": "conv_ops",
                "user_id": "user_ops",
                "character_id": "char_ops",
                "title": base_title,
                "next_trigger_time": now + 3600,
                "time_original": "1小时后",
                "timezone": "Asia/Shanghai",
                "recurrence": {"enabled": False},
                "action_template": "去买菜",
            }
        )
        r1 = dao.get_reminder_by_object_id(r1_id)

        # 取消
        ok_cancel = dao.cancel_reminder(r1["reminder_id"])
        self.assertTrue(ok_cancel)
        cancelled = dao.get_reminder_by_id(r1["reminder_id"])
        self.assertEqual(cancelled["status"], "cancelled")

        # 重新创建一个用于改期
        r2_id = dao.create_reminder(
            {
                "conversation_id": "conv_ops",
                "user_id": "user_ops",
                "character_id": "char_ops",
                "title": base_title,
                "next_trigger_time": now + 7200,
                "time_original": "2小时后",
                "timezone": "Asia/Shanghai",
                "recurrence": {"enabled": False},
                "action_template": "去买菜",
            }
        )
        r2 = dao.get_reminder_by_object_id(r2_id)

        new_time = now + 10800
        ok_reschedule = dao.reschedule_reminder(r2["reminder_id"], new_time)
        self.assertTrue(ok_reschedule)
        updated = dao.get_reminder_by_id(r2["reminder_id"])
        self.assertEqual(updated["next_trigger_time"], new_time)

        # 清理
        dao.delete_reminder(r1["reminder_id"])
        dao.delete_reminder(r2["reminder_id"])
        dao.close()


if __name__ == "__main__":
    unittest.main()
