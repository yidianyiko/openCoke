# -*- coding: utf-8 -*-
import json

import pytest


@pytest.mark.unit
def test_complete_blocks_without_intent_or_keyword_in_user_text(sample_context, monkeypatch):
    from agent.agno_agent.tools import reminder_tools

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def filter_reminders(self, user_id, status_list=None, reminder_type=None, keyword=None, trigger_after=None, trigger_before=None):
            return [
                {"reminder_id": "r1", "title": "休息", "next_trigger_time": 1737314400, "status": "active"},
                {"reminder_id": "r2", "title": "喝水", "next_trigger_time": 1737318000, "status": "active"},
            ]

        def complete_reminders_by_keyword(self, user_id, keyword):
            raise AssertionError("should not execute complete when blocked by guard")

        def close(self):
            return None

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message_type": "text", "message": "就这样吧，我先去吃饭", "input_timestamp": 1737314222}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="complete", session_state=sample_context, keyword="休息"
    )

    assert result["ok"] is False
    assert result.get("needs_confirmation") is True
    assert result.get("candidates")
    assert "【提醒设置工具消息】" in sample_context
    assert "提醒完成未执行" in sample_context["【提醒设置工具消息】"]


@pytest.mark.unit
def test_complete_allows_when_active_title_in_user_text_even_if_keyword_wrong(
    sample_context, monkeypatch
):
    from agent.agno_agent.tools import reminder_tools

    called = {"keyword": None}

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def filter_reminders(self, user_id, status_list=None, reminder_type=None, keyword=None, trigger_after=None, trigger_before=None):
            return [
                {"reminder_id": "r1", "title": "休息", "next_trigger_time": 1737314400, "status": "active"}
            ]

        def complete_reminders_by_keyword(self, user_id, keyword):
            called["keyword"] = keyword
            return 1, [{"reminder_id": "r1", "title": "休息"}]

        def close(self):
            return None

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message_type": "text", "message": "帮我把休息提醒完成掉", "input_timestamp": 1737314222}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="complete", session_state=sample_context, keyword="随便"
    )

    assert result["ok"] is True
    assert called["keyword"] == "休息"


@pytest.mark.unit
def test_complete_blocks_even_if_intent_only_and_single_candidate(sample_context, monkeypatch):
    from agent.agno_agent.tools import reminder_tools

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def filter_reminders(self, user_id, status_list=None, reminder_type=None, keyword=None, trigger_after=None, trigger_before=None):
            return [
                {"reminder_id": "r9", "title": "喝水", "next_trigger_time": 1737314400, "status": "active"}
            ]

        def complete_reminders_by_keyword(self, user_id, keyword):
            raise AssertionError("should not execute complete when keyword/title not in user text")

        def close(self):
            return None

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message_type": "text", "message": "把提醒完成了", "input_timestamp": 1737314222}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="complete", session_state=sample_context, keyword="休息"
    )

    assert result["ok"] is False
    assert result.get("needs_confirmation") is True


@pytest.mark.unit
def test_delete_all_requires_explicit_all_words(sample_context, monkeypatch):
    from agent.agno_agent.tools import reminder_tools

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def filter_reminders(self, user_id, status_list=None, reminder_type=None, keyword=None, trigger_after=None, trigger_before=None):
            return [
                {"reminder_id": "r1", "title": "休息", "next_trigger_time": 1737314400, "status": "active"},
                {"reminder_id": "r2", "title": "喝水", "next_trigger_time": 1737318000, "status": "active"},
            ]

        def delete_all_by_user(self, user_id):
            raise AssertionError("should not delete all when blocked by guard")

        def close(self):
            return None

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message_type": "text", "message": "帮我把提醒删掉", "input_timestamp": 1737314222}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="delete", session_state=sample_context, keyword="*"
    )

    assert result["ok"] is False
    assert result.get("needs_confirmation") is True


@pytest.mark.unit
def test_batch_complete_is_guarded(sample_context, monkeypatch):
    from agent.agno_agent.tools import reminder_tools

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def filter_reminders(self, user_id, status_list=None, reminder_type=None, keyword=None, trigger_after=None, trigger_before=None):
            return [
                {"reminder_id": "r1", "title": "休息", "next_trigger_time": 1737314400, "status": "active"}
            ]

        def complete_reminders_by_keyword(self, user_id, keyword):
            raise AssertionError("should not execute complete when blocked by guard")

        def close(self):
            return None

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message_type": "text", "message": "就这样吧", "input_timestamp": 1737314222}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    operations = json.dumps([{"action": "complete", "keyword": "休息"}], ensure_ascii=False)
    result = reminder_tools.reminder_tool.entrypoint(
        action="batch", session_state=sample_context, operations=operations
    )

    assert result["ok"] is False
    failed = [r for r in result.get("results", []) if not r.get("ok")]
    assert failed
