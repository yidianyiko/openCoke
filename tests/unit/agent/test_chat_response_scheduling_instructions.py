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


def test_delegation_boundary_keeps_direct_utility_tools_out_of_domain_routing():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Use timezone, calendar_import, or url_context directly" in text


def test_delegation_boundary_falls_back_to_direct_response():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "respond directly without calling a domain tool" in text


def test_delegation_boundary_blocks_casual_reminder_creation():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Do not invent a reminder or scheduling action" in text
    assert "casual mention of time" in text


def test_reminder_tool_boundary_is_removed():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Reminder tool boundary:" not in text
    assert "Use the reminder tool only when" not in text


def test_delegation_boundary_restores_scheduling_safety_policy():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Scheduling tool boundary:" not in text
    assert "A-side link management" in text
    assert "B-side appointment actions" in text
    assert "role, provider, or target account is ambiguous" in text
    assert "ask a short clarification" in text
    assert "Do not create appointment state" in text
    assert "Do not reveal raw user-link codes" in text
    assert "Ask the user to confirm before irreversible scheduling changes" in text
    assert "Pending appointment holds do not expire automatically" in text
