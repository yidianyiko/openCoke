# -*- coding: utf-8 -*-
"""
GTD 任务系统集成测试

测试完整流程：
1. 创建无时间任务
2. 创建有时间任务
3. 查询所有任务并验证分组显示
4. 清理
"""
import pytest


@pytest.mark.unit
def test_gtd_inbox_workflow(sample_context, monkeypatch):
    """测试 GTD Inbox 工作流程"""
    import time

    from agent.agno_agent.tools import reminder_tools

    # 使用真实 DAO 的内存模拟
    class InMemoryReminderDAO:
        reminders = []
        id_counter = 1

        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            reminder_data["_id"] = str(self.id_counter)
            InMemoryReminderDAO.id_counter += 1
            InMemoryReminderDAO.reminders.append(reminder_data)
            return reminder_data["_id"]

        def filter_reminders(self, user_id, status_list=None, **kwargs):
            results = []
            for r in InMemoryReminderDAO.reminders:
                if r.get("user_id") != user_id:
                    continue
                if status_list and r.get("status") not in status_list:
                    continue
                results.append(r)
            # 按 trigger_time 排序，None 排最后
            return sorted(
                results,
                key=lambda x: (
                    x.get("next_trigger_time") is None,
                    x.get("next_trigger_time") or 0,
                ),
            )

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def close(self):
            pass

    # 在测试开始前清空数据
    InMemoryReminderDAO.reminders = []
    InMemoryReminderDAO.id_counter = 1

    monkeypatch.setattr(reminder_tools, "ReminderDAO", InMemoryReminderDAO)

    base_timestamp = int(time.time())
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "帮我记一下", "input_timestamp": base_timestamp}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    # Step 1: 创建无时间任务
    result1 = reminder_tools.reminder_tool.entrypoint(
        action="create", title="买牛奶", trigger_time=None, session_state=sample_context
    )
    assert result1["ok"] is True
    assert result1["status"] == "created"

    # Step 2: 创建另一个无时间任务（重置 session state 以允许新的 create）
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "再帮我记一下", "input_timestamp": base_timestamp + 10}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result2 = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="整理书架",
        trigger_time=None,
        session_state=sample_context,
    )
    assert result2["ok"] is True

    # Step 3: 创建有时间任务（重置 session state）
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "明天提醒我", "input_timestamp": base_timestamp + 20}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result3 = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="开会",
        trigger_time="明天09时00分",
        session_state=sample_context,
    )
    assert result3["ok"] is True

    # Step 4: 查询所有任务
    result_query = reminder_tools.reminder_tool.entrypoint(
        action="filter", session_state=sample_context
    )

    assert result_query["ok"] is True
    assert result_query["count"] == 3

    # 验证分组显示
    message = result_query["message"]
    assert "定时提醒" in message or "已安排" in message
    assert "待安排" in message or "Inbox" in message

    # 验证所有任务都在消息中
    assert "买牛奶" in message
    assert "整理书架" in message
    assert "开会" in message
