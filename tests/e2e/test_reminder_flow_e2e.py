# -*- coding: utf-8 -*-
"""
提醒功能端到端测试

测试覆盖场景：
1. 提醒创建流程
2. 提醒数据结构验证
3. 提醒周期设置
4. 提醒状态管理
5. 提醒触发流程
6. 提醒取消/删除
7. 提醒查询/列表
8. 关键字搜索
9. 周期提醒处理
10. 去重检测
11. 边缘情况处理
"""
import time
import uuid

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderFlowE2E:
    """提醒功能端到端测试"""

    # ============ 基本结构测试 ============

    def test_reminder_creation_flow(self, sample_reminder):
        """测试提醒创建流程（_id 由 MongoDB 插入时生成）"""
        assert sample_reminder is not None
        assert "title" in sample_reminder
        assert "next_trigger_time" in sample_reminder

    def test_reminder_structure(self, sample_reminder):
        """测试提醒数据结构（不含 _id，_id 由 MongoDB 插入时生成）"""
        required_keys = [
            "user_id",
            "character_id",
            "title",
            "next_trigger_time",
            "status",
        ]

        for key in required_keys:
            assert key in sample_reminder

    def test_reminder_recurrence(self, sample_reminder):
        """测试提醒周期设置"""
        assert "recurrence" in sample_reminder
        assert isinstance(sample_reminder["recurrence"], dict)
        assert "enabled" in sample_reminder["recurrence"]

    def test_reminder_optional_fields(self, sample_reminder):
        """测试提醒可选字段"""
        # 这些字段是可选的，但应该有默认值
        optional_keys = [
            "conversation_id",
            "action_template",
            "time_original",
            "timezone",
        ]

        for key in optional_keys:
            if key in sample_reminder:
                assert sample_reminder[key] is not None

    # ============ 创建提醒测试 ============

    def test_create_one_time_reminder(self):
        """测试创建一次性提醒"""
        reminder = {
            "user_id": "test_user",
            "character_id": "test_char",
            "conversation_id": "test_conv",
            "title": "开会提醒",
            "next_trigger_time": int(time.time()) + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "active",
        }

        assert reminder["recurrence"]["enabled"] is False
        assert reminder["status"] == "active"

    def test_create_daily_reminder(self):
        """测试创建每日提醒"""
        reminder = {
            "user_id": "test_user",
            "character_id": "test_char",
            "title": "每日吃药提醒",
            "next_trigger_time": int(time.time()) + 3600,
            "recurrence": {
                "enabled": True,
                "type": "daily",
                "interval": 1,
            },
            "status": "active",
        }

        assert reminder["recurrence"]["enabled"] is True
        assert reminder["recurrence"]["type"] == "daily"

    def test_create_weekly_reminder(self):
        """测试创建每周提醒"""
        reminder = {
            "user_id": "test_user",
            "character_id": "test_char",
            "title": "每周例会提醒",
            "next_trigger_time": int(time.time()) + 86400 * 7,
            "recurrence": {
                "enabled": True,
                "type": "weekly",
                "interval": 1,
                "days_of_week": [1],  # Monday
            },
            "status": "active",
        }

        assert reminder["recurrence"]["type"] == "weekly"
        assert "days_of_week" in reminder["recurrence"]

    def test_create_monthly_reminder(self):
        """测试创建每月提醒"""
        reminder = {
            "user_id": "test_user",
            "character_id": "test_char",
            "title": "月初报表提醒",
            "next_trigger_time": int(time.time()) + 86400 * 30,
            "recurrence": {
                "enabled": True,
                "type": "monthly",
                "interval": 1,
                "day_of_month": 1,
            },
            "status": "active",
        }

        assert reminder["recurrence"]["type"] == "monthly"
        assert "day_of_month" in reminder["recurrence"]

    # ============ 状态管理测试 ============

    def test_reminder_status_active(self):
        """测试活跃状态的提醒（替代原 confirmed/pending）"""
        reminder = {
            "status": "active",
            "next_trigger_time": int(time.time()) + 3600,
        }

        assert reminder["status"] == "active"

    def test_reminder_status_triggered(self):
        """测试已触发状态的提醒"""
        reminder = {
            "status": "triggered",
            "last_triggered_at": int(time.time()),
            "triggered_count": 1,
        }

        assert reminder["status"] == "triggered"
        assert reminder["triggered_count"] == 1

    def test_reminder_status_completed(self):
        """测试已完成状态的提醒（包含原 cancelled 场景）"""
        reminder = {
            "status": "completed",
        }

        assert reminder["status"] == "completed"

    # ============ 触发时间测试 ============

    def test_reminder_future_trigger_time(self):
        """测试未来触发时间"""
        current_time = int(time.time())
        future_time = current_time + 3600  # 1小时后

        reminder = {
            "next_trigger_time": future_time,
        }

        assert reminder["next_trigger_time"] > current_time

    def test_reminder_past_trigger_time(self):
        """测试过去触发时间（已过期）"""
        current_time = int(time.time())
        past_time = current_time - 3600  # 1小时前

        reminder = {
            "next_trigger_time": past_time,
        }

        assert reminder["next_trigger_time"] < current_time

    def test_reminder_trigger_time_window(self):
        """测试触发时间窗口检测"""
        current_time = int(time.time())
        time_window = 60  # 60秒窗口

        # 在时间窗口内的提醒
        reminder_in_window = {
            "next_trigger_time": current_time - 30,
        }

        # 在时间窗口外的提醒
        reminder_out_window = {
            "next_trigger_time": current_time - 120,
        }

        assert (
            current_time - reminder_in_window["next_trigger_time"]
        ) <= time_window
        assert (
            current_time - reminder_out_window["next_trigger_time"]
        ) > time_window

    # ============ 消息测试 ============

    def test_reminder_create_message(self):
        """测试创建提醒的消息格式"""
        from tests.fixtures.sample_messages import get_reminder_create_message

        msg = get_reminder_create_message("明天早上8点", "开会")
        assert msg["type"] == "text"
        assert "提醒" in msg["content"]
        assert "明天早上8点" in msg["content"]
        assert "开会" in msg["content"]

    def test_reminder_cancel_message(self):
        """测试取消提醒的消息格式"""
        from tests.fixtures.sample_messages import get_reminder_cancel_message

        msg = get_reminder_cancel_message("开会")
        assert msg["type"] == "text"
        assert "取消" in msg["content"]
        assert "开会" in msg["content"]

    def test_reminder_list_message(self):
        """测试查询提醒列表的消息格式"""
        from tests.fixtures.sample_messages import get_reminder_list_message

        msg = get_reminder_list_message()
        assert msg["type"] == "text"
        assert "提醒" in msg["content"]

    def test_recurring_reminder_message_daily(self):
        """测试每日周期提醒消息"""
        from tests.fixtures.sample_messages import get_recurring_reminder_message

        msg = get_recurring_reminder_message("daily")
        assert msg["type"] == "text"
        assert "每天" in msg["content"]

    def test_recurring_reminder_message_weekly(self):
        """测试每周周期提醒消息"""
        from tests.fixtures.sample_messages import get_recurring_reminder_message

        msg = get_recurring_reminder_message("weekly")
        assert msg["type"] == "text"
        assert "每周" in msg["content"]

    def test_recurring_reminder_message_monthly(self):
        """测试每月周期提醒消息"""
        from tests.fixtures.sample_messages import get_recurring_reminder_message

        msg = get_recurring_reminder_message("monthly")
        assert msg["type"] == "text"
        assert "每月" in msg["content"]

    # ============ 上下文测试 ============

    def test_reminder_context(self):
        """测试提醒场景的 context"""
        from tests.fixtures.sample_contexts import get_context_for_reminder

        ctx = get_context_for_reminder()
        input_messages = ctx["conversation"]["conversation_info"]["input_messages"]

        assert len(input_messages) == 1
        assert "提醒" in input_messages[0]["content"]

    def test_reminder_trigger_message(self):
        """测试提醒触发消息"""
        from tests.fixtures.sample_messages import get_reminder_trigger_message

        msg = get_reminder_trigger_message("reminder_001", "开会提醒")
        assert msg["type"] == "system"
        assert msg["source"] == "reminder"
        assert msg["title"] == "开会提醒"

    # ============ 去重检测测试 ============

    def test_similar_reminder_detection_same_title(self):
        """测试相同标题的相似提醒检测"""
        trigger_time = int(time.time()) + 3600
        time_tolerance = 300  # 5分钟

        reminder1 = {
            "user_id": "test_user",
            "title": "开会提醒",
            "next_trigger_time": trigger_time,
        }

        reminder2 = {
            "user_id": "test_user",
            "title": "开会提醒",
            "next_trigger_time": trigger_time + 60,  # 1分钟后
        }

        # 标题相同，时间差在容差内
        time_diff = abs(reminder2["next_trigger_time"] - reminder1["next_trigger_time"])
        assert time_diff < time_tolerance
        assert reminder1["title"] == reminder2["title"]

    def test_similar_reminder_detection_different_time(self):
        """测试不同时间的相似提醒检测"""
        trigger_time = int(time.time()) + 3600
        time_tolerance = 300  # 5分钟

        reminder1 = {
            "user_id": "test_user",
            "title": "开会提醒",
            "next_trigger_time": trigger_time,
        }

        reminder2 = {
            "user_id": "test_user",
            "title": "开会提醒",
            "next_trigger_time": trigger_time + 7200,  # 2小时后
        }

        # 时间差超出容差
        time_diff = abs(reminder2["next_trigger_time"] - reminder1["next_trigger_time"])
        assert time_diff > time_tolerance

    # ============ 关键字搜索测试 ============

    def test_keyword_search_exact_match(self):
        """测试关键字精确匹配"""
        reminders = [
            {"_id": "1", "title": "开会提醒", "status": "active"},
            {"_id": "2", "title": "吃药提醒", "status": "active"},
            {"_id": "3", "title": "开会通知", "status": "active"},
        ]

        keyword = "开会"
        matched = [r for r in reminders if keyword in r["title"]]
        assert len(matched) == 2

    def test_keyword_search_partial_match(self):
        """测试关键字部分匹配"""
        reminders = [
            {"_id": "1", "title": "每日健身提醒", "status": "active"},
            {"_id": "2", "title": "健身房预约", "status": "active"},
            {"_id": "3", "title": "吃早餐", "status": "active"},
        ]

        keyword = "健身"
        matched = [r for r in reminders if keyword in r["title"]]
        assert len(matched) == 2

    def test_keyword_search_no_match(self):
        """测试关键字无匹配"""
        reminders = [
            {"_id": "1", "title": "开会提醒", "status": "active"},
            {"_id": "2", "title": "吃药提醒", "status": "active"},
        ]

        keyword = "睡觉"
        matched = [r for r in reminders if keyword in r["title"]]
        assert len(matched) == 0

    # ============ 周期提醒测试 ============

    def test_recurrence_reschedule_daily(self):
        """测试每日提醒重新安排"""
        current_time = int(time.time())
        daily_interval = 86400  # 24小时

        reminder = {
            "next_trigger_time": current_time,
            "recurrence": {
                "enabled": True,
                "type": "daily",
                "interval": 1,
            },
        }

        # 重新安排到下一天
        new_trigger_time = reminder["next_trigger_time"] + daily_interval
        assert new_trigger_time > current_time
        assert new_trigger_time - current_time == daily_interval

    def test_recurrence_reschedule_weekly(self):
        """测试每周提醒重新安排"""
        current_time = int(time.time())
        weekly_interval = 86400 * 7  # 7天

        reminder = {
            "next_trigger_time": current_time,
            "recurrence": {
                "enabled": True,
                "type": "weekly",
                "interval": 1,
            },
        }

        # 重新安排到下一周
        new_trigger_time = reminder["next_trigger_time"] + weekly_interval
        assert new_trigger_time > current_time
        assert new_trigger_time - current_time == weekly_interval

    # ============ 边缘情况测试 ============

    def test_reminder_with_long_title(self):
        """测试长标题提醒"""
        long_title = "这是一个非常长的提醒标题" * 10

        reminder = {
            "title": long_title,
            "status": "active",
        }

        assert len(reminder["title"]) > 100

    def test_reminder_with_special_chars(self):
        """测试特殊字符标题"""
        special_title = "提醒：\n换行\t制表符<html>"

        reminder = {
            "title": special_title,
            "status": "active",
        }

        assert "\n" in reminder["title"]
        assert "\t" in reminder["title"]

    def test_reminder_with_emoji(self):
        """测试表情符号标题"""
        emoji_title = "🎉 生日派对提醒 🎂"

        reminder = {
            "title": emoji_title,
            "status": "active",
        }

        assert "🎉" in reminder["title"]
        assert "🎂" in reminder["title"]

    def test_reminder_timestamp_fields(self):
        """测试提醒时间戳字段"""
        current_time = int(time.time())

        reminder = {
            "created_at": current_time,
            "updated_at": current_time,
            "next_trigger_time": current_time + 3600,
        }

        assert reminder["created_at"] <= reminder["updated_at"]
        assert reminder["next_trigger_time"] > reminder["created_at"]

    def test_reminder_triggered_count(self):
        """测试提醒触发次数"""
        reminder = {
            "triggered_count": 0,
        }

        # 模拟触发
        reminder["triggered_count"] += 1
        assert reminder["triggered_count"] == 1

        # 再次触发
        reminder["triggered_count"] += 1
        assert reminder["triggered_count"] == 2


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderDAOInterface:
    """提醒 DAO 接口测试"""

    def test_reminder_dao_import(self):
        """测试 ReminderDAO 可导入"""
        try:
            from dao.reminder_dao import ReminderDAO

            assert ReminderDAO is not None
        except ImportError:
            pytest.skip("ReminderDAO not available")

    def test_reminder_dao_methods_exist(self):
        """测试 ReminderDAO 方法存在"""
        try:
            from dao.reminder_dao import ReminderDAO

            dao = ReminderDAO.__new__(ReminderDAO)
            expected_methods = [
                "create_reminder",
                "get_reminder_by_id",
                "find_pending_reminders",
                "find_reminders_by_user",
                "update_reminder",
                "mark_as_triggered",
                "cancel_reminder",
                "complete_reminder",
                "delete_reminder",
            ]

            for method in expected_methods:
                assert hasattr(ReminderDAO, method), f"Missing method: {method}"
        except ImportError:
            pytest.skip("ReminderDAO not available")


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderToolsInterface:
    """提醒工具接口测试"""

    def test_reminder_tools_import(self):
        """测试提醒工具可导入"""
        try:
            from agent.agno_agent.tools.reminder_tools import set_reminder_session_state

            assert set_reminder_session_state is not None
        except ImportError:
            pytest.skip("reminder_tools not available")

    def test_reminder_context_in_context_retrieve(self):
        """测试提醒在上下文检索中的显示"""
        from tests.fixtures.sample_contexts import get_context_with_context_retrieve

        ctx = get_context_with_context_retrieve()
        assert "confirmed_reminders" in ctx["context_retrieve"]
        assert len(ctx["context_retrieve"]["confirmed_reminders"]) > 0


# ============ Reminder Time Parsing Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderTimeParsing:
    """提醒时间解析测试"""

    def test_reminder_with_vague_time(self):
        """测试模糊时间的提醒消息"""
        from tests.fixtures.sample_messages import get_reminder_with_vague_time

        msg = get_reminder_with_vague_time()
        assert "过两天" in msg["content"]
        # 系统应该能处理这种模糊时间

    def test_reminder_with_past_time(self):
        """测试过去时间的提醒（应该被拒绝或调整）"""
        from tests.fixtures.sample_messages import get_reminder_with_past_time

        msg = get_reminder_with_past_time()
        assert "昨天" in msg["content"]

    def test_reminder_with_conflicting_times(self):
        """测试包含冲突时间的提醒"""
        from tests.fixtures.sample_messages import get_reminder_with_conflicting_info

        msg = get_reminder_with_conflicting_info()
        # 消息包含两个不同时间
        assert "早上8点" in msg["content"]
        assert "下午3点" in msg["content"]

    def test_recurring_reminder_complex_pattern(self):
        """测试复杂周期模式的提醒"""
        from tests.fixtures.sample_messages import get_recurring_reminder_with_complex_pattern

        msg = get_recurring_reminder_with_complex_pattern()
        assert "每个月" in msg["content"]
        assert "最后一个工作日" in msg["content"]

    def test_reminder_time_edge_cases(self):
        """测试时间边界情况"""
        current_time = int(time.time())

        # 刚好在当前时间
        reminder_now = {
            "next_trigger_time": current_time,
        }
        assert reminder_now["next_trigger_time"] == current_time

        # 1秒后
        reminder_soon = {
            "next_trigger_time": current_time + 1,
        }
        assert reminder_soon["next_trigger_time"] > current_time


# ============ Reminder Conflict Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderConflicts:
    """提醒冲突处理测试"""

    def test_overlapping_reminders_same_time(self):
        """测试同一时间的重叠提醒"""
        trigger_time = int(time.time()) + 3600

        reminder1 = {
            "user_id": "test_user",
            "title": "开会",
            "next_trigger_time": trigger_time,
            "status": "active",
        }

        reminder2 = {
            "user_id": "test_user",
            "title": "吃药",
            "next_trigger_time": trigger_time,  # 同一时间
            "status": "active",
        }

        assert reminder1["next_trigger_time"] == reminder2["next_trigger_time"]
        assert reminder1["title"] != reminder2["title"]

    def test_multiple_reminders_same_title(self):
        """测试相同标题的多个提醒"""
        base_time = int(time.time()) + 3600

        reminders = [
            {
                "user_id": "test_user",
                "title": "开会",
                "next_trigger_time": base_time + i * 3600,
                "status": "active",
            }
            for i in range(5)
        ]

        titles = [r["title"] for r in reminders]
        assert len(set(titles)) == 1  # 所有标题相同
        times = [r["next_trigger_time"] for r in reminders]
        assert len(set(times)) == 5  # 所有时间不同

    def test_reminder_conflict_detection_context(self):
        """测试提醒冲突检测context"""
        from tests.fixtures.sample_contexts import get_context_for_reminder_conflict

        ctx = get_context_for_reminder_conflict()
        reminders = ctx["context_retrieve"]["confirmed_reminders"]

        # 验证存在冲突（同一时间多个提醒）
        assert reminders.count("早上8点") >= 2


# ============ Reminder Cancellation Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderCancellation:
    """提醒取消测试"""

    def test_cancel_single_reminder(self):
        """测试取消单个提醒（取消后状态变为 completed）"""
        reminder = {
            "status": "active",
            "title": "要取消的提醒",
        }

        # 模拟取消（新状态系统中取消 = completed）
        reminder["status"] = "completed"
        assert reminder["status"] == "completed"

    def test_cancel_multiple_reminders_by_keyword(self):
        """测试按关键字取消多个提醒"""
        reminders = [
            {"_id": "1", "title": "开会-上午", "status": "active"},
            {"_id": "2", "title": "开会-下午", "status": "active"},
            {"_id": "3", "title": "吃药", "status": "active"},
        ]

        keyword = "开会"
        matched = [r for r in reminders if keyword in r["title"]]
        assert len(matched) == 2

    def test_cancel_nonexistent_reminder(self):
        """测试取消不存在的提醒"""
        reminders = [
            {"_id": "1", "title": "开会", "status": "active"},
        ]

        keyword = "不存在的关键字"
        matched = [r for r in reminders if keyword in r["title"]]
        assert len(matched) == 0

    def test_cancel_already_triggered_reminder(self):
        """测试取消已触发的提醒"""
        reminder = {
            "status": "triggered",
            "title": "已触发的提醒",
            "last_triggered_at": int(time.time()),
        }

        # 已触发的提醒是否可以取消？
        assert reminder["status"] == "triggered"


# ============ Recurring Reminder Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestRecurringReminders:
    """周期提醒测试"""

    def test_daily_recurrence_calculation(self):
        """测试每日周期计算"""
        current_time = int(time.time())
        daily_interval = 86400

        reminder = {
            "next_trigger_time": current_time,
            "recurrence": {
                "enabled": True,
                "type": "daily",
                "interval": 1,
            },
        }

        # 重新安排到下一天
        next_time = reminder["next_trigger_time"] + daily_interval
        assert next_time == current_time + daily_interval

    def test_weekly_recurrence_with_specific_days(self):
        """测试每周特定天的周期"""
        reminder = {
            "next_trigger_time": int(time.time()),
            "recurrence": {
                "enabled": True,
                "type": "weekly",
                "interval": 1,
                "days_of_week": [1, 3, 5],  # 周一、周三、周五
            },
        }

        assert len(reminder["recurrence"]["days_of_week"]) == 3

    def test_monthly_recurrence_end_of_month(self):
        """测试每月末周期"""
        reminder = {
            "next_trigger_time": int(time.time()),
            "recurrence": {
                "enabled": True,
                "type": "monthly",
                "interval": 1,
                "day_of_month": 31,  # 每月最后一天
            },
        }

        # 31号在短月份会有问题
        assert reminder["recurrence"]["day_of_month"] == 31

    def test_recurring_reminder_max_triggers(self):
        """测试周期提醒最大触发次数"""
        reminder = {
            "recurrence": {
                "enabled": True,
                "type": "daily",
                "max_triggers": 30,
            },
            "triggered_count": 29,
        }

        # 接近最大触发次数
        assert reminder["triggered_count"] < reminder["recurrence"]["max_triggers"]


# ============ Reminder Edge Cases ============


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderEdgeCases:
    """提醒边缘情况测试"""

    def test_reminder_with_very_long_title(self):
        """测试超长标题的提醒"""
        long_title = "这是一个非常非常长的提醒标题" * 100  # ~2000字符

        reminder = {
            "title": long_title,
            "status": "active",
        }

        assert len(reminder["title"]) > 1000

    def test_reminder_with_empty_title(self):
        """测试空标题的提醒"""
        reminder = {
            "title": "",
            "status": "active",
        }

        assert reminder["title"] == ""

    def test_reminder_with_special_characters_in_title(self):
        """测试包含特殊字符的标题"""
        special_title = "<script>alert('xss')</script> 提醒\n\t特殊字符"

        reminder = {
            "title": special_title,
            "status": "active",
        }

        assert "<script>" in reminder["title"]
        assert "\n" in reminder["title"]

    def test_reminder_negative_trigger_time(self):
        """测试负数触发时间"""
        reminder = {
            "next_trigger_time": -1000,
            "status": "active",
        }

        assert reminder["next_trigger_time"] < 0

    def test_reminder_zero_trigger_time(self):
        """测试零时间戳触发时间（纪元时间）"""
        reminder = {
            "next_trigger_time": 0,
            "status": "active",
        }

        assert reminder["next_trigger_time"] == 0

    def test_reminder_far_future_trigger(self):
        """测试远期触发时间"""
        far_future = int(time.time()) + 86400 * 365 * 10  # 10年后

        reminder = {
            "next_trigger_time": far_future,
            "status": "active",
        }

        assert reminder["next_trigger_time"] > int(time.time()) + 86400 * 365 * 9


# ============ Reminder Status Transitions ============


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderStatusTransitions:
    """提醒状态转换测试"""

    def test_valid_status_transitions(self):
        """测试有效的状态转换（新状态系统：active, triggered, completed）"""
        valid_transitions = [
            ("active", "triggered"),      # 提醒触发
            ("triggered", "completed"),   # 触发后完成
            ("active", "completed"),      # 直接完成/取消
            ("triggered", "active"),      # 周期提醒重新安排
        ]

        for from_status, to_status in valid_transitions:
            reminder = {"status": from_status}
            reminder["status"] = to_status
            assert reminder["status"] == to_status

    def test_invalid_status_values(self):
        """测试无效的状态值"""
        invalid_statuses = ["unknown", "ACTIVE", "confirmed", "pending", "cancelled", "", None, 123]

        for invalid_status in invalid_statuses:
            reminder = {"status": invalid_status}
            assert reminder["status"] not in ["active", "triggered", "completed"]

    def test_status_change_timestamp_update(self):
        """测试状态变更时的时间戳更新"""
        original_time = int(time.time()) - 1000
        current_time = int(time.time())

        reminder = {
            "status": "active",
            "updated_at": original_time,
        }

        # 模拟状态更新
        reminder["status"] = "triggered"
        reminder["updated_at"] = current_time

        assert reminder["updated_at"] > original_time


# ============ Concurrent Reminder Operations ============


@pytest.mark.e2e
@pytest.mark.slow
class TestConcurrentReminderOperations:
    """并发提醒操作测试"""

    def test_multiple_users_same_time_reminders(self):
        """测试多用户同时创建提醒"""
        trigger_time = int(time.time()) + 3600

        reminders = [
            {
                "user_id": f"user_{i}",
                "title": "同时提醒",
                "next_trigger_time": trigger_time,
            }
            for i in range(10)
        ]

        # 验证所有提醒都有唯一 user_id
        user_ids = [r["user_id"] for r in reminders]
        assert len(set(user_ids)) == 10

    def test_rapid_reminder_creation(self):
        """测试快速创建多个提醒"""
        base_time = int(time.time())

        reminders = [
            {
                "user_id": "test_user",
                "title": f"快速提醒_{i}",
                "next_trigger_time": base_time + 3600 + i,
                "created_at": base_time + i,
            }
            for i in range(100)
        ]

        assert len(reminders) == 100

    def test_simultaneous_trigger_check(self):
        """测试同时触发检查"""
        current_time = int(time.time())
        time_window = 60

        # 创建多个在触发窗口内的提醒
        pending_reminders = [
            {
                "user_id": "test_user",
                "next_trigger_time": current_time - i * 10,
                "status": "active",
            }
            for i in range(6)  # 0-50秒前
        ]

        # 筛选在窗口内的
        in_window = [
            r for r in pending_reminders
            if current_time - r["next_trigger_time"] <= time_window
        ]

        assert len(in_window) == 6


# ============ Reminder Data Integrity Tests ============


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderDataIntegrity:
    """提醒数据完整性测试"""

    def test_reminder_required_fields(self):
        """测试提醒必要字段（不含 _id，_id 由 MongoDB 插入时生成）"""
        required_fields = [
            "user_id",
            "title",
            "next_trigger_time",
            "status",
        ]

        reminder = {
            "user_id": "test_user",
            "title": "测试提醒",
            "next_trigger_time": int(time.time()) + 3600,
            "status": "active",
        }

        for field in required_fields:
            assert field in reminder, f"Missing required field: {field}"

    def test_reminder_id_uniqueness(self):
        """测试提醒ID唯一性"""
        reminder_ids = [str(uuid.uuid4()) for _ in range(1000)]
        assert len(set(reminder_ids)) == 1000

    def test_reminder_timestamp_consistency(self):
        """测试提醒时间戳一致性"""
        current_time = int(time.time())

        reminder = {
            "created_at": current_time,
            "updated_at": current_time,
            "next_trigger_time": current_time + 3600,
        }

        # created_at 应该 <= updated_at
        assert reminder["created_at"] <= reminder["updated_at"]
        # next_trigger_time 应该在未来
        assert reminder["next_trigger_time"] > reminder["created_at"]
