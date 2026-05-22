import asyncio
import time
from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.agent_runtime import build_capability_tool_wrappers
from agent.agno_agent.runtime.result import CapabilityResult


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


@pytest.mark.timeout(2)
def test_sync_blocking_port_does_not_starve_concurrent_task():
    class BlockingPort:
        def run(self, input_message, run_context, args):
            del input_message, run_context, args
            time.sleep(0.4)
            return CapabilityResult(
                name="url_context",
                ok=True,
                content={"items": []},
                metadata={},
            )

    wrappers = build_capability_tool_wrappers(
        ports={"url_context": BlockingPort()},
        run_context=_ctx(),
        input_message="see https://example.com",
        capability_results=[],
    )

    async def runner():
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(10):
                ticks += 1
                await asyncio.sleep(0.05)

        ticker_task = asyncio.create_task(ticker())
        await wrappers["url_context"]()
        await ticker_task
        return ticks

    assert asyncio.run(runner()) >= 6
