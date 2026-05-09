from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Sequence
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.errors import UnknownToolError
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    DeferredActionPayload,
    ReminderFirePayload,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)

logger = logging.getLogger(__name__)

_SUPPORTED_INPUT_TYPES = {"user.turn", "reminder.fired", "deferred_action.fire"}
_DEFAULT_AGENT_RUNTIME_TIMEOUT_SECONDS = 160.0
_UNCONFIRMED_DURABLE_WRITE_PATTERNS = (
    re.compile(
        r"(\u6211\u4f1a|\u5230\u65f6\u5019|\u5df2\u7ecf|\u5df2|\u5e2e\u4f60)"
        r".{0,24}(\u63d0\u9192\u4f60|\u901a\u77e5\u4f60)"
    ),
    re.compile(r"(\u63d0\u9192\u4f60|\u901a\u77e5\u4f60)"),
    re.compile(r"(\u6211\u6765|\u4f1a|\u5230\u65f6\u5019).{0,16}" r"(\u53eb\u4f60)"),
    re.compile(
        r"(\u5df2\u7ecf|\u5df2|\u5e2e\u4f60).{0,16}"
        r"(\u8bbe\u7f6e|\u8bbe\u597d).{0,16}"
        r"(\u63d0\u9192|\u901a\u77e5)"
    ),
    re.compile(
        r"\b(i(?:'ll| will|'ve| have)|we(?:'ll| will)).{0,40}"
        r"\b(remind|notify|set (?:up )?(?:the )?reminder)",
        re.IGNORECASE,
    ),
)


def _float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "%s=%r is not a valid float; using %.1f", name, raw_value, default
        )
        return default
    return value if value > 0 else default


def _agent_runtime_timeout_seconds() -> float:
    return _float_env(
        "COKE_AGENT_RUNTIME_TIMEOUT_SECONDS",
        _DEFAULT_AGENT_RUNTIME_TIMEOUT_SECONDS,
    )


def _default_capability_ports() -> dict[str, Any]:
    from agent.agno_agent.capabilities import (
        CalendarImportPort,
        ReminderIntentPort,
        TimezonePort,
        UrlContextPort,
    )

    return {
        "reminder_intent": ReminderIntentPort(),
        "timezone": TimezonePort(),
        "calendar_import": CalendarImportPort(),
        "url_context": UrlContextPort(),
    }


def _create_agent(
    *,
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> Any:
    from agno.agent import Agent
    from agno.tools import tool

    from agent.agno_agent.model_factory import create_llm_model
    from agent.agno_agent.runtime.chat_response_instructions import (
        build_chat_response_instructions,
    )
    from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers

    wrappers = build_capability_tool_wrappers(
        ports=_default_capability_ports(),
        run_context=run_context,
        input_message=input_message,
        tool_results=tool_results,
    )
    tools = [
        tool(name=name, stop_after_tool_call=name == "reminder_intent")(fn)
        for name, fn in wrappers.items()
    ]
    return Agent(
        id="coke-single-agent",
        name="CokeSingleAgent",
        model=create_llm_model(role="chat_response", max_tokens=2000),
        instructions=build_chat_response_instructions(run_context),
        tools=tools,
        tool_call_limit=4,
        markdown=False,
    )


def _message_value(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _string_content(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _extract_final_text(run_output: Any) -> str:
    messages = getattr(run_output, "messages", None)
    if not messages:
        return _string_content(getattr(run_output, "content", None))

    last_tool_index = -1
    for index, message in enumerate(messages):
        role = str(_message_value(message, "role") or "").lower()
        message_type = str(_message_value(message, "type") or "").lower()
        if role in {"tool", "tool_result"} or message_type in {"tool", "tool_result"}:
            last_tool_index = index

    final_text = ""
    for message in messages[last_tool_index + 1 :]:
        role = str(_message_value(message, "role") or "").lower()
        if role != "assistant":
            continue
        content = _string_content(_message_value(message, "content"))
        if content:
            final_text = content
    return final_text


def _resolve_visible_text(
    final_text: str,
    tool_results: Sequence[CapabilityResult],
) -> str:
    if tool_results and any(
        result.requires_response_synthesis for result in tool_results
    ):
        if final_text:
            return final_text

    summaries = [
        summary for result in tool_results if (summary := result.visible_summary)
    ]
    if summaries:
        return "\n".join(summaries)

    if not tool_results:
        return final_text

    return ""


def _check_durable_write_contract(
    tool_results: Sequence[CapabilityResult],
) -> RuntimeErrorDisposition | None:
    for result in tool_results:
        if result.ok and result.durable_write and not result.visible_summary:
            return RuntimeErrorDisposition(
                code="durable_write_missing_visible_summary",
                retryable=False,
                metadata={"capability": result.name},
            )
    return None


def _input_message(agent_input: AgentInput) -> str:
    if agent_input.input_type == "user.turn":
        return agent_input.text or ""
    if agent_input.input_type == "reminder.fired":
        return agent_input.text or agent_input.payload.title
    if agent_input.input_type == "deferred_action.fire":
        return agent_input.text or agent_input.payload.prompt
    raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")


def _message_source(agent_input: AgentInput, run_context: AgentRunContext) -> str:
    value = run_context.runtime_metadata.get("message_source")
    if isinstance(value, str) and value:
        return value
    return agent_input.input_type


def _model_input(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
) -> str:
    lines = [
        "Trusted runtime context:",
        f"input_type: {agent_input.input_type}",
        f"message_source: {_message_source(agent_input, run_context)}",
        f"current_time: {run_context.current_time.isoformat()}",
        f"user: {run_context.user.nickname or 'User'} ({run_context.user.id})",
        (
            f"character: {run_context.character.nickname or 'Coke'} "
            f"({run_context.character.id})"
        ),
        f"conversation_id: {run_context.conversation.id}",
        f"platform: {run_context.platform}",
    ]
    if run_context.conversation.route_key:
        lines.append(f"route_key: {run_context.conversation.route_key}")

    if isinstance(agent_input.payload, ReminderFirePayload):
        lines.extend(
            [
                (
                    "event_contract: system reminder delivery; deliver the existing "
                    "reminder to the user; do not create, update, cancel, or list "
                    "reminders for this event."
                ),
                f"reminder_id: {agent_input.payload.reminder_id}",
                f"reminder_title: {agent_input.payload.title}",
                f"scheduled_for: {agent_input.payload.scheduled_for.isoformat()}",
                f"fire_id: {agent_input.payload.fire_id}",
            ]
        )
    elif isinstance(agent_input.payload, DeferredActionPayload):
        lines.extend(
            [
                f"deferred_action_id: {agent_input.payload.action_id}",
                f"deferred_action_kind: {agent_input.payload.kind}",
                f"scheduled_for: {agent_input.payload.scheduled_for.isoformat()}",
                f"revision: {agent_input.payload.revision}",
            ]
        )

    if run_context.recent_chat_history:
        lines.extend(["recent_chat_history:", run_context.recent_chat_history])

    return "\n".join(lines) + f"\n\nuser_message:\n{input_message}"


def _check_unconfirmed_durable_write_promise(
    *,
    agent_input: AgentInput,
    final_text: str,
    tool_results: Sequence[CapabilityResult],
) -> RuntimeErrorDisposition | None:
    if agent_input.input_type != "user.turn" or not final_text:
        return None
    if any(result.ok and result.durable_write for result in tool_results):
        return None
    if "?" in final_text or "\uff1f" in final_text or "\u5417" in final_text:
        return None
    if not any(
        pattern.search(final_text) for pattern in _UNCONFIRMED_DURABLE_WRITE_PATTERNS
    ):
        return None
    return RuntimeErrorDisposition(
        code="unconfirmed_durable_write_promise",
        retryable=False,
        metadata={"input_type": agent_input.input_type},
    )


def _exception_result(
    tool_results: Sequence[CapabilityResult] = (),
) -> AgentRunResult:
    logger.exception("Agent runtime failed closed")
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=tuple(tool_results),
        metrics={"capability_result_count": len(tool_results)},
        trace={"runtime": "agent", "status": "exception"},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="agent_runtime_exception",
            retryable=True,
        ),
    )


def _unknown_tool_result(
    exc: UnknownToolError,
    tool_results: Sequence[CapabilityResult] = (),
) -> AgentRunResult:
    logger.error("Agent runtime received unknown tool name: %s", exc)
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=tuple(tool_results),
        metrics={"capability_result_count": len(tool_results)},
        trace={"runtime": "agent", "status": "unknown_tool", "unknown_tool": str(exc)},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="agent_runtime_unknown_tool",
            retryable=False,
        ),
    )


def _timeout_result(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    timeout_seconds: float,
    tool_results: Sequence[CapabilityResult] = (),
) -> AgentRunResult:
    logger.error("Agent runtime timed out: timeout=%.1fs", timeout_seconds)
    captured_tool_results = tuple(tool_results)
    durable_write_error = _check_durable_write_contract(captured_tool_results)
    timeout_error = RuntimeErrorDisposition(
        code="agent_runtime_timeout",
        retryable=True,
        metadata={"timeout_seconds": timeout_seconds},
    )
    visible_text = _resolve_visible_text("", captured_tool_results)
    if durable_write_error is not None:
        visible_text = ""
    visible_messages = (
        (VisibleMessage(message_type="text", content=visible_text),)
        if visible_text
        else ()
    )
    if visible_messages and durable_write_error is None:
        return AgentRunResult(
            visible_messages=visible_messages,
            post_analyze_input={
                "input_message": input_message,
                "message_source": _message_source(agent_input, run_context),
            },
            tool_results=captured_tool_results,
            metrics={"capability_result_count": len(captured_tool_results)},
            trace={"runtime": "agent", "status": "timeout_with_visible_summary"},
            output_disposition=OutputDisposition(status="ok"),
            error_disposition=timeout_error,
        )

    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=captured_tool_results,
        metrics={"capability_result_count": len(captured_tool_results)},
        trace={"runtime": "agent", "status": "timeout"},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=durable_write_error or timeout_error,
    )


async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    tool_results: list[CapabilityResult] = []
    try:
        if agent_input.input_type not in _SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")

        input_message = _input_message(agent_input)
        agent = _create_agent(
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        timeout_seconds = _agent_runtime_timeout_seconds()
        try:
            run_output = await asyncio.wait_for(
                agent.arun(
                    input=_model_input(
                        agent_input=agent_input,
                        run_context=run_context,
                        input_message=input_message,
                    ),
                    session_id=run_context.conversation.id,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return _timeout_result(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                timeout_seconds=timeout_seconds,
                tool_results=tool_results,
            )
        captured_tool_results = tuple(tool_results)
        durable_write_error = _check_durable_write_contract(captured_tool_results)
        final_text = _extract_final_text(run_output)
        unconfirmed_promise_error = _check_unconfirmed_durable_write_promise(
            agent_input=agent_input,
            final_text=final_text,
            tool_results=captured_tool_results,
        )
        runtime_contract_error = durable_write_error or unconfirmed_promise_error
        visible_text = _resolve_visible_text(final_text, captured_tool_results)
        if runtime_contract_error is not None:
            visible_text = ""
        visible_messages = (
            (VisibleMessage(message_type="text", content=visible_text),)
            if visible_text
            else ()
        )

        if visible_messages and runtime_contract_error is None:
            return AgentRunResult(
                visible_messages=visible_messages,
                post_analyze_input={
                    "input_message": input_message,
                    "message_source": _message_source(agent_input, run_context),
                },
                tool_results=captured_tool_results,
                metrics={"capability_result_count": len(captured_tool_results)},
                trace={"runtime": "agent"},
                output_disposition=OutputDisposition(status="ok"),
            )

        return AgentRunResult(
            visible_messages=visible_messages,
            post_analyze_input=None,
            tool_results=captured_tool_results,
            metrics={"capability_result_count": len(captured_tool_results)},
            trace={"runtime": "agent", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=runtime_contract_error,
        )
    except UnknownToolError as exc:
        return _unknown_tool_result(exc, tool_results)
    except Exception:
        return _exception_result(tool_results)
