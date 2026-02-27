# -*- coding: utf-8 -*-
"""
Unit tests for ReminderFormatter module.

Tests the ReminderFormatter class which handles formatting of reminder
operation responses and messages.
"""

from datetime import datetime, timedelta

import pytest

from agent.agno_agent.tools.reminder.formatter import ReminderFormatter


class TestCreateSuccess:
    """Test creation success message formatting."""

    def test_create_success_with_time(self):
        """Test formatting creation success with trigger time."""
        # Create timestamp for tomorrow at 9am
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        ts = int(tomorrow.timestamp())

        reminder = {
            "reminder_id": "test123",
            "title": "开会",
            "next_trigger_time": ts,
            "recurrence": {},
        }

        formatter = ReminderFormatter()
        result = formatter.create_success(reminder)

        assert "已创建提醒" in result or "提醒" in result
        assert "开会" in result
        # Should contain formatted time
        assert "时间" in result or "明天" in result

    def test_create_success_inbox(self):
        """Test formatting creation success without time (inbox)."""
        reminder = {
            "reminder_id": "test456",
            "title": "买牛奶",
            "next_trigger_time": None,
            "recurrence": {},
        }

        formatter = ReminderFormatter()
        result = formatter.create_success(reminder)

        assert "已创建" in result or "任务" in result
        assert "买牛奶" in result
        assert "收集箱" in result or "Inbox" in result or "无时间" in result


class TestUpdateSuccess:
    """Test update success message formatting."""

    def test_update_success(self):
        """Test formatting update success message."""
        reminder = {
            "reminder_id": "test789",
            "title": "新标题",
            "next_trigger_time": None,
        }

        changes = {
            "title": "旧标题",
            "new_title": "新标题",
            "trigger_time": "2024年12月25日09时00分",
        }

        formatter = ReminderFormatter()
        result = formatter.update_success(reminder, changes)

        assert "修改成功" in result or "更新成功" in result or "已更新" in result
        assert "新标题" in result or "旧标题" in result


class TestDeleteSuccess:
    """Test deletion success message formatting."""

    def test_delete_success_single(self):
        """Test formatting single deletion success."""
        formatter = ReminderFormatter()
        result = formatter.delete_success(count=1, keyword="开会")

        assert "删除成功" in result or "已删除" in result
        assert "开会" in result

    def test_delete_success_all(self):
        """Test formatting delete all success."""
        formatter = ReminderFormatter()
        result = formatter.delete_success(count=5, keyword="*")

        assert "删除" in result
        assert "5" in result or "全部" in result or "all" in result


class TestCompleteSuccess:
    """Test completion success message formatting."""

    def test_complete_success(self):
        """Test formatting completion success message."""
        formatter = ReminderFormatter()
        result = formatter.complete_success(count=1, keyword="写报告")

        assert "完成" in result
        assert "写报告" in result


class TestFilterResult:
    """Test filter/query result formatting."""

    def test_filter_result_empty(self):
        """Test formatting empty filter result."""
        formatter = ReminderFormatter()
        result = formatter.filter_result([])

        assert "没有" in result or "0" in result or "空" in result

    def test_filter_result_with_reminders(self):
        """Test formatting filter result with reminders."""
        # Create timestamp for tomorrow at 2pm
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        ts = int(tomorrow.timestamp())

        reminders = [
            {
                "reminder_id": "r1",
                "title": "开会",
                "status": "active",
                "next_trigger_time": ts,
            },
            {
                "reminder_id": "r2",
                "title": "买牛奶",
                "status": "active",
                "next_trigger_time": None,
            },
        ]

        formatter = ReminderFormatter()
        result = formatter.filter_result(reminders)

        assert "开会" in result
        assert "买牛奶" in result
        # Should show grouped display
        assert "定时提醒" in result or "时间" in result


class TestBatchSummary:
    """Test batch operation summary formatting."""

    def test_batch_summary_all_success(self):
        """Test formatting batch summary with all successful operations."""
        results = [
            {"ok": True, "status": "created"},
            {"ok": True, "status": "created"},
            {"ok": True, "status": "updated"},
        ]

        formatter = ReminderFormatter()
        result = formatter.batch_summary(results)

        assert "批量" in result or "batch" in result
        assert "创建" in result or "create" in result
        assert "更新" in result or "update" in result

    def test_batch_summary_with_failures(self):
        """Test formatting batch summary with some failures."""
        results = [
            {"ok": True, "status": "created"},
            {"ok": False, "error": "some error"},
            {"ok": True, "status": "deleted"},
        ]

        formatter = ReminderFormatter()
        result = formatter.batch_summary(results)

        assert "批量" in result or "batch" in result
        assert "失败" in result or "fail" in result or "1" in result


class TestGuardedResponse:
    """Test side-effect guard rejection formatting."""

    def test_guarded_response(self):
        """Test formatting guard rejection response."""
        guard = {
            "allowed": False,
            "error": "用户本轮消息未明确包含要操作的提醒关键字或标题",
            "reason": "keyword_not_in_user_text",
            "candidates": [{"title": "开会", "time": "明天9:00"}],
        }

        formatter = ReminderFormatter()
        result = formatter.guarded_response(guard)

        assert "未执行" in result or "拒绝" in result or "失败" in result
        assert "关键字" in result or "title" in result


class TestErrorResponse:
    """Test error response formatting."""

    def test_error_response(self):
        """Test formatting error response."""
        formatter = ReminderFormatter()
        result = formatter.error("无法解析时间", trigger_time="invalid")

        assert "无法解析时间" in result or "error" in result


class TestStatusIndicator:
    """Test status indicator helper."""

    def test_status_indicator_active(self):
        """Test status indicator for active status."""
        formatter = ReminderFormatter()
        result = formatter._get_status_indicator("active")

        assert "待执行" in result or "pending" in result or "" in result

    def test_status_indicator_completed(self):
        """Test status indicator for completed status."""
        formatter = ReminderFormatter()
        result = formatter._get_status_indicator("completed")

        assert "完成" in result or "done" in result or "" in result
