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


def _build_chat_response_instructions(run_context: AgentRunContext) -> str:
    from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE

    timezone = run_context.user.timezone or "UTC"
    return "\n\n".join([INSTRUCTIONS_CHAT_RESPONSE, f"Default user timezone: {timezone}"])


def _create_agent(
    *,
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> Any:
    from agno.agent import Agent
    from agno.tools import tool

    from agent.agno_agent.model_factory import create_llm_model
    from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers

    wrappers = build_capability_tool_wrappers(
        ports=_default_capability_ports(),
        run_context=run_context,
        input_message=input_message,
        tool_results=tool_results,
    )
    tools = [tool(name=name)(fn) for name, fn in wrappers.items()]
    return Agent(
        id="coke-single-agent",
        name="CokeSingleAgent",
        model=create_llm_model(role="reminder_detect", max_tokens=2000),
        instructions=_build_chat_response_instructions(run_context),
        tools=tools,
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
        run_output = await agent.arun(
            input=input_message,
            session_id=run_context.conversation.id,
        )
        captured_tool_results = tuple(tool_results)
        durable_write_error = _check_durable_write_contract(captured_tool_results)
        final_text = _extract_final_text(run_output)
        visible_text = _resolve_visible_text(final_text, captured_tool_results)
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
            error_disposition=durable_write_error,
        )
    except Exception:
        return _exception_result(tool_results)
