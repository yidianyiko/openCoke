from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest


def test_parse_trigger_at_requires_timezone_offset():
    from agent.agno_agent.tools.deferred_action.tool import _parse_trigger_at

    with pytest.raises(ValueError, match="timezone offset"):
        _parse_trigger_at("2026-04-28T17:57:00")


def test_parse_trigger_at_accepts_aware_iso_datetime():
    from agent.agno_agent.tools.deferred_action.tool import _parse_trigger_at

    parsed = _parse_trigger_at("2026-04-28T17:57:00+09:00")

    assert parsed == datetime(2026, 4, 28, 17, 57, tzinfo=ZoneInfo("Asia/Tokyo"))


@patch("agent.agno_agent.tools.deferred_action.tool.DeferredActionService")
def test_visible_reminder_tool_create_uses_trigger_at(mock_service_class):
    from agent.agno_agent.tools.deferred_action.tool import (
        set_deferred_action_session_state,
        visible_reminder_tool,
    )

    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Europe/London"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
        "input_timestamp": 1770000000,
    }
    mock_service = MagicMock()
    mock_service.create_visible_reminder.return_value = {"title": "开会"}
    mock_service_class.return_value = mock_service

    set_deferred_action_session_state(session_state)
    visible_reminder_tool.entrypoint(
        action="create",
        title="开会",
        trigger_at="2026-02-01T12:00:00+00:00",
    )

    mock_service.create_visible_reminder.assert_called_once_with(
        user_id="user-1",
        character_id="char-1",
        conversation_id="conv-1",
        title="开会",
        dtstart=datetime(2026, 2, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
        timezone="Europe/London",
        rrule=None,
        schedule_kind="floating_local",
        fixed_timezone=False,
    )


@patch("agent.agno_agent.tools.deferred_action.tool.DeferredActionService")
def test_visible_reminder_tool_update_uses_new_trigger_at(mock_service_class):
    from agent.agno_agent.tools.deferred_action.tool import (
        set_deferred_action_session_state,
        visible_reminder_tool,
    )

    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Europe/London"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
        "input_timestamp": 1770000000,
    }
    mock_service = MagicMock()
    mock_service.update_visible_reminder.return_value = {"title": "开会"}
    mock_service_class.return_value = mock_service

    set_deferred_action_session_state(session_state)
    visible_reminder_tool.entrypoint(
        action="update",
        reminder_id="rem-1",
        new_trigger_at="2026-02-01T12:00:00+00:00",
    )

    mock_service.update_visible_reminder.assert_called_once_with(
        action_id="rem-1",
        user_id="user-1",
        dtstart=datetime(2026, 2, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
        timezone="Europe/London",
        schedule_kind="floating_local",
        fixed_timezone=False,
    )


@patch("agent.agno_agent.tools.deferred_action.tool.DeferredActionService")
def test_visible_reminder_tool_batch_executes_ordered_operations(mock_service_class):
    from agent.agno_agent.tools.deferred_action.tool import (
        set_deferred_action_session_state,
        visible_reminder_tool,
    )

    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Asia/Tokyo"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
        "input_timestamp": 1770000000,
    }
    mock_service = MagicMock()
    mock_service.create_visible_reminder.return_value = {"title": "喝水"}
    mock_service.resolve_visible_reminder_by_keyword.return_value = {"_id": "rem-1"}
    mock_service.delete_visible_reminder.return_value = {"title": "买牛奶"}
    mock_service_class.return_value = mock_service

    set_deferred_action_session_state(session_state)
    result = visible_reminder_tool.entrypoint(
        action="batch",
        operations=[
            {
                "action": "create",
                "title": "喝水",
                "trigger_at": "2026-02-01T12:00:00+09:00",
            },
            {"action": "delete", "keyword": "买牛奶"},
        ],
    )

    assert result == "已创建提醒：喝水\n已删除提醒：买牛奶"
    mock_service.create_visible_reminder.assert_called_once()
    mock_service.delete_visible_reminder.assert_called_once_with("rem-1", "user-1")


def test_visible_reminder_tool_rejects_non_rfc_rrule():
    from agent.agno_agent.tools.deferred_action.tool import _validate_rrule

    with pytest.raises(ValueError, match="RRULE"):
        _validate_rrule("daily", datetime(2026, 2, 1, 12, 0, tzinfo=ZoneInfo("UTC")))
