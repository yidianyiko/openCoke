from __future__ import annotations

from typing import Any

from agno.team import Team

from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    RuntimeErrorDisposition,
)


def create_manager_team(*, model: Any, members: list[Any]) -> Team:
    return Team(
        name="CokeManagerTeam",
        model=model,
        members=members,
        tools=[],
        db=None,
        add_session_state_to_context=False,
        enable_agentic_state=False,
        cache_session=False,
    )


async def run_team_runtime(
    *,
    context: dict[str, Any],
    input_message_str: str,
    message_source: str,
    metadata: dict[str, Any] | None,
) -> AgentRunResult:
    return AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={"runtime": "team", "status": "empty_skeleton"},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="team_runtime_empty_skeleton",
            retryable=False,
        ),
    )
