import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers


def _run_context() -> AgentRunContext:
    from datetime import UTC, datetime

    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_reminder_envelope_uses_tool_function_name_not_capability_name():
    captured: list[CapabilityResult] = []

    class StubReminderPort:
        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "已为你设好提醒"},
                metadata={
                    "durable_write": True,
                    "requires_response_synthesis": True,
                },
            )

    wrappers = build_capability_tool_wrappers(
        ports={"reminder_intent": StubReminderPort()},
        run_context=_run_context(),
        input_message="提醒我喝水",
        tool_results=captured,
    )

    envelope = await wrappers["reminder_intent"]()

    assert envelope["name"] == "reminder_intent"
    assert envelope["ok"] is True
    assert envelope["content"] == {"visible_summary": "已为你设好提醒"}
    assert envelope["error"] is None
    assert "metadata" not in envelope
    assert "durable_write" not in envelope
    assert "requires_response_synthesis" not in envelope
    assert captured[0].name == "reminder"
    assert captured[0].durable_write is True
    assert captured[0].requires_response_synthesis is True
