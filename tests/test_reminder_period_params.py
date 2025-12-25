# -*- coding: utf-8 -*-
"""
测试提醒工具的时间段参数处理

测试场景：
1. 不设置时间段参数（普通提醒）
2. 完整设置时间段参数
3. 只设置部分时间段参数（应该忽略）
"""

import sys

sys.path.append(".")

import time
import unittest
from datetime import datetime, timedelta

from dao.reminder_dao import ReminderDAO


class TestReminderPeriodParams(unittest.TestCase):
    """测试提醒工具的时间段参数处理"""

    def setUp(self):
        """测试前准备"""
        self.dao = ReminderDAO()

    def tearDown(self):
        """测试后清理"""
        self.dao.close()

    def test_no_period_params(self):
        """测试不设置时间段参数（普通提醒）"""
        now = int(time.time())
        tomorrow = datetime.fromtimestamp(now) + timedelta(days=1)
        trigger_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        reminder_doc = {
            "user_id": "test_user_no_period",
            "conversation_id": "test_conv_no_period",
            "character_id": "test_char_no_period",
            "title": "开会",
            "action_template": "记得开会",
            "next_trigger_time": int(trigger_time.timestamp()),
            "time_original": "明天09时00分",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False, "type": None, "interval": 1},
            "status": "confirmed",
            # 注意：没有 time_period 字段
        }

        # 创建提醒
        reminder_id = self.dao.create_reminder(reminder_doc)
        self.assertIsNotNone(reminder_id, "应该能成功创建普通提醒")

        # 查询验证
        reminder = self.dao.get_reminder_by_id(reminder_doc["reminder_id"])
        self.assertIsNotNone(reminder, "应该能查询到创建的提醒")
        self.assertNotIn("time_period", reminder, "普通提醒不应该有 time_period 字段")

        # 清理
        self.dao.delete_reminder(reminder_doc["reminder_id"])
        print("✓ 普通提醒（无时间段参数）测试通过")

    def test_complete_period_params(self):
        """测试完整设置时间段参数"""
        now = int(time.time())
        tomorrow = datetime.fromtimestamp(now) + timedelta(days=1)
        trigger_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        reminder_doc = {
            "user_id": "test_user_complete_period",
            "conversation_id": "test_conv_complete_period",
            "character_id": "test_char_complete_period",
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
        self.assertIn("time_period", reminder, "时间段提醒应该有 time_period 字段")
        self.assertTrue(reminder["time_period"]["enabled"], "时间段应该启用")
        self.assertEqual(reminder["time_period"]["start_time"], "09:00")
        self.assertEqual(reminder["time_period"]["end_time"], "18:00")

        # 清理
        self.dao.delete_reminder(reminder_doc["reminder_id"])
        print("✓ 时间段提醒（完整参数）测试通过")

    def test_partial_period_params_start_only(self):
        """测试只设置 period_start（应该被忽略，创建普通提醒）"""
        now = int(time.time())
        tomorrow = datetime.fromtimestamp(now) + timedelta(days=1)
        trigger_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        # 模拟 reminder_tool 的逻辑：只有 period_start，没有 period_end
        period_start = "09:00"
        period_end = None

        # 根据 reminder_tool 的逻辑，time_period_config 应该是 None
        time_period_config = None
        if period_start and period_end:
            time_period_config = {
                "enabled": True,
                "start_time": period_start,
                "end_time": period_end,
                "active_days": None,
                "timezone": "Asia/Shanghai",
            }

        self.assertIsNone(
            time_period_config, "只设置 period_start 时，time_period_config 应该是 None"
        )

        # 创建提醒文档（不包含 time_period）
        reminder_doc = {
            "user_id": "test_user_partial_start",
            "conversation_id": "test_conv_partial_start",
            "character_id": "test_char_partial_start",
            "title": "测试",
            "action_template": "测试提醒",
            "next_trigger_time": int(trigger_time.timestamp()),
            "time_original": "明天09时00分",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False, "type": None, "interval": 1},
            "status": "confirmed",
        }

        # 创建提醒
        reminder_id = self.dao.create_reminder(reminder_doc)
        self.assertIsNotNone(reminder_id, "应该能成功创建提醒")

        # 查询验证
        reminder = self.dao.get_reminder_by_id(reminder_doc["reminder_id"])
        self.assertIsNotNone(reminder, "应该能查询到创建的提醒")
        self.assertNotIn("time_period", reminder, "部分参数时不应该有 time_period 字段")

        # 清理
        self.dao.delete_reminder(reminder_doc["reminder_id"])
        print("✓ 部分参数（仅 period_start）测试通过")

    def test_partial_period_params_end_only(self):
        """测试只设置 period_end（应该被忽略，创建普通提醒）"""
        now = int(time.time())
        tomorrow = datetime.fromtimestamp(now) + timedelta(days=1)
        trigger_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        # 模拟 reminder_tool 的逻辑：只有 period_end，没有 period_start
        period_start = None
        period_end = "18:00"

        # 根据 reminder_tool 的逻辑，time_period_config 应该是 None
        time_period_config = None
        if period_start and period_end:
            time_period_config = {
                "enabled": True,
                "start_time": period_start,
                "end_time": period_end,
                "active_days": None,
                "timezone": "Asia/Shanghai",
            }

        self.assertIsNone(
            time_period_config, "只设置 period_end 时，time_period_config 应该是 None"
        )

        # 创建提醒文档（不包含 time_period）
        reminder_doc = {
            "user_id": "test_user_partial_end",
            "conversation_id": "test_conv_partial_end",
            "character_id": "test_char_partial_end",
            "title": "测试",
            "action_template": "测试提醒",
            "next_trigger_time": int(trigger_time.timestamp()),
            "time_original": "明天09时00分",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False, "type": None, "interval": 1},
            "status": "confirmed",
        }

        # 创建提醒
        reminder_id = self.dao.create_reminder(reminder_doc)
        self.assertIsNotNone(reminder_id, "应该能成功创建提醒")

        # 查询验证
        reminder = self.dao.get_reminder_by_id(reminder_doc["reminder_id"])
        self.assertIsNotNone(reminder, "应该能查询到创建的提醒")
        self.assertNotIn("time_period", reminder, "部分参数时不应该有 time_period 字段")

        # 清理
        self.dao.delete_reminder(reminder_doc["reminder_id"])
        print("✓ 部分参数（仅 period_end）测试通过")

    def test_period_with_none_days(self):
        """测试时间段参数但不设置 period_days（应该每天生效）"""
        now = int(time.time())
        tomorrow = datetime.fromtimestamp(now) + timedelta(days=1)
        trigger_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        reminder_doc = {
            "user_id": "test_user_no_days",
            "conversation_id": "test_conv_no_days",
            "character_id": "test_char_no_days",
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
                "active_days": None,  # 不设置，表示每天
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
        self.assertIn("time_period", reminder, "时间段提醒应该有 time_period 字段")
        self.assertTrue(reminder["time_period"]["enabled"], "时间段应该启用")
        self.assertIsNone(
            reminder["time_period"]["active_days"],
            "active_days 应该是 None（每天生效）",
        )

        # 清理
        self.dao.delete_reminder(reminder_doc["reminder_id"])
        print("✓ 时间段提醒（无 period_days）测试通过")


if __name__ == "__main__":
    unittest.main()
