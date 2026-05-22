from __future__ import annotations

import asyncio
import inspect
from typing import Any

from agno.agent import Agent
from agno.tools import tool

from agent.agno_agent.capabilities import ReminderIntentPort, SchedulingCapabilityPort
from agent.agno_agent.capabilities.scheduling import (
    SCHEDULING_TOOL_NAMES,
    _READ_ONLY_TOOL_NAMES,
)
from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.domain_results import (
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
)
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


def _scheduling_entity_type(tool_name: str) -> str:
    if "appointment" in tool_name:
        return (
            "appointment_request"
            if tool_name == "request_appointment"
            else "appointment"
        )
    if "bookable_window" in tool_name:
        return "bookable_window"
    if "service_link" in tool_name:
        return "service_link"
    return "user_link"


def _scheduling_entity_id(tool_name: str, content: dict[str, Any]) -> str | None:
    for key in (
        "appointment_id",
        "appointment_or_request_id",
        "request_id",
        "appointment_request_id",
        "bookable_window_id",
        "window_instance_id",
        "service_link_id",
        "user_link_id",
        "link_id",
        "id",
    ):
        value = content.get(key)
        if value is not None and str(value):
            return str(value)
    return None


def _scheduling_reply_contract(
    *,
    tool_name: str,
    ok: bool,
    effect: str,
) -> ReplyContract:
    if not ok:
        return ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("appointment_confirmed",),
            allow_rephrase=True,
        )
    if effect == "write":
        return ReplyContract(
            intent="confirm_execution",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("needs_more_info",),
            allow_rephrase=True,
        )
    return ReplyContract(
        intent="direct_answer",
        required_facts=(),
        required_questions=(),
        prohibited_claims=("appointment_confirmed",),
        allow_rephrase=True,
    )


def _scheduling_capability_to_domain_result(
    *,
    tool_name: str,
    result: CapabilityResult,
) -> DomainExecutionResult:
    content = dict(result.content)
    effect = "read" if tool_name in _READ_ONLY_TOOL_NAMES else "write"
    error = (
        DomainError(
            code=str(result.error or "scheduling_failed"),
            message=str(result.error or "Scheduling operation failed"),
            retryable=True,
            detail={"tool_name": tool_name, "content": content},
        )
        if not result.ok
        else None
    )
    operation = DomainOperationResult(
        action=tool_name,
        ok=result.ok,
        effect=effect if result.ok else "none",
        entity_type=_scheduling_entity_type(tool_name),
        entity_id=_scheduling_entity_id(tool_name, content),
        facts=content,
        error=error,
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="executed" if result.ok else "failed",
        operations=(operation,),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=_scheduling_reply_contract(
            tool_name=tool_name,
            ok=result.ok,
            effect=effect,
        ),
        error=error,
    )


def _no_scheduling_tool_called_result(intent: str) -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("appointment_confirmed",),
            allow_rephrase=True,
        ),
        error=DomainError(
            code="no_tool_called",
            message="Scheduling execution agent did not call a scheduling tool",
            retryable=True,
            detail={"intent": intent},
        ),
    )


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
    domain_results: list[DomainExecutionResult],
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
            duplicate = DomainExecutionResult(
                domain="scheduling",
                outcome="failed",
                operations=(),
                missing_fields=(),
                safety_boundary=None,
                reply_contract=ReplyContract(
                    intent="report_failure",
                    required_facts=(),
                    required_questions=(),
                    prohibited_claims=("appointment_confirmed",),
                    allow_rephrase=True,
                ),
                error=DomainError(
                    code="duplicate_scheduling_tool_call",
                    message="Scheduling execution agent called more than one tool",
                    retryable=False,
                    detail={"tool_name": tool_name},
                ),
            )
            domain_results.append(duplicate)
            return duplicate.to_dict()

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
        domain_result = _scheduling_capability_to_domain_result(
            tool_name=tool_name,
            result=result,
        )
        domain_results.append(domain_result)
        return domain_result.to_dict()

    return scheduling_tool


async def run_scheduling_domain(
    *,
    input_message: str,
    intent: str,
    run_context: AgentRunContext,
    domain_results: list[DomainExecutionResult],
) -> dict[str, Any]:
    """Spawn SchedulingExecutionAgent and append typed scheduling domain results."""
    local_domain_results: list[DomainExecutionResult] = []
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
                domain_results=local_domain_results,
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
    if not local_domain_results:
        result = _no_scheduling_tool_called_result(intent)
        domain_results.append(result)
        return result.to_dict()

    last = local_domain_results[-1]
    domain_results.extend(local_domain_results)
    return last.to_dict()
