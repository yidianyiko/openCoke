from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.domain_results import DomainExecutionResult
from agent.agno_agent.runtime.errors import UnknownToolError
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.session import get_agent_session_db

logger = logging.getLogger(__name__)

_SUPPORTED_INPUT_TYPES = {"user.turn", "reminder.fired"}
_DEFAULT_AGENT_RUNTIME_TIMEOUT_SECONDS = 100.0
_MAX_VISIBLE_TEXT_SEGMENTS = 3
_SCHEDULING_INTENT_NAMES = {
    "create_shared_reminder",
    "accept_shared_reminder",
    "reject_shared_reminder",
    "cancel_shared_reminder",
    "send_friend_request_by_user_link_code",
    "list_friend_requests",
    "accept_friend_request",
    "reject_friend_request",
    "cancel_friend_request",
    "list_friends",
    "remove_friendship",
    "block_account",
    "unblock_account",
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "list_friend_calendar_facts",
}
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
        r"(\u5df2\u7ecf|\u5df2|\u5e2e\u4f60|\u597d\u5566).{0,24}"
        r"(\u5efa\u4e86|\u521b\u5efa|created|set up).{0,24}"
        r"(\u5171\u4eab\u63d0\u9192|shared reminder)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(i(?:'ll| will|'ve| have)|we(?:'ll| will)).{0,40}"
        r"\b(remind|notify|set (?:up )?(?:the )?reminder)",
        re.IGNORECASE,
    ),
    # Friend-request accept claims without a successful write. Requires a
    # first-person / completed lead-in so we don't trip on "wait for the other
    # side to accept your request" — those are safe statements, not promises.
    re.compile(
        r"(已经|已|帮你|好啦|好嘞|I(?:'ve| have))"
        r"(?:(?:.{0,32}(通过|接受|accepted|approved).{0,32}(请求|好友|friend request|friend-request))"
        r"|(?:.{0,32}(请求|好友|friend request|friend-request).{0,16}(通过|接受|accepted|approved)))",
        re.IGNORECASE,
    ),
    # "Now you're friends" claims: "你们现在是好友/好朋友啦", "now you are friends".
    re.compile(
        r"(你们现在|现在你们|now you(?:'re| are))"
        r".{0,12}(是好(友|朋友)|friends?)",
        re.IGNORECASE,
    ),
)


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _product_notification_metadata(agent_input: AgentInput) -> Mapping[str, Any] | None:
    payload = agent_input.payload
    metadata = getattr(payload, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    product_notification = metadata.get("product_notification")
    if not isinstance(product_notification, Mapping):
        return None
    return product_notification


def _allows_product_notification_action(
    product_notification: Mapping[str, Any],
    action: str,
) -> bool:
    allowed_actions = product_notification.get("allowed_actions")
    if not isinstance(allowed_actions, Sequence) or isinstance(
        allowed_actions, (str, bytes, bytearray)
    ):
        return True
    normalized = {str(item).casefold() for item in allowed_actions}
    return action in normalized


def _product_notification_decision(input_message: str) -> Literal["accept", "reject"] | None:
    normalized = re.sub(r"[\s。.!！?？,，、~～]+", "", input_message.casefold())
    if not normalized or len(normalized) > 16:
        return None
    if _contains_any(
        normalized,
        ("拒绝", "不通过", "不同意", "不要", "decline", "reject"),
    ):
        return "reject"
    if _contains_any(
        normalized,
        ("确认", "同意", "接受", "通过", "可以", "好的", "好", "yes", "ok", "accept", "approve"),
    ):
        return "accept"
    return None


def _infer_scheduling_intent_from_product_notification(
    input_message: str,
    product_notification: Mapping[str, Any] | None,
) -> str | None:
    if not product_notification:
        return None
    decision = _product_notification_decision(input_message)
    if decision is None or not _allows_product_notification_action(product_notification, decision):
        return None

    request_type = str(product_notification.get("request_type") or "")
    if request_type == "friend_request":
        return "accept_friend_request" if decision == "accept" else "reject_friend_request"
    if request_type == "shared_reminder_request":
        return "accept_shared_reminder" if decision == "accept" else "reject_shared_reminder"
    return None


def _infer_scheduling_intent_from_agent_input(
    input_message: str,
    agent_input: AgentInput,
) -> str | None:
    product_notification_intent = _infer_scheduling_intent_from_product_notification(
        input_message,
        _product_notification_metadata(agent_input),
    )
    if product_notification_intent:
        return product_notification_intent
    return _infer_scheduling_intent_from_message(input_message)


def _infer_scheduling_intent_from_message(input_message: str) -> str | None:
    text = input_message.casefold()

    if _contains_any(input_message, ("我的", "我自己的", "自己的")) and _contains_any(
        input_message, ("用户链接", "邀请链接", "好友邀请链接", "邀请码")
    ):
        if _contains_any(input_message, ("重置", "reset")):
            return "reset_user_link"
        if _contains_any(input_message, ("停用", "禁用", "disable")):
            return "disable_user_link"
        return "get_user_link"

    if _contains_any(input_message, ("链接码", "邀请链接")) or (
        "add friend" in text and (_contains_any(text, ("link", "code")) or "friend" in text)
    ):
        if _contains_any(input_message, ("加好友", "加上", "添加好友")) or "add friend" in text:
            return "send_friend_request_by_user_link_code"

    if _contains_any(input_message, ("好友请求", "待处理好友请求", "未处理好友请求")) or (
        "friend request" in text or "friend-request" in text
    ):
        if _contains_any(input_message, ("通过", "接受")) or _contains_any(
            text, ("accept", "approve")
        ):
            return "accept_friend_request"
        if _contains_any(input_message, ("拒绝", "不通过")) or "reject" in text:
            return "reject_friend_request"
        if _contains_any(input_message, ("取消", "撤回")) or "cancel" in text:
            return "cancel_friend_request"
        if _contains_any(
            input_message,
            ("列表", "有哪些", "看一下", "查看", "未处理", "待处理"),
        ) or "list" in text:
            return "list_friend_requests"

    if _contains_any(input_message, ("好友列表", "我的好友", "都有哪些好友")) or (
        "list friends" in text
    ):
        return "list_friends"

    if _contains_any(input_message, ("屏蔽", "拉黑")) or "block" in text:
        if _contains_any(input_message, ("解除", "取消")) or "unblock" in text:
            return "unblock_account"
        return "block_account"

    if _contains_any(input_message, ("移除好友", "删除好友", "解除好友")) or (
        "unfriend" in text
        or "remove friend" in text
        or "remove friendship" in text
    ):
        return "remove_friendship"

    if _contains_any(input_message, ("共享提醒", "shared reminder")):
        if _contains_any(input_message, ("通过", "接受", "同意")) or "accept" in text:
            return "accept_shared_reminder"
        if _contains_any(input_message, ("拒绝", "不通过")) or "reject" in text:
            return "reject_shared_reminder"
        if _contains_any(input_message, ("取消", "撤回")) or "cancel" in text:
            return "cancel_shared_reminder"
        if _contains_any(input_message, ("建", "创建", "设置", "约")) or "create" in text:
            return "create_shared_reminder"
        if _contains_any(
            input_message,
            ("列表", "列", "看看", "查看", "有没有", "待处理"),
        ) or "list" in text:
            return "list_pending_shared_reminders"

    if _contains_any(input_message, ("用户链接", "我的链接", "邀请码")):
        if _contains_any(input_message, ("重置", "reset")):
            return "reset_user_link"
        if _contains_any(input_message, ("停用", "禁用", "disable")):
            return "disable_user_link"
        return "get_user_link"

    return None


def _normalize_scheduling_intent(raw_intent: Any, input_message: str) -> str:
    if isinstance(raw_intent, str):
        candidate = raw_intent.strip()
        if not candidate:
            inferred = _infer_scheduling_intent_from_message(input_message)
            return inferred or ""
        prefix = candidate.split(":", 1)[0].strip()
        if prefix in _SCHEDULING_INTENT_NAMES:
            return prefix
        inferred = _infer_scheduling_intent_from_message(input_message)
        return inferred or candidate

    if isinstance(raw_intent, Mapping):
        for key, value in raw_intent.items():
            if isinstance(key, str) and key in _SCHEDULING_INTENT_NAMES:
                if isinstance(value, Mapping) and value:
                    return (
                        f"{key}: "
                        f"{json.dumps(_normalize_scheduling_intent_args(key, value), ensure_ascii=False)}"
                    )
                return key

        for key in ("intent", "action", "tool", "tool_name", "name"):
            value = raw_intent.get(key)
            if isinstance(value, str) and value.strip():
                normalized = _normalize_scheduling_intent(value, input_message)
                if normalized:
                    return normalized

        inferred = _infer_scheduling_intent_from_message(input_message)
        if inferred:
            return inferred

    inferred = _infer_scheduling_intent_from_message(input_message)
    if inferred:
        return inferred
    raise ValueError("scheduling intent could not be resolved")


def _normalize_scheduling_intent_args(
    tool_name: str,
    args: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = dict(args)
    if tool_name == "create_shared_reminder":
        if "invitee_name" not in normalized and "friend_name" in normalized:
            normalized["invitee_name"] = normalized.pop("friend_name")
        if "title" not in normalized and "reminder_title" in normalized:
            normalized["title"] = normalized.pop("reminder_title")
        if "fire_at" not in normalized and "reminder_time" in normalized:
            normalized["fire_at"] = normalized.pop("reminder_time")
    return normalized


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


def _utility_capability_ports() -> dict[str, Any]:
    from agent.agno_agent.capabilities import (
        CalendarImportPort,
        TimezoneCapabilityPort,
        UrlContextPort,
    )

    return {
        "timezone": TimezoneCapabilityPort(),
        "calendar_import": CalendarImportPort(),
        "url_context": UrlContextPort(),
    }


def _create_interaction_agent(
    *,
    run_context: AgentRunContext,
    agent_input: AgentInput,
    input_message: str,
    capability_results: list[CapabilityResult],
    domain_results: list[DomainExecutionResult],
    preloaded_scheduling_domain_result: dict[str, Any] | None = None,
    preselected_scheduling_intent: str | None = None,
    session_db: Any | None = None,
) -> Any:
    from agno.agent import Agent
    from agno.tools import tool

    from agent.agno_agent.model_factory import create_llm_model
    from agent.agno_agent.runtime.chat_response_instructions import (
        build_chat_response_instructions,
    )
    from agent.agno_agent.runtime.execution_agents import (
        run_reminder_domain,
        run_scheduling_domain,
    )

    if agent_input.input_type == "reminder.fired":
        final_tools = []
    else:
        utility_wrappers = build_capability_tool_wrappers(
            ports=_utility_capability_ports(),
            run_context=run_context,
            input_message=input_message,
            capability_results=capability_results,
        )
        utility_tools = [tool(name=name)(fn) for name, fn in utility_wrappers.items()]
        reminder_domain_lock = asyncio.Lock()
        reminder_domain_result: dict[str, Any] = {}
        scheduling_domain_lock = asyncio.Lock()
        scheduling_domain_result: dict[str, Any] = (
            {"result": preloaded_scheduling_domain_result}
            if preloaded_scheduling_domain_result is not None
            else {}
        )

        async def reminder_domain(**_model_supplied_args: Any) -> dict[str, Any]:
            """Use for explicit reminder create, update, cancel, complete, or list requests."""
            async with reminder_domain_lock:
                if "result" in reminder_domain_result:
                    return reminder_domain_result["result"]
                result = await run_reminder_domain(
                    input_message=input_message,
                    run_context=run_context,
                    domain_results=domain_results,
                )
                reminder_domain_result["result"] = result
                return result

        async def scheduling_domain(intent: Any = None) -> dict[str, Any]:
            """Use for explicit user-link, friend-request, friendship/block, or shared-reminder actions."""
            async with scheduling_domain_lock:
                if "result" in scheduling_domain_result:
                    return scheduling_domain_result["result"]
                normalized_intent = _normalize_scheduling_intent(intent, input_message)
                result = await run_scheduling_domain(
                    input_message=input_message,
                    intent=normalized_intent,
                    run_context=run_context,
                    domain_results=domain_results,
                )
                scheduling_domain_result["result"] = result
                return result

        scheduling_tool = tool(name="scheduling_domain", stop_after_tool_call=False)(
            scheduling_domain
        )
        domain_tools = [scheduling_tool]
        if preselected_scheduling_intent is None:
            domain_tools.insert(
                0,
                tool(name="reminder_domain", stop_after_tool_call=False)(
                    reminder_domain
                ),
            )
        final_tools = domain_tools + utility_tools

    resolved_session_db = session_db or get_agent_session_db()
    return Agent(
        id="coke-interaction-agent",
        name="CokeInteractionAgent",
        model=create_llm_model(role="chat_response", max_tokens=2000),
        instructions=build_chat_response_instructions(run_context, agent_input),
        tools=final_tools,
        db=resolved_session_db,
        add_history_to_context=True,
        num_history_messages=20,
        add_session_state_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )


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
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump())
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


def _build_capability_tool_wrapper(
    *,
    tool_name: str,
    port: Any,
    run_context: AgentRunContext,
    input_message: str,
    capability_results: list[CapabilityResult],
) -> Any:
    async def _call(args: dict[str, Any]) -> dict[str, Any]:
        result = await _run_capability_port(
            port,
            input_message=input_message,
            run_context=run_context,
            args=args,
        )
        capability_results.append(result)
        return _model_facing_envelope(tool_name, result)

    if tool_name == "timezone":

        async def timezone(
            action: Literal["direct_set", "proposal", "confirm"],
            timezone: str = "",
            decision: str = "",
        ) -> dict[str, Any]:
            """Use direct_set to change timezone now, proposal to ask confirmation, or confirm to consume yes/no."""
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


def build_capability_tool_wrappers(
    *,
    ports: Mapping[str, Any],
    run_context: AgentRunContext,
    input_message: str,
    capability_results: list[CapabilityResult],
) -> dict[str, Any]:
    wrappers: dict[str, Any] = {}

    for tool_name, port in ports.items():
        wrappers[tool_name] = _build_capability_tool_wrapper(
            tool_name=tool_name,
            port=port,
            run_context=run_context,
            input_message=input_message,
            capability_results=capability_results,
        )

    return wrappers


def _string_content(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _message_field(message: Any, field: str) -> Any:
    if isinstance(message, Mapping):
        return message.get(field)
    return getattr(message, field, None)


def _latest_assistant_text(run_output: Any) -> str:
    messages = getattr(run_output, "messages", None)
    if not isinstance(messages, Sequence) or isinstance(
        messages, (str, bytes, bytearray)
    ):
        return ""
    for message in reversed(messages):
        if _message_field(message, "role") != "assistant":
            continue
        content = _string_content(_message_field(message, "content"))
        if content:
            return content
    return ""


def _text_message_segments(content: str) -> tuple[str, ...]:
    return tuple(segment.strip() for segment in content.splitlines() if segment.strip())


_FENCED_JSON_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?```\s*$",
    re.DOTALL,
)


def _try_parse_envelope_json(final_text: str) -> Any:
    """Parse a MultiModalResponses envelope, transparently stripping markdown
    code fences the model sometimes wraps it in. Returns the parsed object or
    None when nothing JSON-shaped can be recovered."""
    try:
        return json.loads(final_text)
    except json.JSONDecodeError:
        pass
    match = _FENCED_JSON_RE.match(final_text)
    if match is not None:
        try:
            return json.loads(match.group("body"))
        except json.JSONDecodeError:
            pass
    return _recover_lenient_envelope(final_text)


_LENIENT_ENVELOPE_RE = re.compile(r'"MultiModalResponses"\s*:\s*\[')
_LENIENT_CONTENT_RE = re.compile(
    r'"type"\s*:\s*"text"[^{}]*?"content"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.DOTALL,
)


def _recover_lenient_envelope(final_text: str) -> Any:
    """Last-resort recovery when the model emits a malformed envelope (e.g.
    extra brace, missing comma). We don't try to repair the JSON; we just pull
    out the text segments verbatim. Returns a synthetic envelope dict or None
    when no plausible envelope signature is present."""
    if _LENIENT_ENVELOPE_RE.search(final_text) is None:
        return None
    segments: list[dict[str, str]] = []
    for match in _LENIENT_CONTENT_RE.finditer(final_text):
        raw = match.group(1)
        try:
            decoded = json.loads(f'"{raw}"')
        except json.JSONDecodeError:
            decoded = raw
        decoded = decoded.strip()
        if decoded:
            segments.append({"type": "text", "content": decoded})
    if not segments:
        return None
    return {"MultiModalResponses": segments}


def _parse_visible_text_segments(final_text: str) -> tuple[str, ...]:
    if not final_text:
        return ()

    payload = _try_parse_envelope_json(final_text)
    if payload is None:
        return (final_text,)

    if not isinstance(payload, Mapping):
        return (final_text,)

    responses = payload.get("MultiModalResponses")
    if not isinstance(responses, Sequence) or isinstance(
        responses, (str, bytes, bytearray)
    ):
        return (final_text,)

    segments: list[str] = []
    for item in responses:
        if not isinstance(item, Mapping) or item.get("type") != "text":
            continue
        content = _string_content(item.get("content"))
        if not content:
            continue
        for segment in _text_message_segments(content):
            segments.append(segment)
            if len(segments) >= _MAX_VISIBLE_TEXT_SEGMENTS:
                break
        if len(segments) >= _MAX_VISIBLE_TEXT_SEGMENTS:
            break
    return tuple(segments)


def _visible_text_for_guardrails(segments: Sequence[str]) -> str:
    return "\n".join(segment for segment in segments if segment)


def _resolve_visible_text(
    final_text: str,
    capability_results: Sequence[CapabilityResult],
) -> str:
    if capability_results and any(
        result.requires_response_synthesis for result in capability_results
    ):
        if final_text:
            return final_text

    summaries = [
        summary for result in capability_results if (summary := result.visible_summary)
    ]
    if summaries:
        return "\n".join(summaries)

    if not capability_results:
        return final_text

    return ""


def _resolve_domain_visible_text(
    domain_results: Sequence[DomainExecutionResult],
) -> str:
    for result in reversed(domain_results):
        for operation in result.operations:
            facts = operation.facts
            for key in ("visible_summary", "summary", "message"):
                value = facts.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _check_durable_write_contract(
    capability_results: Sequence[CapabilityResult],
) -> RuntimeErrorDisposition | None:
    for result in capability_results:
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
    raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")


def _message_source(agent_input: AgentInput, run_context: AgentRunContext) -> str:
    value = run_context.runtime_metadata.get("message_source")
    if isinstance(value, str) and value:
        return value
    return agent_input.input_type


def _check_unconfirmed_durable_write_promise(
    *,
    agent_input: AgentInput,
    final_text: str,
    capability_results: Sequence[CapabilityResult],
    domain_results: Sequence[DomainExecutionResult] = (),
) -> RuntimeErrorDisposition | None:
    if agent_input.input_type != "user.turn" or not final_text:
        return None
    if any(result.ok and result.durable_write for result in capability_results):
        return None
    if any(
        operation.ok and operation.effect == "write"
        for result in domain_results
        for operation in result.operations
    ):
        return None
    matched = [
        pattern
        for pattern in _UNCONFIRMED_DURABLE_WRITE_PATTERNS
        if pattern.search(final_text)
    ]
    if not matched:
        return None
    has_question = "?" in final_text or "\uff1f" in final_text or "\u5417" in final_text
    if has_question:
        direct_promise_patterns = (
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[0],
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[2],
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[3],
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[4],
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[5],
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[6],
            _UNCONFIRMED_DURABLE_WRITE_PATTERNS[7],
        )
        if not any(pattern.search(final_text) for pattern in direct_promise_patterns):
            return None
    return RuntimeErrorDisposition(
        code="unconfirmed_durable_write_promise",
        retryable=False,
        metadata={"input_type": agent_input.input_type},
    )


async def _run_capability_port(
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


def _exception_result(
    capability_results: Sequence[CapabilityResult] = (),
    domain_results: Sequence[DomainExecutionResult] = (),
) -> AgentRunResult:
    logger.exception("Agent runtime failed closed")
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        domain_results=tuple(domain_results),
        capability_results=tuple(capability_results),
        metrics={
            "capability_result_count": len(capability_results),
            "domain_result_count": len(domain_results),
        },
        trace={"runtime": "agent", "status": "exception"},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=RuntimeErrorDisposition(
            code="agent_runtime_exception",
            retryable=True,
        ),
    )


def _unknown_tool_result(
    exc: UnknownToolError,
    capability_results: Sequence[CapabilityResult] = (),
    domain_results: Sequence[DomainExecutionResult] = (),
) -> AgentRunResult:
    logger.error("Agent runtime received unknown tool name: %s", exc)
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        domain_results=tuple(domain_results),
        capability_results=tuple(capability_results),
        metrics={
            "capability_result_count": len(capability_results),
            "domain_result_count": len(domain_results),
        },
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
    capability_results: Sequence[CapabilityResult] = (),
    domain_results: Sequence[DomainExecutionResult] = (),
) -> AgentRunResult:
    logger.error("Agent runtime timed out: timeout=%.1fs", timeout_seconds)
    captured_capability_results = tuple(capability_results)
    captured_domain_results = tuple(domain_results)
    durable_write_error = _check_durable_write_contract(captured_capability_results)
    timeout_error = RuntimeErrorDisposition(
        code="agent_runtime_timeout",
        retryable=True,
        metadata={"timeout_seconds": timeout_seconds},
    )
    visible_text = _resolve_visible_text("", captured_capability_results)
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
            domain_results=captured_domain_results,
            capability_results=captured_capability_results,
            metrics={
                "capability_result_count": len(captured_capability_results),
                "domain_result_count": len(captured_domain_results),
            },
            trace={"runtime": "agent", "status": "timeout_with_visible_summary"},
            output_disposition=OutputDisposition(status="ok"),
            error_disposition=timeout_error,
        )

    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        domain_results=captured_domain_results,
        capability_results=captured_capability_results,
        metrics={
            "capability_result_count": len(captured_capability_results),
            "domain_result_count": len(captured_domain_results),
        },
        trace={"runtime": "agent", "status": "timeout"},
        output_disposition=OutputDisposition(status="empty"),
        error_disposition=durable_write_error or timeout_error,
    )


async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    from agent.agno_agent.runtime.execution_agents import run_scheduling_domain

    capability_results: list[CapabilityResult] = []
    domain_results: list[DomainExecutionResult] = []
    try:
        if agent_input.input_type not in _SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")

        input_message = _input_message(agent_input)
        preloaded_scheduling_domain_result: dict[str, Any] | None = None
        preselected_scheduling_intent = _infer_scheduling_intent_from_agent_input(
            input_message,
            agent_input,
        )
        if preselected_scheduling_intent:
            preloaded_scheduling_domain_result = await run_scheduling_domain(
                input_message=input_message,
                intent=preselected_scheduling_intent,
                run_context=run_context,
                domain_results=domain_results,
            )
        create_agent_kwargs: dict[str, Any] = {
            "run_context": run_context,
            "agent_input": agent_input,
            "input_message": input_message,
            "capability_results": capability_results,
            "domain_results": domain_results,
            "preloaded_scheduling_domain_result": preloaded_scheduling_domain_result,
        }
        if preselected_scheduling_intent is not None:
            create_agent_kwargs["preselected_scheduling_intent"] = preselected_scheduling_intent
        create_agent_signature = inspect.signature(_create_interaction_agent)
        accepts_arbitrary_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in create_agent_signature.parameters.values()
        )
        if not accepts_arbitrary_kwargs:
            create_agent_kwargs = {
                key: value
                for key, value in create_agent_kwargs.items()
                if key in create_agent_signature.parameters
            }
        agent = _create_interaction_agent(**create_agent_kwargs)
        timeout_seconds = _agent_runtime_timeout_seconds()
        try:
            run_output = await asyncio.wait_for(
                agent.arun(
                    input=input_message,
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
                capability_results=capability_results,
                domain_results=domain_results,
            )
        final_text = _string_content(getattr(run_output, "content", None))
        if not final_text:
            final_text = _latest_assistant_text(run_output)
        if preselected_scheduling_intent:
            domain_visible_text = _resolve_domain_visible_text(domain_results)
            if domain_visible_text:
                final_text = domain_visible_text
        final_text_segments = _parse_visible_text_segments(final_text)
        unconfirmed_promise_error = _check_unconfirmed_durable_write_promise(
            agent_input=agent_input,
            final_text=_visible_text_for_guardrails(final_text_segments),
            capability_results=capability_results,
            domain_results=domain_results,
        )

        captured_capability_results = tuple(capability_results)
        captured_domain_results = tuple(domain_results)
        durable_write_error = _check_durable_write_contract(captured_capability_results)
        runtime_contract_error = durable_write_error or unconfirmed_promise_error
        visible_text_segments = final_text_segments
        if not final_text:
            fallback_text = _resolve_visible_text("", captured_capability_results)
            if not fallback_text:
                fallback_text = _resolve_domain_visible_text(captured_domain_results)
            visible_text_segments = (fallback_text,) if fallback_text else ()
        if runtime_contract_error is not None:
            visible_text_segments = ()
        visible_messages = tuple(
            VisibleMessage(message_type="text", content=segment)
            for segment in visible_text_segments
        )

        if visible_messages and runtime_contract_error is None:
            return AgentRunResult(
                visible_messages=visible_messages,
                post_analyze_input={
                    "input_message": input_message,
                    "message_source": _message_source(agent_input, run_context),
                },
                domain_results=captured_domain_results,
                capability_results=captured_capability_results,
                metrics={
                    "capability_result_count": len(captured_capability_results),
                    "domain_result_count": len(captured_domain_results),
                },
                trace={"runtime": "agent"},
                output_disposition=OutputDisposition(status="ok"),
            )

        return AgentRunResult(
            visible_messages=visible_messages,
            post_analyze_input=None,
            domain_results=captured_domain_results,
            capability_results=captured_capability_results,
            metrics={
                "capability_result_count": len(captured_capability_results),
                "domain_result_count": len(captured_domain_results),
            },
            trace={"runtime": "agent", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=runtime_contract_error,
        )
    except UnknownToolError as exc:
        return _unknown_tool_result(exc, capability_results, domain_results)
    except Exception:
        return _exception_result(capability_results, domain_results)
