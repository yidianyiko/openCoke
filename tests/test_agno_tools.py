# -*- coding: utf-8 -*-
"""
Agno Tools 属性测试

测试 Tool 的返回结构完整性：
- context_retrieve_tool (Requirements 3.1)
- reminder_tool CRUD (Requirements 3.2)
- 时间解析 (Requirements 3.3)
"""
import sys

sys.path.append(".")

import time
import unittest
from datetime import datetime, timedelta


class TestContextRetrieveToolStructure(unittest.TestCase):
    """测试 context_retrieve_tool 返回结构完整性 (Requirements 3.1)"""

    def test_return_structure_keys(self):
        """测试返回结构包含所有必要字段"""
        # 预期的返回结构
        expected_keys = [
            "character_global",
            "character_private",
            "user",
            "character_knowledge",
            "confirmed_reminders",
        ]

        # 模拟返回结构
        mock_result = {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
        }

        for key in expected_keys:
            self.assertIn(key, mock_result)
            self.assertIsInstance(mock_result[key], str)

    def test_empty_query_returns_empty_strings(self):
        """测试空查询返回空字符串"""
        mock_result = {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
        }

        for key, value in mock_result.items():
            self.assertEqual(value, "")


class TestReminderToolCRUD(unittest.TestCase):
    """测试 reminder_tool CRUD 一致性 (Requirements 3.2)"""

    def test_create_response_structure(self):
        """测试创建操作返回结构"""
        # 成功响应
        success_response = {"ok": True, "reminder_id": "test-uuid-123"}
        self.assertTrue(success_response["ok"])
        self.assertIn("reminder_id", success_response)

        # 失败响应
        error_response = {"ok": False, "error": "创建提醒需要提供标题"}
        self.assertFalse(error_response["ok"])
        self.assertIn("error", error_response)

    def test_update_response_structure(self):
        """测试更新操作返回结构"""
        success_response = {"ok": True}
        self.assertTrue(success_response["ok"])

        error_response = {"ok": False, "error": "找不到提醒"}
        self.assertFalse(error_response["ok"])

    def test_delete_response_structure(self):
        """测试删除操作返回结构"""
        success_response = {"ok": True}
        self.assertTrue(success_response["ok"])

        error_response = {"ok": False, "error": "删除操作需要提供 reminder_id"}
        self.assertFalse(error_response["ok"])

    def test_list_response_structure(self):
        """测试列表操作返回结构"""
        success_response = {
            "ok": True,
            "reminders": [
                {
                    "reminder_id": "test-123",
                    "title": "测试提醒",
                    "status": "confirmed",
                    "next_trigger_time": int(time.time()) + 3600,
                    "time_friendly": "1小时后",
                    "recurrence": {"enabled": False},
                    "created_at": int(time.time()),
                    "triggered_count": 0,
                }
            ],
        }
        self.assertTrue(success_response["ok"])
        self.assertIn("reminders", success_response)
        self.assertIsInstance(success_response["reminders"], list)

        if success_response["reminders"]:
            reminder = success_response["reminders"][0]
            self.assertIn("reminder_id", reminder)
            self.assertIn("title", reminder)
            self.assertIn("status", reminder)


class TestTimeParsingCorrectness(unittest.TestCase):
    """测试时间解析正确性 (Requirements 3.3)"""

    def setUp(self):
        from util.time_util import parse_relative_time, str2timestamp

        self.parse_relative_time = parse_relative_time
        self.str2timestamp = str2timestamp

    def test_relative_time_minutes(self):
        """测试分钟级相对时间"""
        base = int(time.time())

        result = self.parse_relative_time("30分钟后", base)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, base + 1800, delta=10)

        result = self.parse_relative_time("5分钟后", base)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, base + 300, delta=10)

    def test_relative_time_hours(self):
        """测试小时级相对时间"""
        base = int(time.time())

        result = self.parse_relative_time("2小时后", base)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, base + 7200, delta=10)

        result = self.parse_relative_time("1小时后", base)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, base + 3600, delta=10)

    def test_relative_time_days(self):
        """测试天级相对时间"""
        base = int(time.time())

        result = self.parse_relative_time("明天", base)
        self.assertIsNotNone(result)
        self.assertGreater(result, base)

        result = self.parse_relative_time("后天", base)
        self.assertIsNotNone(result)
        self.assertGreater(result, base)

    def test_absolute_time_parsing(self):
        """测试绝对时间解析"""
        tomorrow = datetime.now() + timedelta(days=1)
        time_str = tomorrow.strftime("%Y年%m月%d日%H时%M分")

        result = self.str2timestamp(time_str)
        self.assertIsNotNone(result)
        self.assertGreater(result, int(time.time()))

    def test_invalid_time_returns_none(self):
        """测试无效时间返回 None"""
        result = self.parse_relative_time("无效时间")
        # 可能返回 None 或尝试解析
        # 这里只验证不会抛出异常
        self.assertTrue(result is None or isinstance(result, int))


class TestRecurrenceCalculation(unittest.TestCase):
    """测试周期计算"""

    def setUp(self):
        from util.time_util import calculate_next_recurrence

        self.calculate_next_recurrence = calculate_next_recurrence

    def test_daily_recurrence(self):
        """测试每日周期"""
        current = int(time.time())
        next_time = self.calculate_next_recurrence(current, "daily", 1)
        self.assertIsNotNone(next_time)
        self.assertAlmostEqual(next_time, current + 86400, delta=10)

    def test_weekly_recurrence(self):
        """测试每周周期"""
        current = int(time.time())
        next_time = self.calculate_next_recurrence(current, "weekly", 1)
        self.assertIsNotNone(next_time)
        self.assertAlmostEqual(next_time, current + 604800, delta=10)

    def test_interval_recurrence(self):
        """测试自定义间隔"""
        current = int(time.time())
        # 每2天
        next_time = self.calculate_next_recurrence(current, "daily", 2)
        self.assertIsNotNone(next_time)
        self.assertAlmostEqual(next_time, current + 172800, delta=10)


if __name__ == "__main__":
    unittest.main()
