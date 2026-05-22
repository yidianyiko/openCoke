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
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.scheduling_types import _compact_scheduling_args

_SCHEDULING_SYSTEM_PROMPT = (
    "You are the friend-link and shared-reminder execution worker. "
    "Call exactly one scheduling tool that matches the intent. "
    "Do not create shared reminder state unless the named person resolves to "
    "one active friend. Ask for clarification when the name is ambiguous. "
    "Ordinary personal reminders are not scheduling-domain work. "
    "Do not treat an iLink QR as a public user-link QR."
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
    tool_results: list[CapabilityResult],
) -> dict[str, Any]:
    """Call ReminderIntentPort directly; append result to shared tool_results.

    No intermediate Agno Agent. ReminderIntentPort handles all outcomes: CRUD,
    clarification, and no-intent.
    """
    port = ReminderIntentPort()
    result = await _run_port(
        port,
        input_message=input_message,
        run_context=run_context,
        args={},
    )
    tool_results.append(result)
    return _capability_envelope(result)


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
        invitee_account_id: str | None = None,
        title: str | None = None,
        fire_at: str | None = None,
        timezone: str | None = None,
        request_id: str | None = None,
        friendship_id: str | None = None,
        blocked_account_id: str | None = None,
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
                    "invitee_account_id": invitee_account_id,
                    "title": title,
                    "fire_at": fire_at,
                    "timezone": timezone,
                    "request_id": request_id,
                    "friendship_id": friendship_id,
                    "blocked_account_id": blocked_account_id,
                    "idempotency_key": idempotency_key,
                }
            ),
        )
        tool_results.append(result)
        domain_results.append(result)
        return _capability_envelope(result)

    return scheduling_tool


def _scheduling_agent_input(input_message: str, intent: str) -> str:
    return (
        f"Resolved scheduling intent: {intent}\n"
        f"User message: {input_message}"
    )


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
        instructions=_SCHEDULING_SYSTEM_PROMPT,
        tools=tools,
        db=None,
        add_history_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )
    await agent.arun(input=_scheduling_agent_input(input_message, intent))
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
