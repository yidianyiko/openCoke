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


def _product_notification_input():
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv_1",
        text="好的",
        payload=UserTurnPayload(
            metadata={
                "product_notification": {
                    "request_id": "srr_1",
                    "request_type": "shared_reminder_request",
                    "allowed_actions": ["accept", "reject"],
                    "kind": "shared_reminder_request",
                }
            }
        ),
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
    assert (
        "explicit user-link, friend-request, friendship/block, or shared-reminder "
        "actions"
    ) in text


def test_delegation_boundary_keeps_direct_utility_tools_out_of_domain_routing():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Use timezone, calendar_import, or url_context directly" in text


def test_delegation_boundary_falls_back_to_direct_response():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "respond directly without calling a domain tool" in text


def test_delegation_boundary_blocks_casual_reminder_creation():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Ordinary one-person reminders must use the Reminder Runtime path" in text
    assert "Do not invent a reminder or scheduling action" in text
    assert "casual mention of time" in text


def test_reminder_tool_boundary_is_removed():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Reminder tool boundary:" not in text
    assert "Use the reminder tool only when" not in text


def test_delegation_boundary_restores_scheduling_safety_policy():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Scheduling tool boundary:" not in text
    assert "A shared reminder requires one active friend" in text
    assert "the user must add them as a friend first" in text
    assert "If the friend name is ambiguous" in text
    assert "ask the user to choose one friend" in text
    assert "Do not treat an iLink QR as a public friend-link QR" in text
    assert "personal-channel binding" in text
    assert "Ask for confirmation before reset/disable user link" in text
    assert "accept/reject/cancel requests" in text
    assert "remove friendship, block, or unblock" in text


def test_product_notification_metadata_is_exposed_as_trusted_context():
    text = build_chat_response_instructions(_run_context(), _product_notification_input())

    assert "product_notification:" in text
    assert '"request_id": "srr_1"' in text
    assert '"request_type": "shared_reminder_request"' in text
    assert '"allowed_actions": ["accept", "reject"]' in text
