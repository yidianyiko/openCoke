from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

from agent.agno_agent.adapters.reminder_command_executor import (
    ReminderCommandExecutor,
)
from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.pending_workflow import (
    PendingWorkflowEnvelope,
    normalize_workflow_invariants,
    validate_status_transition,
    workflow_to_document,
)
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool
from conf.config import CONF
from dao.pending_workflow_dao import PendingWorkflowDAO

logger = logging.getLogger(__name__)
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS = 45.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS = 20.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class _WorkflowPersistenceOutcome:
    had_update: bool = False
    workflow: PendingWorkflowEnvelope | None = None
    saved: bool = False


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
            if "workflow_update" in content:
                fallback_content = dict(content)
                raw_workflow_update = fallback_content.pop("workflow_update")
                try:
                    fallback_decision = ReminderDetectDecision.model_validate(
                        fallback_content
                    )
                except Exception:
                    pass
                else:
                    decision_values = fallback_decision.model_dump()
                    decision_values["workflow_update"] = raw_workflow_update
                    return SimpleNamespace(**decision_values)
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
        pending_workflow_enabled: bool | None = None,
        pending_workflow_dao: Any | None = None,
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
        self.pending_workflow_enabled = (
            bool(pending_workflow_enabled)
            if pending_workflow_enabled is not None
            else bool(_pending_workflow_flags().get("enabled", False))
        )
        if self.pending_workflow_enabled:
            self.pending_workflow_dao = pending_workflow_dao or PendingWorkflowDAO()
        else:
            self.pending_workflow_dao = None

    async def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        active_workflow = self._load_active_pending_workflow(run_context)
        detector_run_context = _context_with_active_workflow(
            run_context,
            active_workflow,
        )
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
                    input=build_reminder_intent_input(
                        input_message,
                        detector_run_context,
                    ),
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
                self._persist_workflow_update(
                    retry_decision, run_context, active_workflow
                )
                return _clarification_result(retry_decision)
            else:
                self._persist_workflow_update(decision, run_context, active_workflow)
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
                self._persist_workflow_update(
                    retry_decision, run_context, active_workflow
                )
                return _clarification_result(retry_decision)
            elif retry_decision is None:
                return _timeout_clarification_result()
            elif _is_unrecognized_decision(retry_decision):
                return _invalid_decision_clarification_result()
        if _is_unrecognized_decision(decision):
            return _invalid_decision_clarification_result()
        workflow_outcome = self._persist_workflow_update(
            decision,
            run_context,
            active_workflow,
        )
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
        if workflow_outcome.had_update and (
            not workflow_outcome.saved
            or workflow_outcome.workflow is None
            or workflow_outcome.workflow.status != "ready_to_execute"
        ):
            return _invalid_decision_clarification_result()
        if _is_unbounded_high_frequency_cadence(decision, input_message=input_message):
            return _unbounded_high_frequency_cadence_clarification_result(decision)

        result = self.command_executor.execute(decision, run_context)
        return CapabilityResult(
            name=result.name,
            ok=result.ok,
            content=dict(result.content),
            error=result.error,
            metadata={**dict(result.metadata), "durable_write": True},
        )

    def _load_active_pending_workflow(
        self,
        run_context: AgentRunContext,
    ) -> Mapping[str, Any] | None:
        if not self.pending_workflow_enabled or self.pending_workflow_dao is None:
            return None
        return self.pending_workflow_dao.load_active_for_conversation(
            run_context.user.id,
            run_context.conversation.id,
        )

    def _persist_workflow_update(
        self,
        decision: Any,
        run_context: AgentRunContext,
        active_workflow: Mapping[str, Any] | None,
    ) -> _WorkflowPersistenceOutcome:
        if not self.pending_workflow_enabled or self.pending_workflow_dao is None:
            return _WorkflowPersistenceOutcome()
        workflow = _workflow_update_from_decision(decision, run_context)
        if workflow is None:
            return _WorkflowPersistenceOutcome(
                had_update=_decision_value(decision, "workflow_update") is not None
            )
        normalized_workflow, violations = normalize_workflow_invariants(workflow)
        if violations:
            logger.warning(
                "workflow_invariant_violation",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": workflow.id,
                    "violations": violations,
                },
            )
        current_status = _active_workflow_status(active_workflow)
        if not validate_status_transition(current_status, normalized_workflow.status):
            logger.warning(
                "workflow_invariant_violation",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": normalized_workflow.id,
                    "current_status": current_status,
                    "proposed_status": normalized_workflow.status,
                },
            )
            return _WorkflowPersistenceOutcome(had_update=True)
        if active_workflow is None:
            saved = self.pending_workflow_dao.upsert_new_active_workflow(
                _workflow_storage_document(
                    normalized_workflow,
                    run_context,
                    revision=0,
                )
            )
            if not saved:
                logger.warning(
                    "workflow_concurrent_write_dropped",
                    extra={
                        "conversation_id": run_context.conversation.id,
                        "workflow_id": normalized_workflow.id,
                    },
                )
            return _WorkflowPersistenceOutcome(
                had_update=True,
                workflow=normalized_workflow,
                saved=saved,
            )

        active_workflow_id = str(active_workflow.get("id") or "").strip()
        if active_workflow_id and normalized_workflow.id != active_workflow_id:
            logger.warning(
                "workflow_invariant_violation",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": normalized_workflow.id,
                    "active_workflow_id": active_workflow_id,
                },
            )
            return _WorkflowPersistenceOutcome(had_update=True)

        revision = int(active_workflow.get("revision") or 0)
        saved = self.pending_workflow_dao.cas_update_workflow(
            normalized_workflow.id,
            revision,
            _workflow_storage_document(
                normalized_workflow,
                run_context,
                revision=revision,
            ),
        )
        if not saved:
            logger.warning(
                "workflow_concurrent_write_dropped",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": normalized_workflow.id,
                    "revision": revision,
                },
            )
        return _WorkflowPersistenceOutcome(
            had_update=True,
            workflow=normalized_workflow,
            saved=saved,
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


def _pending_workflow_flags() -> dict[str, Any]:
    flags = CONF.get("features", {}).get("pending_workflow", {}).get("reminders", {})
    return dict(flags) if isinstance(flags, Mapping) else {}


def _context_with_active_workflow(
    run_context: AgentRunContext,
    active_workflow: Mapping[str, Any] | None,
) -> AgentRunContext:
    if active_workflow is None:
        return run_context
    revision = active_workflow.get("revision")
    document = active_workflow.get("document")
    if revision is None or document is None:
        return run_context
    runtime_metadata = dict(run_context.runtime_metadata)
    runtime_metadata["pending_workflow"] = {
        "revision": revision,
        "document": document,
    }
    return replace(run_context, runtime_metadata=runtime_metadata)


def _workflow_update_from_decision(
    decision: Any,
    run_context: AgentRunContext,
) -> PendingWorkflowEnvelope | None:
    workflow_update = _decision_value(decision, "workflow_update")
    if workflow_update is None:
        return None
    if isinstance(workflow_update, PendingWorkflowEnvelope):
        return workflow_update
    try:
        return PendingWorkflowEnvelope.model_validate(workflow_update)
    except Exception as exc:
        logger.warning(
            "workflow_schema_invalid",
            extra={
                "conversation_id": run_context.conversation.id,
                "error": str(exc),
                "workflow_update_type": type(workflow_update).__name__,
            },
        )
        return None


def _active_workflow_status(active_workflow: Mapping[str, Any] | None) -> str | None:
    if active_workflow is None:
        return None
    document = active_workflow.get("document")
    if isinstance(document, Mapping):
        status = document.get("status")
        if status is not None:
            return str(status)
    status = active_workflow.get("status")
    return str(status) if status is not None else None


def _workflow_storage_document(
    workflow: PendingWorkflowEnvelope,
    run_context: AgentRunContext,
    *,
    revision: int,
) -> dict[str, Any]:
    document = workflow_to_document(workflow)
    return {
        "id": workflow.id,
        "owner_user_id": run_context.user.id,
        "conversation_id": run_context.conversation.id,
        "kind": workflow.kind,
        "status": workflow.status,
        "revision": revision,
        "created_at": workflow.origin.created_at,
        "updated_at": workflow.origin.updated_at,
        "expires_at": workflow.origin.expires_at,
        "document": document,
    }


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


def _is_unbounded_high_frequency_cadence(
    decision: Any,
    *,
    input_message: str = "",
) -> bool:
    rrules = [str(_decision_value(decision, "rrule") or "")]
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        rrules.append(str(_decision_value(operation, "rrule") or ""))
    if any(_is_unbounded_high_frequency_rrule(rrule) for rrule in rrules):
        return True
    if _has_explicit_deadline(decision):
        return False
    evidence = str(_decision_value(decision, "schedule_evidence") or "")
    if _decision_value(
        decision, "schedule_basis"
    ) == "explicit_cadence" and _is_high_frequency_evidence(evidence):
        return True
    if _input_has_high_frequency_without_deadline(input_message):
        return True
    return False


def _has_explicit_deadline(decision: Any) -> bool:
    if str(_decision_value(decision, "deadline_at") or "").strip():
        return True
    operations = _decision_value(decision, "operations") or []
    return any(
        str(_decision_value(operation, "deadline_at") or "").strip()
        for operation in operations
    )


def _is_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    return "FREQ=HOURLY" in rule or "FREQ=MINUTELY" in rule


def _is_unbounded_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    if not _is_high_frequency_rrule(rule):
        return False
    return "UNTIL=" not in rule and "COUNT=" not in rule


def _is_high_frequency_evidence(evidence: str) -> bool:
    text = str(evidence or "").strip().lower()
    tokens = (
        "hourly",
        "minutely",
        "every hour",
        "every minute",
        "每小时",
        "每个小时",
        "每一小时",
        "每分钟",
        "每隔",
    )
    return any(token in text for token in tokens)


def _input_has_high_frequency_without_deadline(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not _is_high_frequency_evidence(normalized):
        return False
    deadline_tokens = (
        "到",
        "截止",
        "结束",
        "持续到",
        "until",
        "through",
        "ending",
        "ends",
        "end at",
    )
    return not any(token in normalized for token in deadline_tokens)


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
