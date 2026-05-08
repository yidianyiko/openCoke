from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import AgentRunResult


async def run_agent_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    message_source: str,
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
) -> AgentRunResult:
    occurred_at = current_time or agent_input.occurred_at or datetime.now(UTC)
    run_context = build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    return await run_agent_runtime(agent_input=agent_input, run_context=run_context)
