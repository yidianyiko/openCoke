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


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def test_assembled_prompt_excludes_protocol_and_json_schema_artifacts():
    prompt = build_chat_response_instructions(_ctx())

    forbidden = [
        "as valid JSON",
        "JSON Schema",
        "Message types include",
        "structured multi-modal",
        "RESPONSE",
        "REQUEST",
        "[reminder tool message]",
    ]
    for token in forbidden:
        assert token not in prompt, f"forbidden token found in prompt: {token!r}"


def test_prompt_keeps_user_challenges_block_in_general_form():
    prompt = build_chat_response_instructions(_ctx())

    assert "Handling User Challenges" in prompt
    assert "reminder tool result" in prompt.lower()


def test_prompt_includes_default_user_timezone():
    prompt = build_chat_response_instructions(_ctx())

    assert "UTC" in prompt
