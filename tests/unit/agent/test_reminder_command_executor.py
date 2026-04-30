from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.adapters import ReminderCommandExecutor
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(
            id="user-1",
            nickname="User",
            timezone="Asia/Tokyo",
        ),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: remind me to hydrate",
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )


def test_success_calls_tool_once_with_decision_and_trusted_context_kwargs():
    calls = []

    def tool_entrypoint(**kwargs):
        calls.append(kwargs)
        return "Reminder created."

    decision = SimpleNamespace(
        action="create",
        title="hydrate",
        trigger_at="2026-05-01T09:00:00+09:00",
    )

    result = ReminderCommandExecutor(tool_entrypoint).execute(
        decision,
        _run_context(),
    )

    assert result.name == "reminder"
    assert result.ok is True
    assert result.content == {
        "summary": "Reminder created.",
        "owner_user_id": "user-1",
        "conversation_id": "conv-1",
    }
    assert calls == [
        {
            "action": "create",
            "title": "hydrate",
            "trigger_at": "2026-05-01T09:00:00+09:00",
            "reminder_id": None,
            "keyword": None,
            "new_title": None,
            "new_trigger_at": None,
            "rrule": None,
            "operations": None,
            "owner_user_id": "user-1",
            "character_id": "char-1",
            "conversation_id": "conv-1",
            "timezone": "Asia/Tokyo",
            "platform": "business",
        }
    ]


def test_dict_decision_input_is_supported_and_empty_operations_becomes_none():
    calls = []

    def tool_entrypoint(**kwargs):
        calls.append(kwargs)
        return "Reminder updated."

    decision = {
        "action": "update",
        "reminder_id": "rem-1",
        "keyword": "hydrate",
        "new_title": "drink water",
        "new_trigger_at": "2026-05-01T10:00:00+09:00",
        "rrule": "FREQ=DAILY",
        "operations": [],
    }

    result = ReminderCommandExecutor(tool_entrypoint).execute(
        decision,
        _run_context(),
    )

    assert result.ok is True
    assert result.content["summary"] == "Reminder updated."
    assert calls[0]["action"] == "update"
    assert calls[0]["title"] is None
    assert calls[0]["reminder_id"] == "rem-1"
    assert calls[0]["keyword"] == "hydrate"
    assert calls[0]["new_title"] == "drink water"
    assert calls[0]["new_trigger_at"] == "2026-05-01T10:00:00+09:00"
    assert calls[0]["rrule"] == "FREQ=DAILY"
    assert calls[0]["operations"] is None


def test_failure_returns_capability_error_without_raising():
    def tool_entrypoint(**kwargs):
        raise RuntimeError("reminder store unavailable")

    result = ReminderCommandExecutor(tool_entrypoint).execute(
        {"action": "create", "title": "hydrate"},
        _run_context(),
    )

    assert result.name == "reminder"
    assert result.ok is False
    assert result.content == {}
    assert result.error == "ReminderCommandExecutorError"
    assert result.metadata["message"] == "reminder store unavailable"
