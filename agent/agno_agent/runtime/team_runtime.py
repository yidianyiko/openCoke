from __future__ import annotations

import inspect
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.capabilities import (
    CalendarImportPort,
    ReminderIntentPort,
    TimezonePort,
    UrlContextPort,
)
from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.prompts.manager import (
    build_manager_input,
    build_manager_instructions,
)
from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.plan_parser import parse_team_plan
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.streaming import filter_user_visible_team_events


def create_manager_team(
    *,
    model: Any,
    members: list[Any],
    instructions: str | None = None,
) -> Any:
    from agno.team import Team

    return Team(
        name="CokeManagerTeam",
        model=model,
        members=members,
        instructions=instructions,
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
    current_time: datetime | None = None,
    capability_ports: dict[str, Any] | None = None,
) -> AgentRunResult:
    run_context = build_agent_run_context(
        context,
        current_time=current_time or datetime.now(UTC),
        runtime_metadata=metadata or {},
    )
    manager_input = build_manager_input(run_context, input_message_str)
    team = create_manager_team(
        model=create_llm_model(role="chat", max_tokens=8000),
        members=[],
        instructions=build_manager_instructions(run_context),
    )

    raw_events = await _collect_team_events(
        team.arun(
            manager_input,
            stream=True,
            session_state=_build_session_state(run_context),
        )
    )
    visible_text = "".join(filter_user_visible_team_events(raw_events)).strip()
    plan = parse_team_plan(visible_text)
    ports = capability_ports or _build_default_capability_ports()
    tool_results = await _execute_capability_requests(
        capability_ports=ports,
        input_message=input_message_str,
        run_context=run_context,
        requests=plan.capability_requests,
    )

    visible_messages: tuple[VisibleMessage, ...] = ()
    if plan.response_text:
        visible_messages = (
            VisibleMessage(message_type="text", content=plan.response_text),
        )

    if not visible_messages and not tool_results:
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=(),
            metrics={"event_count": len(raw_events)},
            trace={
                "runtime": "team",
                "status": "empty",
                "capability_requests": tuple(
                    request.name for request in plan.capability_requests
                ),
                "rejected_requests": plan.rejected_requests,
            },
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=RuntimeErrorDisposition(
                code="team_runtime_empty_output",
                retryable=True,
            ),
        )

    return AgentRunResult(
        visible_messages=visible_messages,
        post_analyze_input=(
            {
                "input_message": input_message_str,
                "message_source": message_source,
            }
            if visible_messages
            else None
        ),
        tool_results=tuple(tool_results),
        metrics={"event_count": len(raw_events)},
        trace={
            "runtime": "team",
            "status": "ok",
            "message_source": message_source,
            "capability_requests": tuple(
                request.name for request in plan.capability_requests
            ),
            "rejected_requests": plan.rejected_requests,
        },
        output_disposition=OutputDisposition(status="ok"),
    )


def _build_default_capability_ports() -> dict[str, Any]:
    return {
        "reminder_intent": ReminderIntentPort(),
        "url_context": UrlContextPort(),
        "timezone": TimezonePort(),
        "calendar_import": CalendarImportPort(),
    }


def _build_session_state(run_context: Any) -> dict[str, Any]:
    return {
        "user": {
            "id": run_context.user.id,
            "timezone": run_context.user.timezone,
        },
        "character": {"id": run_context.character.id},
        "conversation": {
            "id": run_context.conversation.id,
            "route_key": run_context.conversation.route_key,
        },
        "platform": run_context.platform,
    }


async def _collect_team_events(team_run: Any) -> list[Any]:
    if hasattr(team_run, "__aiter__"):
        events = []
        async for event in team_run:
            events.append(event)
        return events

    if inspect.isawaitable(team_run):
        team_run = await team_run

    if team_run is None:
        return []
    if isinstance(team_run, Iterable) and not isinstance(team_run, (str, bytes, dict)):
        return list(team_run)
    return [team_run]


async def _execute_capability_requests(
    *,
    capability_ports: dict[str, Any],
    input_message: str,
    run_context: Any,
    requests: Iterable[Any],
) -> list[CapabilityResult]:
    results: list[CapabilityResult] = []
    for request in requests:
        port = capability_ports.get(request.name)
        if port is None:
            continue
        result = port.run(input_message, run_context, request.args)
        if inspect.isawaitable(result):
            result = await result
        results.append(result)
    return results
