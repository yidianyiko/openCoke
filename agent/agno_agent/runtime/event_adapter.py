from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import AgentRunResult
from agent.agno_agent.runtime.team_runtime import run_team_runtime


async def run_agent_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    message_source: str,
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
) -> AgentRunResult:
    occurred_at = current_time or agent_input.occurred_at or datetime.now(UTC)
    build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    return await run_team_runtime(
        context=context,
        input_message_str=agent_input.text or "",
        message_source=message_source,
        metadata=metadata or {},
        current_time=occurred_at,
    )


async def run_deferred_action_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
):
    from agent.agno_agent.adapters import map_agent_result_to_deferred_status

    result = await run_agent_runtime_event(
        agent_input=agent_input,
        context=context,
        message_source="deferred_action",
        metadata=metadata,
        current_time=current_time,
    )
    return map_agent_result_to_deferred_status(result)
