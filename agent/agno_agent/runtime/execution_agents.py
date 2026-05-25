from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Mapping
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
    "You are the friend-link, friend-calendar, and shared-reminder execution worker. "
    "Call exactly one scheduling tool that matches the intent, except for the "
    "lookup-then-act sequences described below. "
    "When a user asks to add a friend by public user-link code, call "
    "send_friend_request_by_user_link_code with user_link_code. "
    "For accept_friend_request / reject_friend_request / cancel_friend_request "
    "when you do not yet have a concrete request_id, pass friend_name when the "
    "other person's name is present; otherwise call the tool without a name. "
    "The gateway resolves a single pending request and fails closed if the "
    "name is ambiguous, no request exists, or multiple unnamed requests exist. "
    "For accept_shared_reminder / reject_shared_reminder when you do not yet "
    "have a concrete request_id, pass requester_name with the inviter's name; "
    "for cancel_shared_reminder pass invitee_name. The gateway resolves a "
    "single pending shared reminder and fails closed if the name is missing "
    "or matches more than one pending reminder. "
    "For create_shared_reminder, pass invitee_name when the user named a friend "
    "but did not provide an account id; do not call list_friends for this intent. "
    "For create_shared_reminder, derive title from the concrete shared item "
    "requested in the current user message; do not use product defaults or "
    "older conversation topics as the title. "
    "The gateway resolves invitee_name to one active friend and fails closed otherwise. "
    "For list_shared_reminders, pass friend_name when the user names a friend; "
    "if the user asks about a specific state, also pass status for that state. "
    "For current-account overview queries such as my courses today, omit "
    "friend_name and pass from_date, to_date, and timezone for the requested "
    "local day. The gateway resolves named friends server-side and can also "
    "return shared reminders involving the current account without a friend filter. "
    "For list_friend_calendar_facts: pass friend_name with the other person's "
    "name (gateway resolves to account_id and fails closed on ambiguity), AND "
    "always pass from_date + to_date as ISO YYYY-MM-DD strings. Default to "
    "today and today+7 days when the user did not state a range. Do NOT call "
    "list_friends first — the gateway resolver does it. Missing dates cause "
    "the gateway to reject with invalid_body. "
    "Do not create shared reminder state unless the named person resolves to "
    "one active friend. Ask for clarification when the name is ambiguous. "
    "Coke reminders are the source for friend availability. "
    "Do not use Google Calendar for friend availability. "
    "Do not ask the backend for recommended slots. "
    "Pass duration_minutes only after the conversation or policy determines it. "
    "Ordinary personal reminders are not scheduling-domain work. "
    "Do not treat an iLink QR as a public user-link QR."
)


class _SchedulingExecutionGuard:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._claimed_tools: list[str] = []

    async def claim(self, tool_name: str) -> bool:
        async with self._lock:
            if not self._claimed_tools:
                self._claimed_tools.append(tool_name)
                return True
            if (
                self._claimed_tools == ["list_friends"]
                and tool_name == "list_friend_calendar_facts"
            ):
                self._claimed_tools.append(tool_name)
                return True
            return False


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
    if tool_name == "list_friend_calendar_facts":
        return "friend_calendar_facts"
    if "shared_reminder" in tool_name:
        return "shared_reminder_request"
    if "friend_request" in tool_name:
        return "friend_request"
    if "friendship" in tool_name or tool_name == "list_friends":
        return "friendship"
    return "user_link"


def _scheduling_entity_id(tool_name: str, content: dict[str, Any]) -> str | None:
    for key in (
        "request_id",
        "friendship_id",
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
        target_account_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        invitee_account_id: str | None = None,
        invitee_name: str | None = None,
        friend_account_id: str | None = None,
        title: str | None = None,
        fire_at: str | None = None,
        duration_minutes: int | None = None,
        status: str | None = None,
        timezone: str | None = None,
        request_id: str | None = None,
        friend_name: str | None = None,
        requester_name: str | None = None,
        friendship_id: str | None = None,
        user_link_code: str | None = None,
        message: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Use only for the scheduling action specified in the intent."""
        if execution_guard is not None and not await execution_guard.claim(tool_name):
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
                    "from_date": from_date,
                    "to_date": to_date,
                    "invitee_account_id": invitee_account_id or friend_account_id,
                    "invitee_name": invitee_name,
                    "title": title,
                    "fire_at": fire_at,
                    "duration_minutes": duration_minutes,
                    "status": status,
                    "timezone": timezone,
                    "request_id": request_id,
                    "friend_name": friend_name,
                    "requester_name": requester_name,
                    "friendship_id": friendship_id,
                    "user_link_code": user_link_code,
                    "message": message,
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


def _tool_names_for_intent(intent: str) -> tuple[str, ...]:
    normalized = intent.lower()
    if "list_shared_reminders" in normalized:
        return ("list_shared_reminders",)
    if "create_shared_reminder" in normalized:
        return ("create_shared_reminder",)
    if "send_friend_request_by_user_link_code" in normalized:
        return ("send_friend_request_by_user_link_code",)
    if (
        ("user_link" in normalized or "user link" in normalized or "link code" in normalized)
        and ("friend" in normalized or "add" in normalized)
    ):
        return ("send_friend_request_by_user_link_code",)
    if ("链接码" in intent or "邀请链接" in intent) and ("加好友" in intent or "好友" in intent):
        return ("send_friend_request_by_user_link_code",)
    # Single-write intents — restrict to that one tool so the inner LLM cannot
    # silently fall back to a read tool like list_friend_requests when the
    # user message also contains read-tinted keywords ("未处理", "看一下").
    # Gateway resolves friend_name / requester_name server-side.
    for single in (
        "accept_friend_request",
        "reject_friend_request",
        "cancel_friend_request",
        "remove_friendship",
        "accept_shared_reminder",
        "reject_shared_reminder",
        "cancel_shared_reminder",
    ):
        if single in normalized:
            return (single,)
    return SCHEDULING_TOOL_NAMES


def _forced_tool_name_for_intent(intent: str) -> str | None:
    normalized = intent.lower()
    for tool_name in SCHEDULING_TOOL_NAMES:
        if tool_name in normalized:
            return tool_name
    return None


def _normalize_forced_scheduling_call(
    *,
    intent: str,
    forced_args: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    normalized_intent = intent
    normalized_args = dict(forced_args)
    for key in ("operation", "intent", "action"):
        value = normalized_args.get(key)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if candidate in {
            "accept_shared_reminder",
            "reject_shared_reminder",
            "cancel_shared_reminder",
        }:
            normalized_intent = candidate
            normalized_args.pop(key, None)
            break

    tool_name = _forced_tool_name_for_intent(normalized_intent)
    if tool_name == "create_shared_reminder":
        if "invitee_name" not in normalized_args and "friend_name" in normalized_args:
            normalized_args["invitee_name"] = normalized_args.pop("friend_name")
        if "fire_at" not in normalized_args and "date_time" in normalized_args:
            normalized_args["fire_at"] = normalized_args.pop("date_time")
        has_counterparty = any(
            str(normalized_args.get(key) or "").strip()
            for key in (
                "invitee_account_id",
                "invitee_name",
                "friend_account_id",
                "friend_name",
            )
        )
        has_title = bool(str(normalized_args.get("title") or "").strip())
        has_fire_at = bool(str(normalized_args.get("fire_at") or "").strip())
        if not (has_counterparty and has_title and has_fire_at):
            return "create_shared_reminder", None

    return normalized_intent, normalized_args


def _scheduling_agent_input(input_message: str, intent: str) -> str:
    return (
        f"Resolved scheduling intent: {intent}\n"
        f"User message: {input_message}"
    )


def _partial_friend_calendar_name_needs_clarification(
    *,
    input_message: str,
    intent: str,
    forced_args: Mapping[str, Any] | None = None,
) -> bool:
    if "list_friend_calendar_facts" not in intent.lower():
        return False

    friend_name = (
        str(forced_args.get("friend_name") or "").strip()
        if forced_args is not None
        else ""
    )
    if not friend_name:
        friend_name_match = re.search(
            r"""["']?friend_name["']?\s*[:=]\s*["']?([A-Za-z])["']?""",
            intent,
        )
        friend_name = friend_name_match.group(1) if friend_name_match else ""
    if not friend_name:
        friend_name_match = re.search(
            r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])"
            r"\s*(?:那个|那位|这个|这位)?朋友",
            input_message,
            flags=re.IGNORECASE,
        )
        friend_name = friend_name_match.group(1) if friend_name_match else ""
    if not re.fullmatch(r"[A-Za-z]", friend_name):
        return False

    return re.search(
        rf"(?<![A-Za-z]){re.escape(friend_name)}(?![A-Za-z])"
        r"\s*(?:那个|那位|这个|这位)?朋友",
        input_message,
        flags=re.IGNORECASE,
    ) is not None


def _ambiguous_friend_calendar_name_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="scheduling",
        outcome="needs_clarification",
        operations=(),
        missing_fields=("friend_name",),
        safety_boundary="ambiguous_friend_name",
        reply_contract=ReplyContract(
            intent="ask_clarification",
            required_facts=(),
            required_questions=("which_friend",),
            prohibited_claims=("appointment_confirmed",),
            allow_rephrase=True,
        ),
    )


async def run_scheduling_domain(
    *,
    input_message: str,
    intent: str,
    run_context: AgentRunContext,
    domain_results: list[DomainExecutionResult],
    forced_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spawn SchedulingExecutionAgent and append typed scheduling domain results."""
    if _partial_friend_calendar_name_needs_clarification(
        input_message=input_message,
        intent=intent,
        forced_args=forced_args,
    ):
        result = _ambiguous_friend_calendar_name_result()
        domain_results.append(result)
        return result.to_dict()

    local_domain_results: list[DomainExecutionResult] = []
    execution_guard = _SchedulingExecutionGuard()
    tool_names = _tool_names_for_intent(intent)
    if forced_args is not None:
        intent, forced_args = _normalize_forced_scheduling_call(
            intent=intent,
            forced_args=forced_args,
        )
        if forced_args is None:
            tool_names = _tool_names_for_intent(intent)
        else:
            tool_name = _forced_tool_name_for_intent(intent)
            if tool_name is None:
                result = _no_scheduling_tool_called_result(intent)
                domain_results.append(result)
                return result.to_dict()
            port = SchedulingCapabilityPort(tool_name=tool_name)
            capability_result = await _run_port(
                port,
                input_message=input_message,
                run_context=run_context,
                args=dict(forced_args),
            )
            domain_result = _scheduling_capability_to_domain_result(
                tool_name=tool_name,
                result=capability_result,
            )
            domain_results.append(domain_result)
            return domain_result.to_dict()

    ports = {
        name: SchedulingCapabilityPort(tool_name=name) for name in tool_names
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
