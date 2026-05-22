from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from agent.agno_agent.capabilities import ReminderIntentPort
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

logger = logging.getLogger(__name__)


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
