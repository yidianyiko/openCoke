from __future__ import annotations

import asyncio
import inspect
import logging
import os
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
from agent.agno_agent.runtime.plan_parser import TeamPlan, parse_team_plan
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.streaming import filter_user_visible_team_events

logger = logging.getLogger(__name__)


def create_manager_team(
    *, model: Any, members: list[Any], instructions: str | None = None
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


def _default_capability_ports() -> dict[str, Any]:
    return {
        "reminder_intent": ReminderIntentPort(),
        "url_context": UrlContextPort(),
        "timezone": TimezonePort(),
        "calendar_import": CalendarImportPort(),
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _collect_team_events(events: Any) -> list[Any]:
    if inspect.isawaitable(events):
        response = await events
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return [{"event": "TeamRunContent", "content": content}]
        return [response]
    if hasattr(events, "__aiter__"):
        collected = []
        async for event in events:
            collected.append(event)
        return collected
    return list(events)


def _team_manager_timeout_seconds() -> float:
    raw_value = os.environ.get("COKE_TEAM_MANAGER_TIMEOUT_SECONDS")
    if raw_value is None:
        return 45.0
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "COKE_TEAM_MANAGER_TIMEOUT_SECONDS=%r is not a valid float; using 45.0",
            raw_value,
        )
        return 45.0
    return value if value > 0 else 45.0


def _visible_text_from_capability_results(
    tool_results: list[CapabilityResult],
) -> str | None:
    summaries = []
    for result in tool_results:
        summary = result.content.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(summary.strip())
    if not summaries:
        return None
    return "\n".join(summaries)


def _is_protocol_artifact_response(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return normalized in {"operation cancelled by user"} or "<tool_call" in normalized


async def _run_manager_plan(
    team: Any,
    manager_input: str,
    *,
    metadata: dict[str, Any] | None,
    conversation_id: str,
) -> tuple[TeamPlan, bool]:
    events = await asyncio.wait_for(
        _collect_team_events(
            team.arun(
                manager_input,
                session_state={
                    "runtime": "team",
                    "metadata": metadata or {},
                    "conversation_id": conversation_id,
                },
            )
        ),
        timeout=_team_manager_timeout_seconds(),
    )
    raw_visible_text = "".join(filter_user_visible_team_events(events))
    plan = parse_team_plan(raw_visible_text)
    return plan, _is_protocol_artifact_response(plan.response_text)


async def run_team_runtime(
    *,
    context: dict[str, Any],
    input_message_str: str,
    message_source: str,
    metadata: dict[str, Any] | None,
    current_time: datetime | None = None,
    capability_ports: dict[str, Any] | None = None,
) -> AgentRunResult:
    occurred_at = current_time or datetime.now(UTC)
    run_context = build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    team = create_manager_team(
        model=create_llm_model(role="chat", max_tokens=8000),
        members=[],
        instructions=build_manager_instructions(run_context),
    )
    manager_input = build_manager_input(run_context, input_message_str)
    manager_timed_out = False
    manager_protocol_retried = False
    try:
        plan, protocol_artifact = await _run_manager_plan(
            team,
            manager_input,
            metadata=metadata,
            conversation_id=run_context.conversation.id,
        )
        if protocol_artifact and not plan.capability_requests:
            manager_protocol_retried = True
            plan, _ = await _run_manager_plan(
                team,
                "\n".join(
                    [
                        manager_input,
                        "",
                        "Previous manager output violated the RESPONSE/REQUEST contract.",
                        "Do not emit XML, <tool_call>, <invoke>, function-call JSON, or provider tool syntax.",
                        "Return only RESPONSE and REQUEST lines now.",
                    ]
                ),
                metadata=metadata,
                conversation_id=run_context.conversation.id,
            )
    except TimeoutError:
        manager_timed_out = True
        logger.error(
            "Team manager timed out: timeout=%.1fs",
            _team_manager_timeout_seconds(),
        )
        plan = TeamPlan(response_text="", capability_requests=())
    ports = capability_ports or _default_capability_ports()

    tool_results = []
    executed_request_names = []
    seen_request_names = set()
    for request in plan.capability_requests:
        if request.name in seen_request_names:
            continue
        seen_request_names.add(request.name)
        port = ports.get(request.name)
        if port is None:
            continue
        result = await _maybe_await(
            port.run(input_message_str, run_context, request.args)
        )
        tool_results.append(result)
        executed_request_names.append(request.name)

    visible_text = _visible_text_from_capability_results(tool_results) or (
        plan.response_text
    )
    visible_messages = (
        (VisibleMessage(message_type="text", content=visible_text),)
        if visible_text
        else ()
    )
    if visible_messages:
        return AgentRunResult(
            visible_messages=visible_messages,
            post_analyze_input={
                "input_message": input_message_str,
                "message_source": message_source,
            }
            if visible_messages
            else None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={
                "runtime": "team",
                "capability_requests": tuple(executed_request_names),
                "rejected_requests": plan.rejected_requests,
                "manager_timeout": manager_timed_out,
                "manager_protocol_retried": manager_protocol_retried,
            },
            output_disposition=OutputDisposition(status="ok"),
        )

    return AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=tuple(tool_results),
        metrics={"capability_result_count": len(tool_results)},
        trace={
            "runtime": "team",
            "status": "empty_output",
            "capability_requests": tuple(executed_request_names),
            "rejected_requests": plan.rejected_requests,
            "manager_timeout": manager_timed_out,
            "manager_protocol_retried": manager_protocol_retried,
        },
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="team_runtime_empty_output",
            retryable=True,
        ),
    )
