from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.runtime.chat_response_instructions import (
    build_chat_response_instructions,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload


def _run_context():
    return SimpleNamespace(
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        platform="business",
    )


def _user_turn_input():
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv_1",
        text="show my user link",
        payload=UserTurnPayload(),
        occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


def test_delegation_boundary_is_present():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Delegation boundary:" in text


def test_delegation_boundary_covers_reminder_routing():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Use reminder_domain only when" in text
    assert "explicitly requests creating" in text


def test_delegation_boundary_covers_scheduling_routing():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Use scheduling_domain(intent=..." in text
    assert "user-link management" in text
    assert "appointment actions" in text


def test_delegation_boundary_blocks_casual_reminder_creation():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Do not invent a reminder or scheduling action" in text
    assert "casual mention of time" in text


def test_scheduling_tool_boundary_is_removed():
    """_SCHEDULING_TOOL_BOUNDARY is now in execution_agents.py, not the Interaction Agent."""
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Scheduling tool boundary:" not in text
    assert "A-side link management" not in text
    assert "B-side appointment actions" not in text
