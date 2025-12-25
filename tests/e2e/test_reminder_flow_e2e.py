# -*- coding: utf-8 -*-
"""
提醒功能端到端测试
"""
import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestReminderFlowE2E:
    """提醒功能端到端测试"""

    def test_reminder_creation_flow(self, sample_reminder):
        """测试提醒创建流程"""
        assert sample_reminder is not None
        assert "reminder_id" in sample_reminder
        assert "title" in sample_reminder
        assert "next_trigger_time" in sample_reminder

    def test_reminder_structure(self, sample_reminder):
        """测试提醒数据结构"""
        required_keys = [
            "reminder_id",
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
