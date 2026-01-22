# -*- coding: utf-8 -*-
import json
import pytest


@pytest.mark.unit
def test_create_reminder_without_trigger_time_succeeds(sample_context, monkeypatch):
    """测试创建无时间提醒成功（不再返回 needs_info）"""
    from agent.agno_agent.tools import reminder_tools
    import time

    created_reminders = []

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            created_reminders.append(reminder_data)
            return "fake_object_id"

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def find_reminder_at_same_time(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    # 设置 session_state
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "帮我记一下要买牛奶", "input_timestamp": int(time.time())}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    # 调用工具，不提供 trigger_time
    result = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="买牛奶",
        trigger_time=None,  # 无时间
        session_state=sample_context
    )

    # 应该成功创建
    assert result["ok"] is True
    assert result["status"] == "created"
    assert len(created_reminders) == 1
    assert created_reminders[0]["title"] == "买牛奶"
    assert created_reminders[0]["next_trigger_time"] is None
    # list_id 是由 DAO 层在数据库写入时设置的，不在工具层的 reminder_doc 中


@pytest.mark.unit
def test_create_reminder_with_trigger_time_still_works(sample_context, monkeypatch):
    """测试创建有时间提醒仍然正常工作"""
    from agent.agno_agent.tools import reminder_tools
    import time

    created_reminders = []

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            created_reminders.append(reminder_data)
            return "fake_object_id"

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def find_reminder_at_same_time(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    # 使用固定的 base_timestamp 进行时间解析
    base_timestamp = 1737532800  # 2026-01-22 12:00:00 UTC+8

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "明天提醒我", "input_timestamp": base_timestamp}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="买牛奶",
        trigger_time="明天09时00分",
        session_state=sample_context
    )

    assert result["ok"] is True
    assert result["status"] == "created"
    assert len(created_reminders) == 1
    assert created_reminders[0]["next_trigger_time"] is not None
