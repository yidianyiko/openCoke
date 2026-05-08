from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.errors import UnknownToolError
from agent.agno_agent.runtime.result import CapabilityResult

_TOOL_NAMES = ("reminder_intent", "timezone", "calendar_import", "url_context")


def _model_facing_envelope(
    tool_name: str,
    capability_result: CapabilityResult,
) -> dict[str, Any]:
    return {
        "name": tool_name,
        "ok": capability_result.ok,
        "content": _jsonable(capability_result.content),
        "error": capability_result.error,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode(errors="replace")
    if isinstance(value, Sequence):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in value]
    return str(value)


async def _run_port(
    port: Any,
    *,
    input_message: str,
    run_context: AgentRunContext,
    args: dict[str, Any],
) -> CapabilityResult:
    import asyncio

    run = port.run
    if inspect.iscoroutinefunction(run):
        return await run(input_message, run_context, args)
    return await asyncio.to_thread(run, input_message, run_context, args)


def _build_wrapper(
    *,
    tool_name: str,
    port: Any,
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> Callable[..., Any]:
    async def _call(args: dict[str, Any]) -> dict[str, Any]:
        result = await _run_port(
            port,
            input_message=input_message,
            run_context=run_context,
            args=args,
        )
        tool_results.append(result)
        return _model_facing_envelope(tool_name, result)

    if tool_name == "reminder_intent":

        async def reminder_intent() -> dict[str, Any]:
            """Detect and execute reminder create, update, cancel, complete, or list intent."""
            return await _call({})

        return reminder_intent

    if tool_name == "timezone":

        async def timezone(
            action: str,
            timezone: str = "",
            decision: str = "",
        ) -> dict[str, Any]:
            """Set, propose, or confirm a user timezone."""
            return await _call(
                {
                    "action": action,
                    "timezone": timezone,
                    "decision": decision,
                }
            )

        return timezone

    if tool_name == "calendar_import":

        async def calendar_import(
            handoff_payload: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Create a Google Calendar import handoff link."""
            return await _call({"handoff_payload": handoff_payload})

        return calendar_import

    if tool_name == "url_context":

        async def url_context() -> dict[str, Any]:
            """Read URLs from the current user message and return context."""
            return await _call({})

        return url_context

    raise ValueError(f"Unsupported capability tool: {tool_name}")


def _build_missing_wrapper(tool_name: str) -> Callable[..., Any]:
    if tool_name == "reminder_intent":

        async def reminder_intent() -> dict[str, Any]:
            raise UnknownToolError(tool_name)

        return reminder_intent

    if tool_name == "timezone":

        async def timezone(
            action: str,
            timezone: str = "",
            decision: str = "",
        ) -> dict[str, Any]:
            del action, timezone, decision
            raise UnknownToolError(tool_name)

        return timezone

    if tool_name == "calendar_import":

        async def calendar_import(
            handoff_payload: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del handoff_payload
            raise UnknownToolError(tool_name)

        return calendar_import

    if tool_name == "url_context":

        async def url_context() -> dict[str, Any]:
            raise UnknownToolError(tool_name)

        return url_context

    raise ValueError(f"Unsupported capability tool: {tool_name}")


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
            wrappers[tool_name] = _build_missing_wrapper(tool_name)
            continue

        wrappers[tool_name] = _build_wrapper(
            tool_name=tool_name,
            port=port,
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )

    return wrappers
