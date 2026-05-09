from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from typing import Any

from agent.agno_agent.adapters.reminder_command_executor import (
    ReminderCommandExecutor,
)
from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool

logger = logging.getLogger(__name__)
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS = 45.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS = 20.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS = 20.0


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


def _agent_runtime_reminder_detect_timeout_seconds() -> float:
    return _float_env(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS",
        _DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS,
    )


def _agent_runtime_reminder_detect_timeout_retry_seconds() -> float:
    return _float_env(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS",
        _DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS,
    )


def _agent_runtime_reminder_detect_retry_timeout_seconds() -> float:
    return _float_env(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS",
        _DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS,
    )


def _decision_from_response(response: Any) -> Any:
    if isinstance(response, ReminderDetectDecision):
        return response
    content = getattr(response, "content", response)
    if isinstance(content, ReminderDetectDecision):
        return content
    if isinstance(content, Mapping):
        try:
            return ReminderDetectDecision.model_validate(content)
        except Exception:
            logger.warning("ReminderDetectAgent returned invalid structured mapping")
            return "ReminderDetectInvalidStructuredOutput"
    if isinstance(content, str) and content.strip():
        try:
            return ReminderDetectDecision.model_validate_json(content)
        except Exception:
            return content
    return content


def _build_reminder_retry_input(
    input_message: str,
    run_context: AgentRunContext,
    *,
    reason: str,
) -> str:
    return f"""### Time
{run_context.current_time.isoformat()}

### TZ
{run_context.user.timezone or "UTC"}

### Retry
Retry reason: {reason}
Use the ReminderDetect system instructions already attached to this agent.
Return only a valid ReminderDetectDecision for the current user message.
Do not invent, rename, merge, or concatenate schema field names.
Never output keys like intentaction; use intent_type and action separately.
action must be exactly one of create, update, cancel, delete, complete, batch, list, or empty.
Do not use conversation history or infer missing details from prior turns.
A reminder request with concrete time but no reminder content clarifies; do not create a generic title="提醒" reminder.
Relative delays such as after 1 min or in 10 minutes are concrete; resolve them from Time to trigger_at.
Use short name/object plus activity as reminder content; ignore filler before a concrete reminder time.
Drop final particles; preserve quoted title.
For same-message listed routine times plus a reminder request, use action="batch",
schedule_basis="explicit_occurrences", schedule_evidence, and one operation per listed time.
Use the activity next to each listed time as the title; do not ask for daily confirmation or lead time.
When the user explicitly lists multiple reminder times and tasks, create each requested reminder even if times are close together; do not ask whether to merge them.
For bounded cadence requests with a deadline, use action="batch", schedule_basis="explicit_cadence",
schedule_evidence, deadline_at, and one-shot operations at or before deadline_at instead of RRULE.

### 当前用户消息
{input_message}"""


def _decision_value(decision: Any, field: str) -> Any:
    if isinstance(decision, Mapping):
        return decision.get(field)
    get_value = getattr(decision, "get", None)
    if callable(get_value):
        return get_value(field)
    return getattr(decision, field, None)


class ReminderIntentPort:
    def __init__(
        self,
        *,
        detector_agent: Any | None = None,
        retry_agent: Any | None = None,
        command_executor: Any | None = None,
    ) -> None:
        if detector_agent is None:
            from agent.agno_agent.agents import (
                reminder_detect_agent,
                reminder_detect_retry_agent,
            )

            detector_agent = reminder_detect_agent
            retry_agent = reminder_detect_retry_agent
        self.detector_agent = detector_agent
        self.retry_agent = retry_agent
        self.command_executor = command_executor or ReminderCommandExecutor(
            visible_reminder_tool.entrypoint
        )

    async def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        session_state = {
            "user": {
                "id": run_context.user.id,
                "timezone": run_context.user.timezone,
            },
            "character": {"id": run_context.character.id},
            "conversation": {"id": run_context.conversation.id},
            "platform": run_context.platform,
        }
        try:
            response = await asyncio.wait_for(
                self.detector_agent.arun(
                    input=build_reminder_intent_input(input_message, run_context),
                    session_state=session_state,
                ),
                timeout=_agent_runtime_reminder_detect_timeout_seconds(),
            )
            decision = _decision_from_response(response)
        except asyncio.TimeoutError:
            logger.error(
                "ReminderDetectAgent timed out in single-Agent runtime: timeout=%.1fs",
                _agent_runtime_reminder_detect_timeout_seconds(),
            )
            retry_decision = await self._run_retry_detector(
                input_message,
                run_context,
                session_state,
                reason="primary detector timed out",
                timeout_seconds=_agent_runtime_reminder_detect_timeout_retry_seconds(),
            )
            if retry_decision is None:
                return _timeout_clarification_result()
            decision = retry_decision
        if _should_retry_for_quoted_title_loss(input_message, decision):
            retry_decision = await self._run_retry_detector(
                input_message,
                run_context,
                session_state,
                reason="primary detector dropped quoted reminder title content",
            )
            if retry_decision is None:
                return _timeout_clarification_result()
            if not _should_retry_for_quoted_title_loss(input_message, retry_decision):
                decision = retry_decision
        if _is_clarification_decision(decision) and self.retry_agent is not None:
            retry_decision = await self._run_retry_detector(
                input_message,
                run_context,
                session_state,
                reason="primary detector returned no executable decision",
                timeout_seconds=_float_env(
                    "COKE_AGENT_RUNTIME_REMINDER_CLARIFICATION_RETRY_TIMEOUT_SECONDS",
                    30.0,
                ),
            )
            if _should_execute_decision(retry_decision):
                decision = retry_decision
            elif _is_clarification_decision(retry_decision):
                return _clarification_result(retry_decision)
            else:
                return _clarification_result(decision)
        if not _should_execute_decision(decision) and self.retry_agent is not None:
            retry_decision = await self._run_retry_detector(
                input_message,
                run_context,
                session_state,
                reason="primary detector returned no executable decision",
            )
            if _should_execute_decision(retry_decision):
                decision = retry_decision
            elif _is_clarification_decision(retry_decision):
                return _clarification_result(retry_decision)
            elif retry_decision is None:
                return _timeout_clarification_result()
            elif _is_unrecognized_decision(retry_decision):
                return _invalid_decision_clarification_result()
        if _is_unrecognized_decision(decision):
            return _invalid_decision_clarification_result()
        if _is_clarification_decision(decision):
            return _clarification_result(decision)
        intent_type = _decision_value(decision, "intent_type")
        if not _should_execute_decision(decision):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
                metadata={"durable_write": False},
            )
        if _is_unbounded_high_frequency_cadence(decision):
            return _unbounded_high_frequency_cadence_clarification_result(decision)

        result = self.command_executor.execute(decision, run_context)
        return CapabilityResult(
            name=result.name,
            ok=result.ok,
            content=dict(result.content),
            error=result.error,
            metadata={**dict(result.metadata), "durable_write": True},
        )

    async def _run_retry_detector(
        self,
        input_message: str,
        run_context: AgentRunContext,
        session_state: dict[str, Any],
        *,
        reason: str,
        timeout_seconds: float | None = None,
    ) -> Any | None:
        if self.retry_agent is None:
            return None
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else _agent_runtime_reminder_detect_retry_timeout_seconds()
        )
        try:
            retry_response = await asyncio.wait_for(
                self.retry_agent.arun(
                    input=_build_reminder_retry_input(
                        input_message,
                        run_context,
                        reason=reason,
                    ),
                    session_state=session_state,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "ReminderDetectRetryAgent timed out in single-Agent runtime: timeout=%.1fs",
                timeout,
            )
            return None
        return _decision_from_response(retry_response)


def _should_execute_decision(decision: Any) -> bool:
    intent_type = _decision_value(decision, "intent_type")
    action = _decision_value(decision, "action")
    return intent_type == "crud" or (intent_type == "query" and action == "list")


def _is_unrecognized_decision(decision: Any) -> bool:
    if decision is None:
        return False
    if isinstance(decision, (str, bytes)):
        return bool(str(decision).strip())
    intent_type = _decision_value(decision, "intent_type")
    action = _decision_value(decision, "action")
    if intent_type in {"crud", "clarify", "query", "discussion", "none"}:
        return False
    if action in {
        "",
        None,
        "create",
        "update",
        "delete",
        "cancel",
        "complete",
        "batch",
        "list",
    }:
        return False
    return True


def _should_retry_for_quoted_title_loss(input_message: str, decision: Any) -> bool:
    if not _should_execute_decision(decision):
        return False
    quoted_segments = _quoted_segments(input_message)
    if not quoted_segments:
        return False
    titles = _decision_titles(decision)
    if not titles:
        return False
    return any(
        segment and not any(segment in title for title in titles)
        for segment in quoted_segments
    )


def _quoted_segments(text: str) -> tuple[str, ...]:
    pairs = (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"))
    segments: list[str] = []
    for opening, closing in pairs:
        start = 0
        while True:
            left = text.find(opening, start)
            if left < 0:
                break
            right = text.find(closing, left + len(opening))
            if right < 0:
                break
            segment = text[left : right + len(closing)].strip()
            if segment:
                segments.append(segment)
            start = right + len(closing)
    return tuple(segments)


def _decision_titles(decision: Any) -> tuple[str, ...]:
    titles: list[str] = []
    title = str(_decision_value(decision, "title") or "").strip()
    if title:
        titles.append(title)
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        operation_title = _decision_value(operation, "title")
        if operation_title:
            titles.append(str(operation_title).strip())
    return tuple(title for title in titles if title)


def _is_clarification_decision(decision: Any) -> bool:
    return _decision_value(decision, "intent_type") == "clarify" and bool(
        str(_decision_value(decision, "clarification_question") or "").strip()
    )


def _is_unbounded_high_frequency_cadence(decision: Any) -> bool:
    if _decision_value(decision, "schedule_basis") != "explicit_cadence":
        return False
    if str(_decision_value(decision, "deadline_at") or "").strip():
        return False
    rrules = [str(_decision_value(decision, "rrule") or "")]
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        rrules.append(str(_decision_value(operation, "rrule") or ""))
    evidence = str(_decision_value(decision, "schedule_evidence") or "")
    if any(_is_high_frequency_rrule(rrule) for rrule in rrules):
        return True
    return _is_high_frequency_evidence(evidence)


def _is_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    return "FREQ=HOURLY" in rule or "FREQ=MINUTELY" in rule


def _is_high_frequency_evidence(evidence: str) -> bool:
    text = str(evidence or "").strip().lower()
    tokens = (
        "hourly",
        "minutely",
        "every hour",
        "every minute",
        "每小时",
        "每分钟",
        "每隔",
    )
    return any(token in text for token in tokens)


def _clarification_result(decision: Any) -> CapabilityResult:
    question = str(_decision_value(decision, "clarification_question") or "").strip()
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": question,
        },
        metadata={"durable_write": False},
    )


def _unbounded_high_frequency_cadence_clarification_result(
    decision: Any,
) -> CapabilityResult:
    title = str(_decision_value(decision, "title") or "").strip()
    if not title:
        operations = _decision_value(decision, "operations") or []
        for operation in operations:
            title = str(_decision_value(operation, "title") or "").strip()
            if title:
                break
    subject = title or "这个高频提醒"
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": f"{subject}要持续到什么时候结束？请告诉我截止时间。",
        },
        metadata={"durable_write": False},
    )


def _timeout_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=False,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "提醒设置还没完成。请确认具体提醒时间和提醒内容。",
        },
        error="ReminderDetectTimeout",
        metadata={"durable_write": False},
    )


def _invalid_decision_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=False,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "提醒设置还没完成。请确认具体提醒时间和提醒内容。",
        },
        error="ReminderDetectInvalidDecision",
        metadata={"durable_write": False},
    )
