from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Mapping, Sequence
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
from agent.agno_agent.runtime.plan_parser import (
    CapabilityRequest,
    TeamPlan,
    parse_team_plan,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.streaming import filter_user_visible_team_events

logger = logging.getLogger(__name__)
_DEFAULT_TEAM_MANAGER_TIMEOUT_SECONDS = 30.0
_DEFAULT_TEAM_MANAGER_RETRY_TIMEOUT_SECONDS = 10.0
_TEAM_MANAGER_MODEL_ROLE = "reminder_detect"
_TEAM_MANAGER_MAX_TOKENS = 2000


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
    return _float_env(
        "COKE_TEAM_MANAGER_TIMEOUT_SECONDS",
        _DEFAULT_TEAM_MANAGER_TIMEOUT_SECONDS,
    )


def _team_manager_retry_timeout_seconds() -> float:
    return _float_env(
        "COKE_TEAM_MANAGER_RETRY_TIMEOUT_SECONDS",
        _DEFAULT_TEAM_MANAGER_RETRY_TIMEOUT_SECONDS,
    )


def _float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "%s=%r is not a valid float; using %.1f",
            name,
            raw_value,
            default,
        )
        return default
    return value if value > 0 else default


def _visible_text_from_capability_results(
    tool_results: list[CapabilityResult],
) -> str | None:
    summaries = []
    for result in tool_results:
        summary = result.content.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(summary.strip())
            continue
        message = result.content.get("message")
        if isinstance(message, str) and message.strip():
            summaries.append(message.strip())
    if not summaries:
        return None
    return "\n".join(summaries)


def _requires_response_synthesis(tool_results: list[CapabilityResult]) -> bool:
    return any(
        result.metadata.get("requires_response_synthesis") is True
        for result in tool_results
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return value


def _format_capability_results_for_manager(
    tool_results: list[CapabilityResult],
) -> str:
    payload = [
        {
            "name": result.name,
            "ok": result.ok,
            "content": _jsonable(result.content),
            "error": result.error,
            "metadata": _jsonable(result.metadata),
        }
        for result in tool_results
    ]
    return json.dumps(payload, ensure_ascii=False, default=str)


async def _run_manager_response_synthesis(
    team: Any,
    manager_input: str,
    *,
    metadata: dict[str, Any] | None,
    conversation_id: str,
    tool_results: list[CapabilityResult],
) -> TeamPlan:
    synthesis_input = "\n".join(
        [
            manager_input,
            "",
            "Capability results:",
            _format_capability_results_for_manager(tool_results),
            "",
            "The capability requests above have already been executed.",
            "Use the capability results to answer the user now.",
            "Return final user-visible RESPONSE text only.",
            "Do not request capabilities again unless the result shows a missing required input.",
        ]
    )
    try:
        plan, protocol_artifact = await _run_manager_plan(
            team,
            synthesis_input,
            metadata=metadata,
            conversation_id=conversation_id,
            timeout_seconds=_team_manager_retry_timeout_seconds(),
        )
    except TimeoutError:
        logger.error(
            "Team manager response synthesis timed out: timeout=%.1fs",
            _team_manager_retry_timeout_seconds(),
        )
        return TeamPlan(response_text="", capability_requests=())
    if protocol_artifact:
        logger.warning("Team manager response synthesis returned protocol artifact")
        return TeamPlan(response_text="", capability_requests=())
    return plan


def _is_protocol_artifact_response(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    artifact_markers = (
        "<tool_call",
        ":tool_call",
        "<invoke",
        "</invoke>",
        "<parameter",
        "</parameter>",
        "[tool_call]",
        "[/tool_call]",
        "{tool =>",
        "--action",
    )
    return normalized in {"operation cancelled by user"} or any(
        marker in normalized for marker in artifact_markers
    )


async def _run_manager_plan(
    team: Any,
    manager_input: str,
    *,
    metadata: dict[str, Any] | None,
    conversation_id: str,
    timeout_seconds: float | None = None,
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
        timeout=timeout_seconds or _team_manager_timeout_seconds(),
    )
    raw_visible_text = "".join(filter_user_visible_team_events(events))
    plan = parse_team_plan(raw_visible_text)
    if not raw_visible_text.strip():
        event_names = [
            (
                event.get("event")
                if isinstance(event, dict)
                else getattr(event, "event", None)
            )
            for event in events
        ]
        logger.warning(
            "Team manager produced no visible content: events=%s", event_names
        )
    elif not plan.response_text and not plan.capability_requests:
        logger.warning(
            "Team manager produced empty parsed plan: raw=%r",
            raw_visible_text[:500],
        )
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
        model=create_llm_model(
            role=_TEAM_MANAGER_MODEL_ROLE,
            max_tokens=_TEAM_MANAGER_MAX_TOKENS,
        ),
        members=[],
        instructions=build_manager_instructions(run_context),
    )
    manager_input = build_manager_input(run_context, input_message_str)
    manager_timed_out = False
    manager_protocol_retried = False
    manager_empty_retried = False
    manager_recovery_capability = False
    try:
        plan, protocol_artifact = await _run_manager_plan(
            team,
            manager_input,
            metadata=metadata,
            conversation_id=run_context.conversation.id,
        )
        if protocol_artifact and not plan.capability_requests:
            manager_protocol_retried = True
            plan, protocol_artifact = await _run_manager_plan(
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
                timeout_seconds=_team_manager_retry_timeout_seconds(),
            )
            if protocol_artifact and not plan.capability_requests:
                logger.error("Team manager returned protocol artifact after retry")
                plan = TeamPlan(response_text="", capability_requests=())
        if not plan.response_text and not plan.capability_requests:
            manager_empty_retried = True
            plan, protocol_artifact = await _run_manager_plan(
                team,
                "\n".join(
                    [
                        manager_input,
                        "",
                        "Previous manager output was empty.",
                        "Return a valid RESPONSE block and any needed REQUEST lines now.",
                        "If the user is asking for reminder CRUD or reminder listing, include REQUEST reminder_intent {}.",
                        "Do not emit XML, <tool_call>, <invoke>, function-call JSON, or provider tool syntax.",
                    ]
                ),
                metadata=metadata,
                conversation_id=run_context.conversation.id,
                timeout_seconds=_team_manager_retry_timeout_seconds(),
            )
            if protocol_artifact and not plan.capability_requests:
                logger.error(
                    "Team manager returned protocol artifact after empty retry"
                )
                plan = TeamPlan(response_text="", capability_requests=())
    except TimeoutError:
        manager_timed_out = True
        logger.error(
            "Team manager timed out: timeout=%.1fs",
            _team_manager_timeout_seconds(),
        )
        plan = TeamPlan(response_text="", capability_requests=())
    if (
        manager_protocol_retried
        and not manager_timed_out
        and not plan.response_text
        and not plan.capability_requests
    ):
        manager_recovery_capability = True
        plan = TeamPlan(
            response_text="",
            capability_requests=(CapabilityRequest(name="reminder_intent", args={}),),
        )
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

    response_synthesized_after_capabilities = False
    synthesized_plan = None
    if tool_results and _requires_response_synthesis(tool_results):
        synthesized_plan = await _run_manager_response_synthesis(
            team,
            manager_input,
            metadata=metadata,
            conversation_id=run_context.conversation.id,
            tool_results=tool_results,
        )
        if synthesized_plan.response_text:
            response_synthesized_after_capabilities = True

    visible_text = (
        synthesized_plan.response_text
        if synthesized_plan is not None and synthesized_plan.response_text
        else _visible_text_from_capability_results(tool_results) or plan.response_text
    )
    visible_messages = (
        (VisibleMessage(message_type="text", content=visible_text),)
        if visible_text
        else ()
    )
    if visible_messages:
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
            metrics={"capability_result_count": len(tool_results)},
            trace={
                "runtime": "team",
                "capability_requests": tuple(executed_request_names),
                "rejected_requests": plan.rejected_requests,
                "manager_timeout": manager_timed_out,
                "manager_protocol_retried": manager_protocol_retried,
                "manager_empty_retried": manager_empty_retried,
                "manager_recovery_capability": manager_recovery_capability,
                "response_synthesized_after_capabilities": response_synthesized_after_capabilities,
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
            "manager_empty_retried": manager_empty_retried,
            "manager_recovery_capability": manager_recovery_capability,
            "response_synthesized_after_capabilities": response_synthesized_after_capabilities,
        },
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="team_runtime_empty_output",
            retryable=True,
        ),
    )
