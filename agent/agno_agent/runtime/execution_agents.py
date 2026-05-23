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


def _scheduling_entity_type(tool_name: str) -> str:
    if "shared_reminder" in tool_name:
        return "shared_reminder_request"
    if "friend_request" in tool_name:
        return "friend_request"
    if "friendship" in tool_name or tool_name == "list_friends":
        return "friendship"
    if "block" in tool_name:
        return "account_block"
    return "user_link"


def _scheduling_entity_id(tool_name: str, content: dict[str, Any]) -> str | None:
    for key in (
        "request_id",
        "friendship_id",
        "blocked_account_id",
        "shared_reminder_request_id",
        "friend_request_id",
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


def _returnable_scheduling_result(
    results: list[DomainExecutionResult],
) -> DomainExecutionResult:
    for result in reversed(results):
        if result.outcome == "executed":
            return result
    return results[-1]


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
        domain_result = _scheduling_capability_to_domain_result(
            tool_name=tool_name,
            result=result,
        )
        domain_results.append(domain_result)
        return domain_result.to_dict()

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
        instructions=_SCHEDULING_SYSTEM_PROMPT,
        tools=tools,
        db=None,
        add_history_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )
    await agent.arun(input=_scheduling_agent_input(input_message, intent))
    if not local_domain_results:
        result = _no_scheduling_tool_called_result(intent)
        domain_results.append(result)
        return result.to_dict()

    selected = _returnable_scheduling_result(local_domain_results)
    domain_results.extend(local_domain_results)
    return selected.to_dict()
