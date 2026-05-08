from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)

logger = logging.getLogger(__name__)

_SUPPORTED_INPUT_TYPES = {"user.turn", "reminder.fired", "deferred_action.fire"}


def _create_agent(**kwargs: Any) -> Any:
    raise NotImplementedError("agent runtime construction is not implemented yet")


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


def _extract_tool_results(run_output: Any) -> tuple[CapabilityResult, ...]:
    raw_tool_results = getattr(run_output, "tool_results", ())
    if raw_tool_results is None:
        return ()
    return tuple(
        result for result in raw_tool_results if isinstance(result, CapabilityResult)
    )


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


def _exception_result() -> AgentRunResult:
    logger.exception("Agent runtime failed closed")
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=(),
        metrics={"capability_result_count": 0},
        trace={"runtime": "agent", "status": "exception"},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="agent_runtime_exception",
            retryable=True,
        ),
    )


async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    try:
        if agent_input.input_type not in _SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")

        input_message = _input_message(agent_input)
        agent = _create_agent(agent_input=agent_input, run_context=run_context)
        run_output = await agent.arun(
            input=input_message,
            session_id=run_context.conversation.id,
        )
        tool_results = _extract_tool_results(run_output)
        durable_write_error = _check_durable_write_contract(tool_results)
        final_text = _extract_final_text(run_output)
        visible_text = _resolve_visible_text(final_text, tool_results)
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
                tool_results=tool_results,
                metrics={"capability_result_count": len(tool_results)},
                trace={"runtime": "agent"},
                output_disposition=OutputDisposition(status="ok"),
            )

        return AgentRunResult(
            visible_messages=visible_messages,
            post_analyze_input=None,
            tool_results=tool_results,
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "agent", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=durable_write_error,
        )
    except Exception:
        return _exception_result()
