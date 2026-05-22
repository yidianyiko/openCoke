from __future__ import annotations

import asyncio
import inspect
from typing import Any

from agno.agent import Agent
from agno.tools import tool

from agent.agno_agent.capabilities import ReminderIntentPort, SchedulingCapabilityPort
from agent.agno_agent.capabilities.scheduling import SCHEDULING_TOOL_NAMES
from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.domain_results import DomainExecutionResult
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.scheduling_types import (
    SchedulingBookableWindowPreview,
    _compact_scheduling_args,
)

_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE = (
    "You are the scheduling execution worker. The intent is: {intent}. "
    "Call exactly one scheduling tool that matches the intent. "
    "Respect scheduling safety: separate A-side link management from B-side "
    "appointment actions, do not guess ambiguous roles or target accounts, "
    "do not expose raw user-link codes when status or URL is enough, and do "
    "not perform irreversible scheduling changes unless the intent confirms "
    "the exact change. Pending appointment holds do not expire automatically. "
    "Output only the tool call - do not generate user-visible text."
)


class _SchedulingExecutionGuard:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._claimed = False

    async def claim(self) -> bool:
        async with self._lock:
            if self._claimed:
                return False
            self._claimed = True
            return True


async def _run_port(
    port: Any,
    *,
    input_message: str,
    run_context: AgentRunContext,
    args: dict[str, Any],
) -> CapabilityResult:
    run = port.run
    if inspect.iscoroutinefunction(run):
        return await run(input_message, run_context, args)
    return await asyncio.to_thread(run, input_message, run_context, args)


def _capability_envelope(result: CapabilityResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "ok": result.ok,
        "content": dict(result.content),
        "visible_summary": result.visible_summary,
        "synthesis_context": result.synthesis_context,
        "error": result.error,
    }


async def run_reminder_domain(
    *,
    input_message: str,
    run_context: AgentRunContext,
    domain_results: list[DomainExecutionResult],
) -> dict[str, Any]:
    """Call ReminderIntentPort directly and append a typed domain result."""
    port = ReminderIntentPort()
    result = await port.run(input_message, run_context, {})
    domain_results.append(result)
    return result.to_dict()


def _make_scheduling_tool_fn(
    tool_name: str,
    port: Any,
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
    domain_results: list[CapabilityResult],
    execution_guard: _SchedulingExecutionGuard | None = None,
) -> Any:
    async def scheduling_tool(
        target_account_id: str | None = None,
        consumer_account_id: str | None = None,
        other_account_id: str | None = None,
        request_id: str | None = None,
        appointment_or_request_id: str | None = None,
        window_instance_id: str | None = None,
        bookable_window_id: str | None = None,
        instance_start: str | None = None,
        instance_end: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        timezone: str | None = None,
        viewer_timezone: str | None = None,
        instruction: str | None = None,
        preview: SchedulingBookableWindowPreview | None = None,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Use only for the scheduling action specified in the intent."""
        if execution_guard is not None and not await execution_guard.claim():
            return {
                "name": tool_name,
                "ok": False,
                "content": {},
                "visible_summary": None,
                "synthesis_context": None,
                "error": "duplicate_scheduling_tool_call",
            }

        result = await _run_port(
            port,
            input_message=input_message,
            run_context=run_context,
            args=_compact_scheduling_args(
                {
                    "target_account_id": target_account_id,
                    "consumer_account_id": consumer_account_id,
                    "other_account_id": other_account_id,
                    "request_id": request_id,
                    "appointment_or_request_id": appointment_or_request_id,
                    "window_instance_id": window_instance_id,
                    "bookable_window_id": bookable_window_id,
                    "instance_start": instance_start,
                    "instance_end": instance_end,
                    "date_from": date_from,
                    "date_to": date_to,
                    "timezone": timezone,
                    "viewer_timezone": viewer_timezone,
                    "instruction": instruction,
                    "preview": preview,
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                }
            ),
        )
        tool_results.append(result)
        domain_results.append(result)
        return _capability_envelope(result)

    return scheduling_tool


async def run_scheduling_domain(
    *,
    input_message: str,
    intent: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
) -> dict[str, Any]:
    """Spawn SchedulingExecutionAgent; append results to shared tool_results."""
    domain_results: list[CapabilityResult] = []
    execution_guard = _SchedulingExecutionGuard()
    ports = {
        name: SchedulingCapabilityPort(tool_name=name) for name in SCHEDULING_TOOL_NAMES
    }
    tools = [
        tool(name=name)(
            _make_scheduling_tool_fn(
                name,
                port,
                input_message=input_message,
                run_context=run_context,
                tool_results=tool_results,
                domain_results=domain_results,
                execution_guard=execution_guard,
            )
        )
        for name, port in ports.items()
    ]
    agent = Agent(
        id="coke-scheduling-agent",
        name="CokeSchedulingAgent",
        model=create_llm_model(role="chat_response", max_tokens=1000),
        instructions=_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE.format(intent=intent),
        tools=tools,
        db=None,
        add_history_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )
    await agent.arun(input=input_message)
    if not domain_results:
        return {
            "ok": False,
            "domain": "scheduling",
            "visible_summary": None,
            "synthesis_context": None,
            "error": "no_tool_called",
        }

    last = domain_results[-1]
    return {
        "ok": last.ok,
        "domain": "scheduling",
        "visible_summary": last.visible_summary,
        "synthesis_context": last.synthesis_context,
        "content": dict(last.content),
        "error": last.error,
    }
