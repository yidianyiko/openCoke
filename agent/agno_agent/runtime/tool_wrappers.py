from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

_TOOL_NAMES = ("reminder_intent", "timezone", "calendar_import", "url_context")


def _model_facing_envelope(
    tool_name: str,
    capability_result: CapabilityResult,
) -> dict[str, Any]:
    return {
        "name": tool_name,
        "ok": capability_result.ok,
        "content": dict(capability_result.content),
        "error": capability_result.error,
    }


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


def build_capability_tool_wrappers(
    *,
    ports: Mapping[str, Any],
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> dict[str, Callable[..., Any]]:
    wrappers: dict[str, Callable[..., Any]] = {}

    for tool_name in _TOOL_NAMES:
        port = ports.get(tool_name)
        if port is None:
            continue

        async def _wrapper(
            _tool_name: str = tool_name,
            _port: Any = port,
            **kwargs: Any,
        ) -> dict[str, Any]:
            result = await _run_port(
                _port,
                input_message=input_message,
                run_context=run_context,
                args=dict(kwargs),
            )
            tool_results.append(result)
            return _model_facing_envelope(_tool_name, result)

        wrappers[tool_name] = _wrapper

    return wrappers
