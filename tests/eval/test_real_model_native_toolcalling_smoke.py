"""Real-model smoke for the single-Agent runtime.

Run only with staging credentials:
    AGENT_RUNTIME_REAL_MODEL_SMOKE=1 .venv/bin/python -m pytest tests/eval/test_real_model_native_toolcalling_smoke.py -v -s

This is gated by the env flag because it issues real LLM calls.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_RUNTIME_REAL_MODEL_SMOKE") != "1",
    reason="real-model smoke is opt-in via AGENT_RUNTIME_REAL_MODEL_SMOKE=1",
)


def _ctx(timezone: str = "Asia/Tokyo") -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="staging-u", nickname="Smoke", timezone=timezone),
        character=TrustedCharacterContext(id="staging-c", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="staging-conv", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="staging-u", cid="staging-c"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
        runtime_metadata={"message_source": "user"},
    )


def _input(text: str) -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="staging-conv",
        text=text,
        payload=UserTurnPayload(current_message_ids=["staging-msg"]),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_reminder_create_flow_real_model():
    result = await run_agent_runtime(
        agent_input=_input("明天 8 点提醒我喝水"),
        run_context=_ctx(),
    )

    assert result.output_disposition.status == "ok"
    assert any(
        domain_result.domain == "reminder"
        and any(
            operation.ok and operation.effect == "write"
            for operation in domain_result.operations
        )
        for domain_result in result.domain_results
    )


@pytest.mark.asyncio
async def test_url_context_synthesis_real_model():
    result = await run_agent_runtime(
        agent_input=_input("简单介绍下 https://example.com 这个页面"),
        run_context=_ctx(),
    )

    assert result.output_disposition.status == "ok"
    assert any(result.name == "url_context" for result in result.capability_results)
    visible = "".join(message.content for message in result.visible_messages)
    for marker in ("RESPONSE", "REQUEST", "<tool_call", "<invoke", "tool_use"):
        assert marker not in visible


@pytest.mark.asyncio
async def test_timezone_change_real_model():
    result = await run_agent_runtime(
        agent_input=_input("帮我把时区改成东京"),
        run_context=_ctx(timezone="UTC"),
    )

    assert result.output_disposition.status == "ok"
    assert any(result.name == "timezone" for result in result.capability_results)
