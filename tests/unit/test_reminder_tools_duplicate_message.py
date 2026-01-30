# -*- coding: utf-8 -*-
import pytest


@pytest.mark.unit
def test_create_duplicate_is_reported_as_success(sample_context, monkeypatch):
    from agent.agno_agent.tools import reminder_tools

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def find_similar_reminder(
            self, user_id, title, trigger_time, recurrence_type=None, time_tolerance=300
        ):
            return {
                "reminder_id": "r-dup",
                "title": title,
                "status": "active",
                "next_trigger_time": trigger_time,
            }

        def close(self):
            return None

    # Patch ReminderDAO at the source import location
    monkeypatch.setattr("dao.reminder_dao.ReminderDAO", FakeReminderDAO)

    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="create",
        session_state=sample_context,
        title="休息",
        trigger_time="5分钟后",
        recurrence_type="none",
    )

    assert result["ok"] is True
    assert result["status"] == "duplicate"
    assert "创建提醒成功" in sample_context.get("【提醒设置工具消息】", "")
    tool_context = sample_context.get("tool_execution_context", {})
    assert tool_context.get("intent_fulfilled") is True
    assert "创建提醒成功" in tool_context.get("result_summary", "")
