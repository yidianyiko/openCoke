from datetime import UTC, datetime

from agent.agno_agent.runtime.chat_response_instructions import (
    build_chat_response_instructions,
)
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def test_chat_response_instructions_include_domain_execution_contract():
    instructions = build_chat_response_instructions(
        _run_context(),
        AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="remind me",
            payload=UserTurnPayload(current_message_ids=["msg-1"]),
            occurred_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        ),
    )

    assert "Domain execution result contract:" in instructions
    assert (
        "operations, facts, missing_fields, and safety_boundary as trusted execution facts"
        in instructions
    )
    assert 'Do not claim a write occurred unless outcome == "executed"' in instructions
    assert "Do not omit required questions" in instructions
    assert (
        "Do not invent ids, dates, times, recurrence, appointment state, reminder state, "
        "or confirmation state"
    ) in instructions
    assert (
        "Do not rewrite or replace the user's final answer with a deterministic domain summary"
        not in instructions
    )
