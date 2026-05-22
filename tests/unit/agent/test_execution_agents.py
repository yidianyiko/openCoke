from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.execution_agents import run_reminder_domain
from agent.agno_agent.runtime.result import CapabilityResult


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        runtime_metadata={},
    )


class _FakePort:
    def __init__(self, result: CapabilityResult) -> None:
        self._result = result

    async def run(self, input_message, run_context, args):
        return self._result


@pytest.mark.asyncio
async def test_run_reminder_domain_appends_exactly_one_result_to_tool_results():
    fake_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已为你设好提醒"},
        metadata={"durable_write": True},
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert len(tool_results) == 1
    assert tool_results[0] is fake_result


@pytest.mark.asyncio
async def test_run_reminder_domain_returns_full_capability_envelope():
    fake_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已为你设好提醒", "synthesis_context": "ctx"},
        metadata={"durable_write": True},
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert envelope["ok"] is True
    assert envelope["visible_summary"] == "已为你设好提醒"
    assert envelope["synthesis_context"] == "ctx"
    assert "content" in envelope
    assert envelope["error"] is None


@pytest.mark.asyncio
async def test_run_reminder_domain_forwards_failed_port_result():
    fake_result = CapabilityResult(
        name="reminder",
        ok=False,
        content={},
        error="reminder_service_unavailable",
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="set a reminder",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert envelope["ok"] is False
    assert envelope["error"] == "reminder_service_unavailable"
    assert len(tool_results) == 1
