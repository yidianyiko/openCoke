from datetime import UTC, datetime

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="wechat_personal:primary",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: remind me tomorrow",
        current_time=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )


def test_manager_instructions_define_leader_boundary():
    from agent.agno_agent.prompts.manager import build_manager_instructions

    instructions = build_manager_instructions(_run_context())

    assert "You are CokeManagerTeam leader" in instructions
    assert "Do not write durable state directly" in instructions
    assert "Return user-visible text in the RESPONSE block" in instructions
    assert "REQUEST reminder_intent {}" in instructions
    assert "REQUEST url_context {}" in instructions
    assert "REQUEST timezone" in instructions
    assert "REQUEST calendar_import {}" in instructions


def test_manager_input_contains_trusted_context_and_user_text():
    from agent.agno_agent.prompts.manager import build_manager_input

    message = build_manager_input(_run_context(), "18:00 remind me to drink water")

    assert "conversation_id: conv-1" in message
    assert "timezone: Asia/Tokyo" in message
    assert "recent_chat_history:" in message
    assert "18:00 remind me to drink water" in message
