from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.diagnostic_patterns import check_prohibited_claims
from agent.agno_agent.runtime.domain_results import (
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
    ReplyFactRequirement,
)
from agent.agno_agent.runtime.errors import UnknownToolError
from agent.agno_agent.runtime.focus import (
    focus_from_agent_focus_binding,
    focus_from_session_state,
    focus_to_session_state,
)
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.semantic_interpreter import SemanticIntentResult
from agent.agno_agent.runtime.semantic_interpreter import (
    create_semantic_intent_client as _create_semantic_intent_client,
)
from agent.agno_agent.runtime.semantic_interpreter import interpret_semantic_intent
from agent.agno_agent.runtime.session import get_agent_session_db
from agent.agno_agent.runtime.trace import (
    TraceOutput,
    build_agent_turn_trace,
    emit_agent_turn_trace_jsonl,
    resolve_agent_turn_trace_config,
    trace_evidence_path,
)

logger = logging.getLogger(__name__)

# Spec A diagnostic: surface agno's own logger output (LLM call / tool call /
# session activity) so a silent hang is no longer silent. Override only if the
# upstream logger is at WARNING+ (production default).
_agno_logger = logging.getLogger("agno")
if _agno_logger.level == logging.NOTSET or _agno_logger.level >= logging.WARNING:
    _agno_logger.setLevel(logging.INFO)

_SUPPORTED_INPUT_TYPES = {"user.turn", "reminder.fired"}
_DEFAULT_AGENT_RUNTIME_TIMEOUT_SECONDS = 100.0
_MAX_VISIBLE_TEXT_SEGMENTS = 3
_SCHEDULING_INTENT_NAMES = {
    "create_shared_reminder",
    "cancel_shared_reminder",
    "create_friendship_by_user_link_code",
    "list_friends",
    "remove_friendship",
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "list_friend_calendar_facts",
    "list_shared_reminders",
}
_SCHEDULING_READ_ONLY_INTENTS = {
    "get_user_link",
    "list_friends",
    "list_friend_calendar_facts",
    "list_shared_reminders",
}
_SCHEDULING_INTENT_SELECTOR_KEYS = {
    "intent",
    "intent_name",
    "tool",
    "tool_name",
    "name",
    "operation",
    "action",
}
_SCHEDULING_CREATE_SHARED_REMINDER_ARG_KEYS = {
    "receiver_account_id",
    "receiver_name",
    "friend_account_id",
    "friendship_id",
    "title",
    "fire_at",
    "duration_minutes",
    "timezone",
    "idempotency_key",
}
_SCHEDULING_FORCED_ARG_KEYS = {
    "user_link_code",
    "friend_name",
    "requester_name",
    "target_name",
    "message",
    "shared_reminder_id",
    "focus_token",
    "focus_handle",
    "title",
    "friendship_id",
    "receiver_name",
    "receiver_account_id",
    "target_account_id",
    "from_date",
    "to_date",
    "timezone",
    "status",
    "idempotency_key",
}
_RETIRED_ACCOUNT_CONTROL_RE = re.compile(
    r"(屏蔽|拉黑|解除屏蔽|取消屏蔽|\b(?:unblock|block)\b)",
    re.IGNORECASE,
)
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
    # "Now you're friends" claims: "你们现在是好友/好朋友啦", "now you are friends".
    re.compile(
        r"(你们现在|现在你们|now you(?:'re| are))" r".{0,12}(是好(友|朋友)|friends?)",
        re.IGNORECASE,
    ),
)
_STALE_SHARED_REMINDER_INVITE_CLAIM_PATTERNS = (
    re.compile(r"(邀请|邀约|共享提醒请求).{0,24}(发给|发过去|发出|发送|提交)"),
    re.compile(r"(发给|发过去|发出|发送|提交).{0,24}(邀请|邀约|共享提醒请求)"),
    re.compile(r"(等|等待).{0,16}(确认|接受|同意)"),
    re.compile(
        r"\b(waiting|wait).{0,40}\b(confirm|accept)",
        re.IGNORECASE,
    ),
)
_VISIBLE_IDENTIFIER_LEAK_PATTERNS = (
    re.compile(r"ck_[a-zA-Z0-9_]{8,}"),
    re.compile(r"acct_[a-zA-Z0-9_]{8,}"),
)
_CAPABILITY_BOUNDARY_MARKERS = (
    "不能",
    "无法",
    "没法",
    "没有办法",
    "没办法",
    "帮不了",
    "做不了",
    "暂时不",
    "暂时没有",
    "还不能",
    "只能",
)
_REMINDER_OFFER_MARKERS = (
    "可以帮你",
    "可以告诉我",
    "随时告诉我",
    "需要我",
    "要不要",
    "要不要我",
    "帮你设吗",
    "我能做",
    "如果",
    "想要提醒",
    "只能帮你",
)
# OUTPUT SAFETY NET (not a semantic classifier): catches LLM final-text
# claims of a completed reminder write when no tool write actually
# succeeded. Survives the LLM-only intent migration because its purpose
# is to compensate for LLM unreliability, not to classify user intent.
_COMPLETED_WRITE_CLAIM_PATTERNS = (
    re.compile(r"(已经|已).{0,24}(设置|设好|创建|建了).{0,24}(提醒|通知)"),
    re.compile(r"(设置好|设好|创建好|建好).{0,8}(了|啦)"),
    re.compile(r"我再帮你.{0,8}(设一下|设置一下|安排一下).{0,80}(提醒|通知)"),
    re.compile(r"给你.{0,8}(设个|设置个|安排个).{0,16}\d+\s*分钟后.{0,8}(提醒|通知)"),
    re.compile(
        r"(好嘞|好的|收到).{0,80}(提醒你|通知你|叫你).{0,80}(告诉我|补充).{0,32}(设好|设置好|安排好)"
    ),
)


class _SchedulingIntentError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.detail = dict(detail or {})


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


def _has_product_notification_hint(agent_input: AgentInput) -> bool:
    return _product_notification_metadata(agent_input) is not None


def _resolve_scheduling_focus(
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> Any:
    session_state = getattr(run_context, "session_state", {})
    existing_focus = (
        session_state.get("focus") if isinstance(session_state, Mapping) else None
    )
    if isinstance(existing_focus, Mapping):
        focus = focus_from_session_state(
            existing_focus,
            current_time=run_context.current_time,
        )
        if _focus_has_actionable_candidates(focus):
            return focus
    if not _has_product_notification_hint(agent_input):
        return focus_from_agent_focus_binding(
            None, current_time=run_context.current_time
        )
    from agent.agno_agent.capabilities.scheduling import SchedulingContractClient

    payload = {
        "customer_id": run_context.user.id,
        "conversation_id": run_context.conversation.id,
        "platform": run_context.platform,
        "timezone": run_context.user.timezone or "UTC",
    }
    try:
        raw = SchedulingContractClient().resolve_agent_focus(payload)
    except Exception:
        logger.warning("scheduling_focus_resolve_failed", exc_info=True)
        return focus_from_agent_focus_binding(
            None, current_time=run_context.current_time
        )
    if raw.get("ok") is not True:
        logger.warning("scheduling_focus_resolve_rejected: error=%s", raw.get("error"))
        return focus_from_agent_focus_binding(
            None, current_time=run_context.current_time
        )
    data = raw.get("data")
    return focus_from_agent_focus_binding(data, current_time=run_context.current_time)


def _is_retired_account_control_turn(input_message: str) -> bool:
    return bool(
        _RETIRED_ACCOUNT_CONTROL_RE.search(_latest_user_turn_text(input_message))
    )


def _normalize_scheduling_intent(raw_intent: Any, input_message: str) -> str:
    del input_message
    if isinstance(raw_intent, str):
        candidate = raw_intent.strip()
        if not candidate:
            return ""
        prefix = candidate.split(":", 1)[0].strip()
        if prefix in _SCHEDULING_INTENT_NAMES:
            return prefix
        return candidate

    if isinstance(raw_intent, Mapping):
        for key, value in raw_intent.items():
            normalized_key = key
            if (
                isinstance(normalized_key, str)
                and normalized_key in _SCHEDULING_INTENT_NAMES
            ):
                if isinstance(value, Mapping) and value:
                    return (
                        f"{normalized_key}: "
                        f"{json.dumps(_normalize_scheduling_intent_args(normalized_key, value), ensure_ascii=False)}"
                    )
                return normalized_key

        for key in _SCHEDULING_INTENT_SELECTOR_KEYS:
            value = raw_intent.get(key)
            if isinstance(value, str) and value.strip():
                normalized = _normalize_scheduling_intent(value, "")
                if normalized:
                    if normalized in _SCHEDULING_INTENT_NAMES:
                        args = {
                            arg_key: arg_value
                            for arg_key, arg_value in raw_intent.items()
                            if arg_key not in _SCHEDULING_INTENT_SELECTOR_KEYS
                        }
                        if args:
                            return (
                                f"{normalized}: "
                                f"{json.dumps(_normalize_scheduling_intent_args(normalized, args), ensure_ascii=False)}"
                            )
                    return normalized
            if isinstance(value, Mapping):
                normalized = _normalize_scheduling_intent(value, "")
                normalized_name = normalized.split(":", 1)[0].strip()
                if normalized_name in _SCHEDULING_INTENT_NAMES:
                    if ":" in normalized:
                        return normalized
                    args = {
                        arg_key: arg_value
                        for arg_key, arg_value in value.items()
                        if arg_key not in _SCHEDULING_INTENT_SELECTOR_KEYS
                    }
                    if args:
                        return (
                            f"{normalized}: "
                            f"{json.dumps(_normalize_scheduling_intent_args(normalized, args), ensure_ascii=False)}"
                        )
                    return normalized
    raise _SchedulingIntentError(
        "invalid_scheduling_intent",
        "scheduling intent could not be resolved",
        detail={"intent": _jsonable(raw_intent)},
    )


def _normalize_scheduling_intent_args(
    tool_name: str,
    args: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = dict(args)
    if "message" not in normalized and "note" in normalized:
        normalized["message"] = normalized.pop("note")
    if "requester_name" not in normalized:
        for alias in ("inviter_name", "inviter", "requester"):
            if alias in normalized and normalized[alias]:
                normalized["requester_name"] = normalized[alias]
                break
    if "title" not in normalized and "reminder_title" in normalized:
        normalized["title"] = normalized.pop("reminder_title")
    else:
        normalized.pop("reminder_title", None)
    if tool_name == "create_shared_reminder":
        invalid_keys = sorted(
            key
            for key in normalized
            if key not in _SCHEDULING_CREATE_SHARED_REMINDER_ARG_KEYS
        )
        if invalid_keys:
            raise _SchedulingIntentError(
                "invalid_scheduling_args",
                "create_shared_reminder only accepts canonical scheduling args",
                detail={"tool_name": tool_name, "invalid_keys": invalid_keys},
            )
        compact = {
            key: value
            for key, value in normalized.items()
            if value is not None and value != ""
        }
        has_counterparty = any(
            str(compact.get(key) or "").strip()
            for key in (
                "receiver_account_id",
                "receiver_name",
                "friend_account_id",
                "friendship_id",
            )
        )
        has_title = bool(str(compact.get("title") or "").strip())
        has_fire_at = bool(str(compact.get("fire_at") or "").strip())
        if not (has_counterparty and has_title and has_fire_at):
            raise _SchedulingIntentError(
                "invalid_scheduling_args",
                "create_shared_reminder requires a canonical counterparty, title, and fire_at",
                detail={
                    "tool_name": tool_name,
                    "missing": [
                        key
                        for key, present in (
                            ("counterparty", has_counterparty),
                            ("title", has_title),
                            ("fire_at", has_fire_at),
                        )
                        if not present
                    ],
                },
            )
        return compact
    if tool_name == "cancel_shared_reminder":
        allowed_cancel_keys = {
            "shared_reminder_id",
            "friend_name",
            "title",
            "friendship_id",
            "timezone",
            "focus_token",
            "focus_handle",
            "idempotency_key",
        }
        invalid_keys = sorted(
            key for key in normalized if key not in allowed_cancel_keys
        )
        if invalid_keys:
            raise _SchedulingIntentError(
                "invalid_scheduling_args",
                "cancel_shared_reminder only accepts canonical scheduling args",
                detail={"tool_name": tool_name, "invalid_keys": invalid_keys},
            )
        return {
            key: value
            for key, value in normalized.items()
            if value is not None and value != ""
        }
    allowed = set(_SCHEDULING_FORCED_ARG_KEYS)
    return {
        key: value
        for key, value in normalized.items()
        if key in allowed and value is not None and value != ""
    }


def _split_scheduling_intent_args(
    normalized_intent: str,
) -> tuple[str, dict[str, Any] | None]:
    intent, separator, raw_args = normalized_intent.partition(":")
    tool_name = intent.strip()
    if not separator or tool_name not in _SCHEDULING_INTENT_NAMES:
        return normalized_intent, None
    try:
        args = json.loads(raw_args.strip())
    except json.JSONDecodeError:
        return normalized_intent, None
    if not isinstance(args, Mapping):
        return normalized_intent, None
    return tool_name, _normalize_scheduling_intent_args(tool_name, args)


def _scheduling_failure_result(
    *,
    code: str,
    message: str,
    safety_boundary: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> DomainExecutionResult:
    error = DomainError(
        code=code,
        message=message,
        retryable=False,
        detail=detail or {},
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(),
        missing_fields=(),
        safety_boundary=safety_boundary,
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("appointment_confirmed",),
            allow_rephrase=True,
        ),
        error=error,
    )


def _scheduling_call_cache_key(
    intent: str,
    forced_args: Mapping[str, Any] | None,
) -> tuple[str, str]:
    args_json = json.dumps(
        _jsonable(dict(forced_args or {})),
        ensure_ascii=False,
        sort_keys=True,
    )
    return intent, args_json


def _scheduling_result_has_successful_write(
    result: Mapping[str, Any],
    *,
    intent: str,
) -> bool:
    operations = result.get("operations")
    if isinstance(operations, Sequence) and not isinstance(
        operations,
        (str, bytes, bytearray),
    ):
        for operation in operations:
            if not isinstance(operation, Mapping):
                continue
            if operation.get("ok") and operation.get("effect") == "write":
                return True
        return False
    return (
        result.get("outcome") == "executed"
        and intent not in _SCHEDULING_READ_ONLY_INTENTS
    )


def _semantic_scheduling_intent_and_args(
    semantic_result: SemanticIntentResult,
    focus: Any,
) -> tuple[str | None, dict[str, Any]]:
    del focus
    if semantic_result.intent in {
        "ambiguous",
        "ask_detail",
        "request_change",
        "unrelated",
    }:
        return None, {}
    if semantic_result.intent in _SCHEDULING_INTENT_NAMES:
        if (
            semantic_result.intent == "create_shared_reminder"
            and not semantic_result.args
        ):
            return semantic_result.intent, {}
        return semantic_result.intent, _normalize_scheduling_intent_args(
            semantic_result.intent,
            semantic_result.args,
        )
    return None, {}


def _focus_action_value(action: Any, field: str) -> Any:
    if isinstance(action, Mapping):
        return action.get(field)
    return getattr(action, field, None)


def _focus_current_action(focus: Any) -> Any | None:
    if isinstance(focus, Mapping):
        current = focus.get("current")
        if current is not None:
            return current
        candidates = focus.get("candidates")
    else:
        current = getattr(focus, "current", None)
        if current is not None:
            return current
        candidates = getattr(focus, "candidates", None)
    if isinstance(candidates, Sequence) and candidates:
        return candidates[0]
    return None


def _focus_has_actionable_candidates(focus: Any) -> bool:
    return _focus_current_action(focus) is not None


def _focused_semantic_failure_result(
    focus: Any,
    semantic_result: SemanticIntentResult,
    *,
    run_context: AgentRunContext | None = None,
) -> DomainExecutionResult:
    if getattr(focus, "ambiguity", None) == "multi_candidate":
        return _multi_candidate_clarification_result(
            focus, semantic_result, run_context=run_context
        )
    return _single_candidate_focus_failure_result(focus, semantic_result)


def _single_candidate_focus_failure_result(
    focus: Any,
    semantic_result: SemanticIntentResult,
) -> DomainExecutionResult:
    action = _focus_current_action(focus)
    action_id = str(_focus_action_value(action, "action_id") or "")
    kind = str(_focus_action_value(action, "kind") or "product_action")
    summary = "我没法可靠判断你要同意还是拒绝这条请求，请再明确回复同意或拒绝。"
    error = DomainError(
        code="semantic_focus_ambiguous",
        message=semantic_result.clarification_reason or summary,
        retryable=True,
        detail={
            "semantic_intent": semantic_result.intent,
            "semantic_confidence": semantic_result.confidence,
            "action_id": action_id,
            "kind": kind,
        },
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="classify_product_action_reply",
                ok=False,
                effect="none",
                entity_type=kind,
                entity_id=action_id or None,
                facts={"visible_summary": summary},
                error=error,
            ),
        ),
        missing_fields=(),
        safety_boundary="semantic_focus_ambiguous",
        reply_contract=ReplyContract(
            intent="ask_clarification",
            required_facts=(),
            required_questions=("同意还是拒绝这条请求？",),
            prohibited_claims=(),
            allow_rephrase=True,
        ),
        error=error,
    )


def _multi_candidate_clarification_result(
    focus: Any,
    semantic_result: SemanticIntentResult,
    *,
    run_context: AgentRunContext | None = None,
) -> DomainExecutionResult:
    candidates = tuple(getattr(focus, "candidates", ()) or ())
    viewer_timezone = _viewer_timezone_from_run_context(run_context)
    lines = ["你有多条等你确认的邀请，请选一条："]
    facts: list[ReplyFactRequirement] = []
    for index, candidate in enumerate(candidates):
        delivered_at = getattr(candidate, "delivered_at", None)
        summary = getattr(candidate, "summary_for_llm", "") or ""
        delivered_label = _format_delivered_at_for_user(delivered_at, viewer_timezone)
        lines.append(f"{index + 1}. {delivered_label} {summary}".rstrip())
        facts.append(ReplyFactRequirement(path=f"candidates[{index}].delivered_at"))
        facts.append(ReplyFactRequirement(path=f"candidates[{index}].summary_for_llm"))
    summary_text = "\n".join(lines)
    error = DomainError(
        code="semantic_focus_multi_candidate",
        message=semantic_result.clarification_reason or summary_text,
        retryable=True,
        detail={
            "semantic_intent": semantic_result.intent,
            "semantic_confidence": semantic_result.confidence,
            "candidate_count": len(candidates),
        },
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="classify_product_action_reply",
                ok=False,
                effect="none",
                entity_type="product_action",
                entity_id=None,
                facts={"visible_summary": summary_text},
                error=error,
            ),
        ),
        missing_fields=(),
        safety_boundary="semantic_focus_multi_candidate",
        reply_contract=ReplyContract(
            intent="ask_clarification",
            required_facts=tuple(facts),
            required_questions=("你要对哪一条邀请操作？",),
            prohibited_claims=(),
            allow_rephrase=True,
        ),
        error=error,
    )


def _format_delivered_at_for_user(value: Any, viewer_timezone: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    tzinfo = _resolve_viewer_tzinfo(viewer_timezone)
    if value.tzinfo is None or tzinfo is None:
        local = value
    else:
        local = value.astimezone(tzinfo)
    return local.strftime("%H:%M")


def _viewer_timezone_from_run_context(run_context: AgentRunContext | None) -> str:
    if run_context is None:
        return ""
    user = getattr(run_context, "user", None)
    if user is None:
        return ""
    return str(getattr(user, "timezone", "") or "")


def _resolve_viewer_tzinfo(viewer_timezone: Any):
    if isinstance(viewer_timezone, str) and viewer_timezone.strip():
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(viewer_timezone.strip())
        except Exception:
            return None
    return None


def _should_fail_closed_focused_semantic(
    focus: Any,
    semantic_result: SemanticIntentResult,
) -> bool:
    return _focus_has_actionable_candidates(focus) and semantic_result.intent in {
        "ambiguous",
        "ask_detail",
        "request_change",
    }


def _current_utterance_for_semantic_interpreter(
    agent_input: AgentInput,
    input_message: str,
) -> str:
    payload = agent_input.payload
    metadata = getattr(payload, "metadata", None)
    if isinstance(metadata, Mapping):
        raw = metadata.get("product_notification_input_text")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return _latest_user_turn_text(input_message)


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
        scheduling_domain_results: dict[tuple[str, str], dict[str, Any]] = {}
        scheduling_domain_state: dict[str, bool] = {
            "has_successful_write": bool(
                preloaded_scheduling_domain_result
                and _scheduling_result_has_successful_write(
                    preloaded_scheduling_domain_result,
                    intent=preselected_scheduling_intent or "",
                )
            )
        }

        async def reminder_domain(**_model_supplied_args: Any) -> dict[str, Any]:
            """Use for explicit personal reminder create, update, cancel, complete, or list requests. Do not use for friend appointment invitations."""
            async with reminder_domain_lock:
                if "result" in reminder_domain_result:
                    return {
                        "domain": "reminder",
                        "outcome": "failed",
                        "operations": [],
                        "missing_fields": [],
                        "safety_boundary": "duplicate_call",
                        "reply_contract": {
                            "intent": "report_failure",
                            "required_facts": [],
                            "required_questions": [],
                            "prohibited_claims": ["reminder_created"],
                            "allow_rephrase": True,
                        },
                        "error": {
                            "code": "duplicate_call",
                            "message": (
                                "reminder_domain may only be called once per turn; "
                                "answer from the first result"
                            ),
                            "retryable": False,
                            "detail": {},
                        },
                    }
                result = await run_reminder_domain(
                    input_message=input_message,
                    run_context=run_context,
                    domain_results=domain_results,
                )
                reminder_domain_result["result"] = result
                return result

        async def scheduling_domain(
            intent: Any = None,
            friend_name: str = "",
            target_account_id: str = "",
            from_date: str = "",
            to_date: str = "",
            timezone: str = "",
        ) -> dict[str, Any]:
            """Use for explicit user-link, friendship, friend availability, or shared-reminder actions. For friend availability, use intent=list_friend_calendar_facts and pass friend_name, from_date, to_date, and timezone. For friend invites like "帮我约/邀请 <friend>" with a concrete appointment time, call create_shared_reminder using canonical fields receiver_name, title, fire_at, timezone, and duration_minutes."""
            async with scheduling_domain_lock:
                if preloaded_scheduling_domain_result is not None:
                    result = _scheduling_failure_result(
                        code="preselected_scheduling_result",
                        message=(
                            "scheduling_domain already has a preselected result for this turn"
                        ),
                        safety_boundary="preselected_scheduling_result",
                        detail={"intent": _jsonable(intent)},
                    )
                    domain_results.append(result)
                    return result.to_dict()
                try:
                    normalized_intent = _normalize_scheduling_intent(
                        intent,
                        input_message,
                    )
                    (
                        scheduling_intent,
                        forced_scheduling_args,
                    ) = _split_scheduling_intent_args(normalized_intent)
                    direct_raw_args = {
                        key: value
                        for key, value in {
                            "friend_name": friend_name,
                            "target_account_id": target_account_id,
                            "from_date": from_date,
                            "to_date": to_date,
                            "timezone": timezone,
                        }.items()
                        if value is not None and value != ""
                    }
                    direct_args = (
                        _normalize_scheduling_intent_args(
                            scheduling_intent,
                            direct_raw_args,
                        )
                        if direct_raw_args
                        else {}
                    )
                    if direct_args:
                        forced_scheduling_args = {
                            **(forced_scheduling_args or {}),
                            **direct_args,
                        }
                except _SchedulingIntentError as error:
                    result = _scheduling_failure_result(
                        code=error.code,
                        message=str(error),
                        detail=error.detail,
                    )
                    domain_results.append(result)
                    return result.to_dict()
                call_key = _scheduling_call_cache_key(
                    scheduling_intent,
                    forced_scheduling_args,
                )
                if call_key in scheduling_domain_results:
                    return scheduling_domain_results[call_key]
                if scheduling_domain_state["has_successful_write"]:
                    result = _scheduling_failure_result(
                        code="multiple_scheduling_calls_after_write",
                        message=(
                            "a different scheduling call after a successful write is not allowed"
                        ),
                        safety_boundary="multiple_scheduling_calls_after_write",
                        detail={"intent": scheduling_intent},
                    )
                    domain_results.append(result)
                    return result.to_dict()
                run_scheduling_kwargs: dict[str, Any] = {
                    "input_message": input_message,
                    "intent": scheduling_intent,
                    "run_context": run_context,
                    "domain_results": domain_results,
                }
                if forced_scheduling_args is not None:
                    run_scheduling_kwargs["forced_args"] = forced_scheduling_args
                result = await run_scheduling_domain(**run_scheduling_kwargs)
                scheduling_domain_results[call_key] = result
                if _scheduling_result_has_successful_write(
                    result,
                    intent=scheduling_intent,
                ):
                    scheduling_domain_state["has_successful_write"] = True
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
_SERIALIZED_TOOL_CALL_OUTPUT_RE = re.compile(
    r"(<\s*(?:minimax:)?tool_call\b|</\s*(?:minimax:)?tool_call\s*>|"
    r"<\s*invoke\s+name\s*=|<\s*parameter\s+name\s*=\s*[\"']_model_supplied_args[\"'])",
    re.IGNORECASE,
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


def _check_serialized_tool_call_output(final_text: str) -> RuntimeErrorDisposition | None:
    if not final_text or _SERIALIZED_TOOL_CALL_OUTPUT_RE.search(final_text) is None:
        return None
    return RuntimeErrorDisposition(
        code="serialized_tool_call_output",
        retryable=False,
        metadata={"reason": "model emitted tool-call markup as visible text"},
    )


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
    *,
    include_failed_generic: bool = False,
) -> str:
    for result in reversed(domain_results):
        if result.outcome != "executed":
            continue
        summaries: list[str] = []
        for operation in result.operations:
            if not operation.ok:
                continue
            facts = operation.facts
            for key in ("visible_summary", "summary", "message"):
                value = facts.get(key)
                if isinstance(value, str) and value.strip():
                    summaries.append(value.strip())
                    break
        if summaries:
            return "\n".join(summaries)
    for result in reversed(domain_results):
        if result.domain != "scheduling" or result.outcome != "failed":
            continue
        for operation in result.operations:
            facts = operation.facts
            for key in ("visible_summary", "summary", "message"):
                value = facts.get(key)
                if _is_safe_scheduling_failure_summary(value):
                    return str(value).strip()
        if include_failed_generic:
            return "日程操作暂时无法完成。"
    for result in reversed(domain_results):
        if (
            result.domain != "reminder"
            or result.outcome != "failed"
            or result.safety_boundary != "explicit_past"
        ):
            continue
        for operation in result.operations:
            facts = operation.facts
            for key in ("visible_summary", "summary", "message"):
                value = facts.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        error = result.error
        if error is not None and error.message.strip():
            return error.message.strip()
    return ""


def _authoritative_domain_visible_text(
    domain_results: Sequence[DomainExecutionResult],
) -> str:
    for result in reversed(domain_results):
        if (
            result.domain != "reminder"
            or result.outcome != "rejected"
            or not result.safety_boundary
        ):
            continue
        for operation in result.operations:
            if operation.ok or operation.effect != "none":
                continue
            facts = operation.facts
            for key in ("visible_summary", "summary", "message"):
                value = facts.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    for result in reversed(domain_results):
        if result.domain != "reminder" or result.outcome != "executed":
            continue
        for operation in result.operations:
            if (
                operation.action != "list"
                or not operation.ok
                or operation.effect != "read"
            ):
                continue
            facts = operation.facts
            for key in ("visible_summary", "summary", "message"):
                value = facts.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _is_safe_scheduling_failure_summary(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if value.strip() == "日程操作暂时无法完成。":
        return False
    lowered = value.casefold()
    unsafe_markers = (
        "traceback",
        "stack trace",
        "exception",
        "runtimeerror",
        "valueerror",
        "typeerror",
        "mongodb",
        "postgres",
        "prisma",
        "sql",
    )
    return not any(marker in lowered for marker in unsafe_markers)


_DOMAIN_VISIBLE_TEXT_KEYS = ("visible_summary", "summary", "message")


def _operation_has_visible_text(operation: DomainOperationResult) -> bool:
    for key in _DOMAIN_VISIBLE_TEXT_KEYS:
        value = operation.facts.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _latest_user_turn_text(input_message: str) -> str:
    parts = re.split(r"（[^）]*发来了文本消息）", input_message)
    if len(parts) > 1:
        return parts[-1].strip()
    return input_message.strip()


def _check_durable_write_contract(
    capability_results: Sequence[CapabilityResult],
    domain_results: Sequence[DomainExecutionResult] = (),
) -> RuntimeErrorDisposition | None:
    for result in capability_results:
        if result.ok and result.durable_write and not result.visible_summary:
            return RuntimeErrorDisposition(
                code="durable_write_missing_visible_summary",
                retryable=False,
                metadata={"capability": result.name},
            )
    for result in domain_results:
        if result.domain != "scheduling":
            continue
        for operation in result.operations:
            if (
                operation.ok
                and operation.effect == "write"
                and not _operation_has_visible_text(operation)
            ):
                return RuntimeErrorDisposition(
                    code="durable_write_missing_visible_summary",
                    retryable=False,
                    metadata={
                        "domain": result.domain,
                        "action": operation.action,
                    },
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
    stale_shared_reminder_invite_claim = any(
        pattern.search(final_text)
        for pattern in _STALE_SHARED_REMINDER_INVITE_CLAIM_PATTERNS
    )
    if stale_shared_reminder_invite_claim:
        return RuntimeErrorDisposition(
            code="unconfirmed_durable_write_promise",
            retryable=False,
            metadata={"input_type": agent_input.input_type},
        )
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
        for pattern in (
            *_UNCONFIRMED_DURABLE_WRITE_PATTERNS,
            *_COMPLETED_WRITE_CLAIM_PATTERNS,
        )
        if pattern.search(final_text)
    ]
    if not matched:
        return None
    if _is_reminder_capability_offer_not_write_claim(final_text):
        return None
    has_question = "?" in final_text or "\uff1f" in final_text or "\u5417" in final_text
    if has_question:
        direct_promise_patterns = (
            *(
                pattern
                for index, pattern in enumerate(_UNCONFIRMED_DURABLE_WRITE_PATTERNS)
                if index != 1
            ),
            *_COMPLETED_WRITE_CLAIM_PATTERNS,
        )
        if not any(pattern.search(final_text) for pattern in direct_promise_patterns):
            return None
    return RuntimeErrorDisposition(
        code="unconfirmed_durable_write_promise",
        retryable=False,
        metadata={"input_type": agent_input.input_type},
    )


def _check_domain_reply_contract(
    *,
    final_text: str,
    domain_results: Sequence[DomainExecutionResult],
) -> RuntimeErrorDisposition | None:
    if not final_text:
        return None
    for result in domain_results:
        contract = replace(
            result.reply_contract,
            prohibited_claims=tuple(
                claim
                for claim in result.reply_contract.prohibited_claims
                if not _prohibited_claim_confirmed_by_write(
                    claim,
                    domain_results,
                )
            ),
        )
        violations = check_prohibited_claims(contract, final_text)
        if violations:
            return RuntimeErrorDisposition(
                code="domain_reply_contract_violation",
                retryable=False,
                metadata={
                    "domain": result.domain,
                    "violations": violations,
                },
            )
    return None


def _prohibited_claim_confirmed_by_write(
    claim: str,
    domain_results: Sequence[DomainExecutionResult],
) -> bool:
    if claim == "reminder_created":
        return any(
            result.domain == "reminder"
            and operation.ok
            and operation.effect == "write"
            and operation.action == "create"
            for result in domain_results
            for operation in result.operations
        )
    if claim == "appointment_confirmed":
        return any(
            result.domain == "scheduling"
            and operation.ok
            and operation.effect == "write"
            and operation.action == "create_shared_reminder"
            for result in domain_results
            for operation in result.operations
        )
    return False


def _has_successful_domain_write(
    domain_results: Sequence[DomainExecutionResult],
    *,
    action: str,
) -> bool:
    return any(
        result.domain == "scheduling"
        and operation.ok
        and operation.effect == "write"
        and operation.action == action
        for result in domain_results
        for operation in result.operations
    )


def _is_reminder_capability_offer_not_write_claim(final_text: str) -> bool:
    """Allow refusal text that offers reminder help without claiming a write.

    The durable-write guardrail should block claims like "已经帮你设置好了提醒"
    when no tool write succeeded. It should not block a capability boundary
    such as "我不能预约教练，只能帮你设置提醒，需要我提醒你吗？".
    """
    if not _contains_any(final_text, _CAPABILITY_BOUNDARY_MARKERS):
        return False
    if not _contains_any(final_text, _REMINDER_OFFER_MARKERS):
        return False
    if any(pattern.search(final_text) for pattern in _COMPLETED_WRITE_CLAIM_PATTERNS):
        return False
    return True


def _check_visible_identifier_leak(final_text: str) -> RuntimeErrorDisposition | None:
    if not final_text:
        return None
    if not any(
        pattern.search(final_text) for pattern in _VISIBLE_IDENTIFIER_LEAK_PATTERNS
    ):
        return None
    return RuntimeErrorDisposition(
        code="visible_identifier_leak",
        retryable=False,
        metadata={},
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
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    started_at: datetime,
    capability_results: Sequence[CapabilityResult] = (),
    domain_results: Sequence[DomainExecutionResult] = (),
) -> AgentRunResult:
    logger.exception("Agent runtime failed closed")
    output_disposition = OutputDisposition(status="empty")
    error_disposition = RuntimeErrorDisposition(
        code="agent_runtime_exception",
        retryable=True,
    )
    trace = _build_runtime_trace(
        agent_input=agent_input,
        run_context=run_context,
        input_message=input_message,
        started_at=started_at,
        status="exception",
        failure_stage="agent_run",
        timeout_seconds=None,
        preselected_scheduling_intent=None,
        forced_args_present=False,
        tool_names=_available_tool_names(agent_input, None),
        selected_tool_names=_selected_tool_names(domain_results, capability_results),
        capability_results=capability_results,
        domain_results=domain_results,
        output=TraceOutput(
            disposition_status=output_disposition.status,
            output_source="empty",
            visible_message_count=0,
            output_reference_count=0,
            post_analyze_requested=False,
            fallback_reason=None,
        ),
        output_disposition=output_disposition,
        error_disposition=error_disposition,
    )
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        domain_results=tuple(domain_results),
        capability_results=tuple(capability_results),
        metrics={
            "capability_result_count": len(capability_results),
            "domain_result_count": len(domain_results),
        },
        trace=trace,
        output_disposition=output_disposition,
        error_disposition=error_disposition,
    )


def _explicit_past_reminder_precheck(
    input_message: str,
    run_context: AgentRunContext,
) -> DomainExecutionResult | None:
    from agent.agno_agent.capabilities import reminder_intent

    current_user_text = reminder_intent._latest_user_turn_text(input_message)
    if not reminder_intent._REMINDER_VERB_PATTERN.search(current_user_text):
        return None
    if reminder_intent._single_relative_delay(current_user_text) is not None:
        return None
    if not reminder_intent._explicit_past_time_evidence(
        current_user_text,
        run_context,
    ):
        return None
    return reminder_intent._invalid_past_schedule_result()


def _retired_account_control_result() -> DomainExecutionResult:
    summary = "屏蔽/拉黑账号功能已停用，我不会改动你的好友关系。"
    error = DomainError(
        code="retired_account_control",
        message=summary,
        retryable=False,
        detail={},
    )
    operation = DomainOperationResult(
        action="account_control",
        ok=False,
        effect="none",
        entity_type="friendship",
        entity_id=None,
        facts={"visible_summary": summary},
        error=error,
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(operation,),
        missing_fields=(),
        safety_boundary="retired_account_control",
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=(
                "friendship_removed",
                "account_blocked",
                "account_unblocked",
            ),
            allow_rephrase=True,
        ),
        error=error,
    )


def _domain_visible_text_result(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    started_at: datetime,
    domain_result: DomainExecutionResult,
) -> AgentRunResult:
    domain_results = (domain_result,)
    visible_text = _resolve_domain_visible_text(domain_results)
    visible_messages = (
        (VisibleMessage(message_type="text", content=visible_text),)
        if visible_text
        else ()
    )
    output_disposition = OutputDisposition(status="ok" if visible_text else "empty")
    trace = _build_runtime_trace(
        agent_input=agent_input,
        run_context=run_context,
        input_message=input_message,
        started_at=started_at,
        status="ok" if visible_text else "empty_output",
        failure_stage=None,
        timeout_seconds=None,
        preselected_scheduling_intent=None,
        forced_args_present=False,
        tool_names=_available_tool_names(agent_input, None),
        selected_tool_names=_selected_tool_names(domain_results, ()),
        capability_results=(),
        domain_results=domain_results,
        output=TraceOutput(
            disposition_status=output_disposition.status,
            output_source="domain_summary" if visible_text else "empty",
            visible_message_count=len(visible_messages),
            output_reference_count=0,
            post_analyze_requested=bool(visible_text),
            fallback_reason=None,
        ),
        output_disposition=output_disposition,
        error_disposition=None,
        content_evidence=(
            {
                "input_text": input_message,
                "visible_output_text": [
                    message.content for message in visible_messages
                ],
            }
            if visible_messages
            else None
        ),
    )
    return AgentRunResult(
        visible_messages=visible_messages,
        post_analyze_input=(
            {
                "input_message": input_message,
                "message_source": _message_source(agent_input, run_context),
            }
            if visible_messages
            else None
        ),
        domain_results=domain_results,
        capability_results=(),
        metrics={"capability_result_count": 0, "domain_result_count": 1},
        trace=trace,
        output_disposition=output_disposition,
    )


def _unknown_tool_result(
    exc: UnknownToolError,
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    started_at: datetime,
    capability_results: Sequence[CapabilityResult] = (),
    domain_results: Sequence[DomainExecutionResult] = (),
) -> AgentRunResult:
    logger.error("Agent runtime received unknown tool name: %s", exc)
    output_disposition = OutputDisposition(status="empty")
    error_disposition = RuntimeErrorDisposition(
        code="agent_runtime_unknown_tool",
        retryable=False,
    )
    trace = _build_runtime_trace(
        agent_input=agent_input,
        run_context=run_context,
        input_message=input_message,
        started_at=started_at,
        status="unknown_tool",
        failure_stage="tool_selection",
        timeout_seconds=None,
        preselected_scheduling_intent=None,
        forced_args_present=False,
        tool_names=_available_tool_names(agent_input, None),
        selected_tool_names=_selected_tool_names(domain_results, capability_results),
        capability_results=capability_results,
        domain_results=domain_results,
        output=TraceOutput(
            disposition_status=output_disposition.status,
            output_source="empty",
            visible_message_count=0,
            output_reference_count=0,
            post_analyze_requested=False,
            fallback_reason=None,
        ),
        output_disposition=output_disposition,
        error_disposition=error_disposition,
    )
    return AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        domain_results=tuple(domain_results),
        capability_results=tuple(capability_results),
        metrics={
            "capability_result_count": len(capability_results),
            "domain_result_count": len(domain_results),
        },
        trace=trace,
        output_disposition=output_disposition,
        error_disposition=error_disposition,
    )


def _timeout_result(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    started_at: datetime,
    timeout_seconds: float,
    preselected_scheduling_intent: str | None = None,
    forced_args_present: bool = False,
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
        output_disposition = OutputDisposition(status="ok")
        trace = _build_runtime_trace(
            agent_input=agent_input,
            run_context=run_context,
            input_message=input_message,
            started_at=started_at,
            status="timeout",
            failure_stage="agent_run",
            timeout_seconds=timeout_seconds,
            preselected_scheduling_intent=preselected_scheduling_intent,
            forced_args_present=forced_args_present,
            tool_names=_available_tool_names(
                agent_input, preselected_scheduling_intent
            ),
            selected_tool_names=_selected_tool_names(
                captured_domain_results,
                captured_capability_results,
            ),
            capability_results=captured_capability_results,
            domain_results=captured_domain_results,
            output=TraceOutput(
                disposition_status=output_disposition.status,
                output_source="capability_summary",
                visible_message_count=len(visible_messages),
                output_reference_count=0,
                post_analyze_requested=True,
                fallback_reason="timeout_visible_summary",
            ),
            output_disposition=output_disposition,
            error_disposition=timeout_error,
        )
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
            trace=trace,
            output_disposition=output_disposition,
            error_disposition=timeout_error,
        )

    output_disposition = OutputDisposition(status="empty")
    error_disposition = durable_write_error or timeout_error
    trace = _build_runtime_trace(
        agent_input=agent_input,
        run_context=run_context,
        input_message=input_message,
        started_at=started_at,
        status="timeout",
        failure_stage="agent_run",
        timeout_seconds=timeout_seconds,
        preselected_scheduling_intent=preselected_scheduling_intent,
        forced_args_present=forced_args_present,
        tool_names=_available_tool_names(agent_input, preselected_scheduling_intent),
        selected_tool_names=_selected_tool_names(
            captured_domain_results,
            captured_capability_results,
        ),
        capability_results=captured_capability_results,
        domain_results=captured_domain_results,
        output=TraceOutput(
            disposition_status=output_disposition.status,
            output_source="empty",
            visible_message_count=0,
            output_reference_count=0,
            post_analyze_requested=False,
            fallback_reason=None,
        ),
        output_disposition=output_disposition,
        error_disposition=error_disposition,
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
        trace=trace,
        output_disposition=output_disposition,
        error_disposition=error_disposition,
    )


def _available_tool_names(
    agent_input: AgentInput,
    preselected_scheduling_intent: str | None,
) -> tuple[str, ...]:
    if agent_input.input_type == "reminder.fired":
        return ()
    names = ["scheduling_domain", *_utility_capability_ports().keys()]
    if preselected_scheduling_intent is None:
        names.insert(0, "reminder_domain")
    return tuple(names)


def _selected_tool_names(
    domain_results: Sequence[DomainExecutionResult],
    capability_results: Sequence[CapabilityResult],
) -> tuple[str, ...]:
    domain_tool_names = {
        "reminder": "reminder_domain",
        "scheduling": "scheduling_domain",
    }
    names = [
        domain_tool_names.get(result.domain, result.domain) for result in domain_results
    ]
    names.extend(result.name for result in capability_results)
    return tuple(names)


def _trace_route(
    *,
    agent_input: AgentInput,
    domain_results: Sequence[DomainExecutionResult],
    capability_results: Sequence[CapabilityResult],
    preselected_scheduling_intent: str | None,
    output_disposition: OutputDisposition,
) -> tuple[
    Literal[
        "direct_reply",
        "reminder_domain",
        "scheduling_domain",
        "utility_capability",
        "reminder_fired",
        "fallback",
        "unknown",
    ],
    str,
]:
    if agent_input.input_type == "reminder.fired":
        return "reminder_fired", "reminder_fired_event"
    if preselected_scheduling_intent is not None:
        return "scheduling_domain", "preselected_scheduling_intent"
    if any(result.domain == "scheduling" for result in domain_results):
        return "scheduling_domain", "scheduling_domain_result"
    if any(result.domain == "reminder" for result in domain_results):
        return "reminder_domain", "reminder_domain_result"
    if capability_results:
        return "utility_capability", "capability_result_present"
    if output_disposition.status in {"fallback", "rollback"}:
        return "fallback", "runtime_fallback"
    return "direct_reply", "no_tool_requested"


def _build_runtime_trace(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    started_at: datetime,
    status: str,
    failure_stage: str | None,
    timeout_seconds: float | None,
    preselected_scheduling_intent: str | None,
    forced_args_present: bool,
    tool_names: Sequence[str],
    selected_tool_names: Sequence[str],
    capability_results: Sequence[CapabilityResult],
    domain_results: Sequence[DomainExecutionResult],
    output: TraceOutput,
    output_disposition: OutputDisposition,
    error_disposition: RuntimeErrorDisposition | None,
    content_evidence: Mapping[str, Any] | None = None,
):
    finished_at = datetime.now(UTC)
    route, reason = _trace_route(
        agent_input=agent_input,
        domain_results=domain_results,
        capability_results=capability_results,
        preselected_scheduling_intent=preselected_scheduling_intent,
        output_disposition=output_disposition,
    )
    if (
        status in {"exception", "unknown_tool", "timeout"}
        and reason == "no_tool_requested"
    ):
        route = "fallback"
        reason = "runtime_fallback"
    trace = build_agent_turn_trace(
        agent_input=agent_input,
        run_context=run_context,
        input_message=input_message,
        started_at=started_at,
        finished_at=finished_at,
        timeout_seconds=timeout_seconds,
        status=status,
        failure_stage=failure_stage,
        route=route,
        reason=reason,
        preselected_intent=preselected_scheduling_intent,
        forced_args_present=forced_args_present,
        tool_names=tool_names,
        selected_tool_names=selected_tool_names,
        capability_results=capability_results,
        domain_results=domain_results,
        output=output,
        error_disposition=error_disposition,
    )
    _emit_runtime_trace_if_configured(
        trace,
        content_evidence,
        runtime_metadata=run_context.runtime_metadata,
    )
    return trace


def _emit_runtime_trace_if_configured(
    trace: Any,
    content_evidence: Mapping[str, Any] | None,
    *,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> None:
    config = resolve_agent_turn_trace_config()
    if not config.enabled:
        return
    explicit_path = os.environ.get("COKE_AGENT_TURN_TRACE_JSONL")
    run_id = os.environ.get("COKE_AGENT_TURN_TRACE_RUN_ID")
    suite = os.environ.get("COKE_AGENT_TURN_TRACE_SUITE", "dev")
    if not explicit_path and not run_id:
        metadata_trace = _metadata_trace_sink(runtime_metadata)
        if metadata_trace is None:
            return
        suite = metadata_trace["suite"]
        run_id = metadata_trace["run_id"]
    if not explicit_path and not run_id:
        return
    path = (
        Path(explicit_path)
        if explicit_path
        else trace_evidence_path(
            suite=suite,
            run_id=run_id or "run",
        )
    )
    emit_agent_turn_trace_jsonl(
        path=path,
        trace=trace,
        suite=suite,
        trace_run_id=run_id or path.stem,
        content_evidence=content_evidence,
    )


def _metadata_trace_sink(
    runtime_metadata: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    if not isinstance(runtime_metadata, Mapping):
        return None
    trace_config = runtime_metadata.get("agent_turn_trace")
    if not isinstance(trace_config, Mapping):
        return None
    suite = trace_config.get("suite")
    run_id = trace_config.get("run_id")
    if not isinstance(suite, str) or not suite.strip():
        return None
    if not isinstance(run_id, str) or not run_id.strip():
        return None
    return {"suite": suite.strip(), "run_id": run_id.strip()}


async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    from agent.agno_agent.runtime.execution_agents import run_scheduling_domain

    capability_results: list[CapabilityResult] = []
    domain_results: list[DomainExecutionResult] = []
    started_at = datetime.now(UTC)
    input_message = ""
    preselected_scheduling_intent: str | None = None
    preselected_scheduling_args: dict[str, Any] = {}
    try:
        if agent_input.input_type not in _SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")

        input_message = _input_message(agent_input)
        focus = _resolve_scheduling_focus(agent_input, run_context)
        run_context = replace(
            run_context,
            session_state={
                **dict(run_context.session_state),
                "focus": focus_to_session_state(focus),
            },
        )
        # Runtime safety guards only. These reject impossible or retired writes;
        # supported reminder/scheduling intent routing belongs to the semantic
        # interpreter and interaction-agent tool path below.
        explicit_past_result = _explicit_past_reminder_precheck(
            input_message,
            run_context,
        )
        if explicit_past_result is not None:
            return _domain_visible_text_result(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                started_at=started_at,
                domain_result=explicit_past_result,
            )
        if _is_retired_account_control_turn(input_message):
            return _domain_visible_text_result(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                started_at=started_at,
                domain_result=_retired_account_control_result(),
            )
        preloaded_scheduling_domain_result: dict[str, Any] | None = None
        semantic_client = (
            _create_semantic_intent_client()
            if _focus_has_actionable_candidates(focus)
            else None
        )
        semantic_result = await interpret_semantic_intent(
            focus=focus,
            current_utterance=_current_utterance_for_semantic_interpreter(
                agent_input,
                input_message,
            ),
            client=semantic_client,
        )
        preselected_scheduling_intent, preselected_scheduling_args = (
            _semantic_scheduling_intent_and_args(semantic_result, focus)
        )
        if (
            preselected_scheduling_intent is None
            and _should_fail_closed_focused_semantic(focus, semantic_result)
        ):
            return _domain_visible_text_result(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                started_at=started_at,
                domain_result=_focused_semantic_failure_result(
                    focus,
                    semantic_result,
                    run_context=run_context,
                ),
            )
        if preselected_scheduling_intent:
            run_scheduling_kwargs: dict[str, Any] = {
                "input_message": input_message,
                "intent": preselected_scheduling_intent,
                "run_context": run_context,
                "domain_results": domain_results,
            }
            if preselected_scheduling_args:
                run_scheduling_kwargs["forced_args"] = preselected_scheduling_args
            preloaded_scheduling_domain_result = await run_scheduling_domain(
                **run_scheduling_kwargs
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
            create_agent_kwargs["preselected_scheduling_intent"] = (
                preselected_scheduling_intent
            )
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
        agent_instructions = getattr(agent, "instructions", "") or ""
        logger.info(
            "agent.arun start: timeout=%.1fs, instructions_len=%d, tools=%d, "
            "has_preselected_intent=%s, session_id=%s",
            timeout_seconds,
            len(agent_instructions) if isinstance(agent_instructions, str) else -1,
            len(getattr(agent, "tools", []) or []),
            bool(preselected_scheduling_intent),
            run_context.conversation.id,
        )
        try:
            run_output = await asyncio.wait_for(
                agent.arun(
                    input=input_message,
                    session_id=run_context.conversation.id,
                ),
                timeout=timeout_seconds,
            )
            logger.info(
                "agent.arun returned: session_id=%s", run_context.conversation.id
            )
        except asyncio.TimeoutError:
            return _timeout_result(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                started_at=started_at,
                timeout_seconds=timeout_seconds,
                preselected_scheduling_intent=preselected_scheduling_intent,
                forced_args_present=bool(preselected_scheduling_args),
                capability_results=capability_results,
                domain_results=domain_results,
            )
        final_text = _string_content(getattr(run_output, "content", None))
        if not final_text:
            final_text = _latest_assistant_text(run_output)
        final_text_segments = _parse_visible_text_segments(final_text)
        unconfirmed_promise_error = _check_unconfirmed_durable_write_promise(
            agent_input=agent_input,
            final_text=_visible_text_for_guardrails(final_text_segments),
            capability_results=capability_results,
            domain_results=domain_results,
        )

        captured_capability_results = tuple(capability_results)
        captured_domain_results = tuple(domain_results)
        durable_write_error = _check_durable_write_contract(
            captured_capability_results,
            captured_domain_results,
        )
        runtime_contract_error = durable_write_error or unconfirmed_promise_error
        visible_text_segments = final_text_segments
        output_source = "model"
        fallback_reason = None
        authoritative_domain_text = _authoritative_domain_visible_text(
            captured_domain_results
        )
        if authoritative_domain_text:
            visible_text_segments = (authoritative_domain_text,)
            output_source = "domain_summary"
            fallback_reason = "authoritative_read_result"
        elif not final_text:
            fallback_text = _resolve_visible_text("", captured_capability_results)
            if not fallback_text:
                fallback_text = _resolve_domain_visible_text(
                    captured_domain_results,
                    include_failed_generic=True,
                )
                if fallback_text:
                    output_source = "domain_summary"
                    fallback_reason = "empty_agent_output"
            elif fallback_text:
                output_source = "capability_summary"
                fallback_reason = "empty_agent_output"
            visible_text_segments = (fallback_text,) if fallback_text else ()
        identifier_leak_error = _check_visible_identifier_leak(
            _visible_text_for_guardrails(visible_text_segments)
        )
        serialized_tool_call_error = _check_serialized_tool_call_output(
            _visible_text_for_guardrails(visible_text_segments)
        )
        domain_reply_contract_error = _check_domain_reply_contract(
            final_text=_visible_text_for_guardrails(visible_text_segments),
            domain_results=captured_domain_results,
        )
        runtime_contract_error = (
            runtime_contract_error
            or domain_reply_contract_error
            or identifier_leak_error
            or serialized_tool_call_error
        )
        if runtime_contract_error is not None:
            visible_text_segments = ()
        visible_messages = tuple(
            VisibleMessage(message_type="text", content=segment)
            for segment in visible_text_segments
        )

        if visible_messages and runtime_contract_error is None:
            output_disposition = OutputDisposition(status="ok")
            trace = _build_runtime_trace(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                started_at=started_at,
                status="ok",
                failure_stage=None,
                timeout_seconds=timeout_seconds,
                preselected_scheduling_intent=preselected_scheduling_intent,
                forced_args_present=bool(preselected_scheduling_args),
                tool_names=_available_tool_names(
                    agent_input,
                    preselected_scheduling_intent,
                ),
                selected_tool_names=_selected_tool_names(
                    captured_domain_results,
                    captured_capability_results,
                ),
                capability_results=captured_capability_results,
                domain_results=captured_domain_results,
                output=TraceOutput(
                    disposition_status=output_disposition.status,
                    output_source=output_source,
                    visible_message_count=len(visible_messages),
                    output_reference_count=0,
                    post_analyze_requested=True,
                    fallback_reason=fallback_reason,
                ),
                output_disposition=output_disposition,
                error_disposition=None,
                content_evidence={
                    "input_text": input_message,
                    "visible_output_text": [
                        message.content for message in visible_messages
                    ],
                },
            )
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
                trace=trace,
                output_disposition=output_disposition,
            )

        output_disposition = OutputDisposition(status="empty")
        trace = _build_runtime_trace(
            agent_input=agent_input,
            run_context=run_context,
            input_message=input_message,
            started_at=started_at,
            status="empty_output",
            failure_stage=None,
            timeout_seconds=timeout_seconds,
            preselected_scheduling_intent=preselected_scheduling_intent,
            forced_args_present=bool(preselected_scheduling_args),
            tool_names=_available_tool_names(
                agent_input, preselected_scheduling_intent
            ),
            selected_tool_names=_selected_tool_names(
                captured_domain_results,
                captured_capability_results,
            ),
            capability_results=captured_capability_results,
            domain_results=captured_domain_results,
            output=TraceOutput(
                disposition_status=output_disposition.status,
                output_source="empty",
                visible_message_count=len(visible_messages),
                output_reference_count=0,
                post_analyze_requested=False,
                fallback_reason=None,
            ),
            output_disposition=output_disposition,
            error_disposition=runtime_contract_error,
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
            trace=trace,
            output_disposition=output_disposition,
            error_disposition=runtime_contract_error,
        )
    except UnknownToolError as exc:
        return _unknown_tool_result(
            exc,
            agent_input=agent_input,
            run_context=run_context,
            input_message=input_message,
            started_at=started_at,
            capability_results=capability_results,
            domain_results=domain_results,
        )
    except Exception:
        return _exception_result(
            agent_input=agent_input,
            run_context=run_context,
            input_message=input_message,
            started_at=started_at,
            capability_results=capability_results,
            domain_results=domain_results,
        )
