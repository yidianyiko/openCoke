from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
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
    validate_slot_transitions,
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
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS = 30.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class _WorkflowPersistenceOutcome:
    had_update: bool = False
    workflow: PendingWorkflowEnvelope | None = None
    saved: bool = False
    stored_revision: int | None = None
    concurrent_drop: bool = False
    fresh_workflow: Mapping[str, Any] | None = None


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
        raw_workflow_update = content.get("workflow_update")
        try:
            decision = ReminderDetectDecision.model_validate(content)
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
        if raw_workflow_update is not None and decision.workflow_update is None:
            decision_values = decision.model_dump()
            decision_values["workflow_update"] = raw_workflow_update
            return SimpleNamespace(**decision_values)
        return decision
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
    workflow_block = _active_workflow_prompt_block(run_context)
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
workflow_update is only for pending clarification workflows.
When no pending-workflow block is present, do not output workflow_update.
For retries without a pending-workflow block, workflow_update is not an allowed output field.
Complete CRUD decisions must omit workflow_update.
Never attach workflow_update to create, update, delete, complete, batch, or list decisions.
Do not use conversation history or infer missing details from prior turns.
A reminder request with concrete time but no reminder content clarifies, except bare call/wake/alarm-me requests where the reminder verb is the content. Do not create a generic title="提醒" reminder.
One-shot deadline wording such as "before/by 22:30" is not a concrete trigger_at; clarify for when to remind unless the user explicitly says to remind at that deadline.
Need/intention statements such as "I need to do X at Y" are discussion, not clarify, unless the user asks you to remind, notify, alarm, call, check in, nudge, or supervise.
Do not ask whether to set a reminder for ordinary plans or need/intention statements; return discussion.
Relative delays such as after 1 min or in 10 minutes are concrete; resolve them from Time to trigger_at.
If a bare local clock time has already passed and the user did not explicitly say today, resolve the next future occurrence.
Use short name/object plus activity as reminder content; ignore filler before a concrete reminder time.
Noisy filler before a concrete clock time is not recurrence evidence.
Do not ask for frequency confirmation unless the user explicitly requests a cadence or recurrence.
Drop final particles; preserve quoted title.
For same-message listed routine times plus a reminder request, use action="batch",
schedule_basis="explicit_occurrences", schedule_evidence, and one operation per listed time.
Use the activity next to each listed time as the title; do not ask for daily confirmation or lead time.
When the user explicitly lists multiple reminder times and tasks, create each requested reminder even if times are close together; do not ask whether to merge them.
For bounded recurring cadence requests with a deadline, use action="create",
RRULE, schedule_basis="explicit_cadence", schedule_evidence, and deadline_at.
Do not drop the deadline.
Weekly recurrence with listed weekdays must include every listed weekday in BYDAY; do not keep only the first weekday.
{workflow_block}

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
                detector_run_context,
                session_state,
                reason="primary detector timed out",
                timeout_seconds=_agent_runtime_reminder_detect_timeout_retry_seconds(),
            )
            if retry_decision is None:
                return _fallback_clarification_for_input(
                    input_message,
                    _timeout_clarification_result(),
                )
            decision = retry_decision
        if _should_retry_for_quoted_title_loss(input_message, decision):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason="primary detector dropped quoted reminder title content",
            )
            if retry_decision is None:
                return _fallback_clarification_for_input(
                    input_message,
                    _timeout_clarification_result(),
                )
            if not _should_retry_for_quoted_title_loss(input_message, retry_decision):
                decision = retry_decision
        if _is_clarification_decision(decision) and self.retry_agent is not None:
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
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
                retry_outcome = self._persist_workflow_update(
                    retry_decision, run_context, active_workflow
                )
                if retry_outcome.concurrent_drop:
                    return _fresh_workflow_state_result(retry_outcome.fresh_workflow)
                return _clarification_result(retry_decision)
            else:
                fallback_outcome = self._persist_workflow_update(
                    decision, run_context, active_workflow
                )
                if fallback_outcome.concurrent_drop:
                    return _fresh_workflow_state_result(fallback_outcome.fresh_workflow)
                return _clarification_result(decision)
        if not _should_execute_decision(decision) and self.retry_agent is not None:
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason="primary detector returned no executable decision",
            )
            if _should_execute_decision(retry_decision):
                decision = retry_decision
            elif _is_clarification_decision(retry_decision):
                retry_outcome = self._persist_workflow_update(
                    retry_decision, run_context, active_workflow
                )
                if retry_outcome.concurrent_drop:
                    return _fresh_workflow_state_result(retry_outcome.fresh_workflow)
                return _clarification_result(retry_decision)
            elif retry_decision is None:
                return _fallback_clarification_for_input(
                    input_message,
                    _timeout_clarification_result(),
                )
            elif _is_unrecognized_decision(retry_decision):
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
        if _is_unrecognized_decision(decision):
            return _fallback_clarification_for_input(
                input_message,
                _invalid_decision_clarification_result(),
            )
        if _should_execute_decision(decision) and _is_bounded_cadence_deadline_loss(
            input_message, decision
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector returned an unbounded recurring reminder "
                    "for an input that includes a cadence and a deadline; keep "
                    "the deadline as deadline_at"
                ),
            )
            if _should_execute_decision(
                retry_decision
            ) and not _is_bounded_cadence_deadline_loss(input_message, retry_decision):
                decision = retry_decision
            elif retry_decision is not None and _is_unrecognized_decision(
                retry_decision
            ):
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
            else:
                return _bounded_cadence_deadline_loss_clarification_result(decision)
        if _should_execute_decision(decision) and _is_unbounded_high_frequency_cadence(
            decision, input_message=input_message
        ):
            return _unbounded_high_frequency_cadence_clarification_result(decision)
        workflow_outcome = self._persist_workflow_update(
            decision,
            run_context,
            active_workflow,
        )
        if workflow_outcome.concurrent_drop:
            return _fresh_workflow_state_result(workflow_outcome.fresh_workflow)
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
            return _fallback_clarification_for_input(
                input_message,
                _invalid_decision_clarification_result(),
            )
        execution_workflow = workflow_outcome.workflow
        execution_revision = workflow_outcome.stored_revision
        if workflow_outcome.had_update and execution_workflow is not None:
            executing_outcome = self._persist_workflow_status(
                execution_workflow,
                run_context,
                expected_revision=execution_revision,
                status="executing",
            )
            if not executing_outcome.saved:
                return _fresh_workflow_state_result(executing_outcome.fresh_workflow)
            execution_workflow = executing_outcome.workflow
            execution_revision = executing_outcome.stored_revision

        decision = _normalize_past_bare_create_trigger(
            input_message,
            decision,
            run_context,
        )
        if _should_clarify_date_only_create(input_message, decision):
            return _date_only_missing_time_clarification_result()
        result = self.command_executor.execute(decision, run_context)
        if (
            not workflow_outcome.had_update
            and _should_retry_for_past_one_shot_failure(input_message, result)
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "reminder tool rejected past trigger_at; if the user gave a "
                    "bare clock time and did not explicitly say today, resolve the "
                    "next future occurrence"
                ),
            )
            if _should_execute_decision(retry_decision) and not (
                _is_unbounded_high_frequency_cadence(
                    retry_decision,
                    input_message=input_message,
                )
            ):
                decision = retry_decision
                result = self.command_executor.execute(decision, run_context)
        if workflow_outcome.had_update and execution_workflow is not None:
            terminal_status = "completed" if result.ok else "failed"
            terminal_outcome = self._persist_workflow_status(
                execution_workflow,
                run_context,
                expected_revision=execution_revision,
                status=terminal_status,
            )
            if terminal_outcome.concurrent_drop:
                logger.warning(
                    "workflow_terminal_write_dropped",
                    extra={
                        "conversation_id": run_context.conversation.id,
                        "workflow_id": execution_workflow.id,
                        "status": terminal_status,
                    },
                )
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
            now=run_context.current_time,
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
            return _WorkflowPersistenceOutcome()
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
        slot_violations = validate_slot_transitions(
            _active_workflow_envelope(active_workflow),
            normalized_workflow,
        )
        if slot_violations:
            logger.warning(
                "workflow_invariant_violation",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": normalized_workflow.id,
                    "slot_violations": slot_violations,
                },
            )
            return _WorkflowPersistenceOutcome(had_update=True)
        if active_workflow is None:
            saved = self.pending_workflow_dao.upsert_new_active_workflow(
                _workflow_storage_document(
                    normalized_workflow,
                    run_context,
                    revision=0,
                ),
                now=run_context.current_time,
            )
            if not saved:
                logger.warning(
                    "workflow_concurrent_write_dropped",
                    extra={
                        "conversation_id": run_context.conversation.id,
                        "workflow_id": normalized_workflow.id,
                    },
                )
                fresh_workflow = self._load_active_pending_workflow(run_context)
            return _WorkflowPersistenceOutcome(
                had_update=True,
                workflow=normalized_workflow,
                saved=saved,
                stored_revision=0 if saved else None,
                concurrent_drop=not saved,
                fresh_workflow=fresh_workflow if not saved else None,
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
            run_context.user.id,
            run_context.conversation.id,
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
            fresh_workflow = self._load_active_pending_workflow(run_context)
        return _WorkflowPersistenceOutcome(
            had_update=True,
            workflow=normalized_workflow,
            saved=saved,
            stored_revision=revision + 1 if saved else None,
            concurrent_drop=not saved,
            fresh_workflow=fresh_workflow if not saved else None,
        )

    def _persist_workflow_status(
        self,
        workflow: PendingWorkflowEnvelope,
        run_context: AgentRunContext,
        *,
        expected_revision: int | None,
        status: str,
    ) -> _WorkflowPersistenceOutcome:
        if (
            not self.pending_workflow_enabled
            or self.pending_workflow_dao is None
            or expected_revision is None
        ):
            return _WorkflowPersistenceOutcome()
        if not validate_status_transition(workflow.status, status):
            logger.warning(
                "workflow_invariant_violation",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": workflow.id,
                    "current_status": workflow.status,
                    "proposed_status": status,
                },
            )
            return _WorkflowPersistenceOutcome(had_update=True)
        updated_workflow = workflow.model_copy(update={"status": status})
        saved = self.pending_workflow_dao.cas_update_workflow(
            updated_workflow.id,
            run_context.user.id,
            run_context.conversation.id,
            expected_revision,
            _workflow_storage_document(
                updated_workflow,
                run_context,
                revision=expected_revision,
            ),
        )
        if not saved:
            if status in {"completed", "cancelled", "expired", "failed"} and hasattr(
                self.pending_workflow_dao,
                "mark_terminal_workflow_from_executing",
            ):
                terminal_saved = (
                    self.pending_workflow_dao.mark_terminal_workflow_from_executing(
                        updated_workflow.id,
                        run_context.user.id,
                        run_context.conversation.id,
                        _workflow_storage_document(
                            updated_workflow,
                            run_context,
                            revision=expected_revision,
                        ),
                    )
                )
                if terminal_saved:
                    return _WorkflowPersistenceOutcome(
                        had_update=True,
                        workflow=updated_workflow,
                        saved=True,
                        stored_revision=expected_revision,
                    )
            logger.warning(
                "workflow_concurrent_write_dropped",
                extra={
                    "conversation_id": run_context.conversation.id,
                    "workflow_id": updated_workflow.id,
                    "revision": expected_revision,
                },
            )
            return _WorkflowPersistenceOutcome(
                had_update=True,
                workflow=updated_workflow,
                concurrent_drop=True,
                fresh_workflow=self._load_active_pending_workflow(run_context),
            )
        return _WorkflowPersistenceOutcome(
            had_update=True,
            workflow=updated_workflow,
            saved=True,
            stored_revision=expected_revision + 1,
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


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _active_workflow_prompt_block(run_context: AgentRunContext) -> str:
    pending_workflow = run_context.runtime_metadata.get("pending_workflow")
    if not pending_workflow:
        return ""
    return "\n\n### Active Pending Workflow\n" + json.dumps(
        _json_safe_value(pending_workflow),
        ensure_ascii=False,
        sort_keys=True,
    )


def _active_workflow_envelope(
    active_workflow: Mapping[str, Any] | None,
) -> PendingWorkflowEnvelope | None:
    if active_workflow is None:
        return None
    document = active_workflow.get("document")
    if document is None:
        return None
    try:
        return PendingWorkflowEnvelope.model_validate(document)
    except Exception:
        return None


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
                "raw_decision_excerpt": str(_decision_public_excerpt(decision))[:1000],
                "workflow_update_type": type(workflow_update).__name__,
            },
        )
        return None


def _decision_public_excerpt(decision: Any) -> dict[str, Any]:
    return {
        key: _decision_value(decision, key)
        for key in (
            "intent_type",
            "action",
            "clarification_question",
            "workflow_update",
        )
        if _decision_value(decision, key) is not None
    }


def _fresh_workflow_state_result(
    active_workflow: Mapping[str, Any] | None,
) -> CapabilityResult:
    document = (
        active_workflow.get("document")
        if isinstance(active_workflow, Mapping)
        else None
    )
    status = ""
    missing_fields: list[str] = []
    goal = ""
    if isinstance(document, Mapping):
        status = str(document.get("status") or "")
        missing_fields = [
            str(field)
            for field in document.get("missing_fields", [])
            if str(field).strip()
        ]
        goal = str(document.get("goal") or "").strip()
    detail = "、".join(missing_fields)
    if detail:
        summary = f"这个提醒流程已经更新，还需要补充：{detail}。"
    elif status:
        summary = f"这个提醒流程已经更新，当前状态是 {status}。"
    else:
        summary = "这个提醒流程已经更新，请继续按最新状态补充信息。"
    content: dict[str, Any] = {
        "action": "clarify",
        "intent_type": "clarify",
        "summary": summary,
        "workflow_status": status,
        "missing_fields": missing_fields,
    }
    if goal:
        content["goal"] = goal
    return CapabilityResult(
        name="reminder",
        ok=True,
        content=content,
        metadata={"durable_write": False},
    )


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


def _should_retry_for_past_one_shot_failure(
    input_message: str,
    result: Any,
) -> bool:
    if not str(input_message or "").strip():
        return False
    if getattr(result, "ok", None) is not False:
        return False
    if str(getattr(result, "error", "") or "") != "InvalidSchedule":
        return False
    content = getattr(result, "content", None)
    summary = ""
    if isinstance(content, Mapping):
        summary = str(content.get("summary") or "")
    return "时间已经过去" in summary or "past" in summary.lower()


_BARE_CLOCK_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：.]\s*\d{1,2}|\d{1,2}\s*(?:点|时)|"
    r"[零一二两三四五六七八九十百半]+\s*(?:点|时))"
)
_EXPLICIT_DATE_PATTERN = re.compile(
    r"(今天|今日|今晚|今早|明天|明早|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,4}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|\d{1,2}[/-]\d{1,2})",
    re.IGNORECASE,
)
_STANDALONE_DAY_OF_MONTH_PATTERN = re.compile(r"(?<!\d)\d{1,2}\s*[日号](?!\d)")
_INPUT_MESSAGE_PREFIX_PATTERN = re.compile(r"^(?:（[^）]*）\s*)+")


def _normalize_past_bare_create_trigger(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> Any:
    if _decision_value(decision, "action") != "create":
        return decision
    trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
    if not trigger_at:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not _BARE_CLOCK_PATTERN.search(current_user_text):
        return decision
    if _EXPLICIT_DATE_PATTERN.search(current_user_text):
        return decision
    try:
        parsed = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError:
        return decision
    current_time = run_context.current_time
    if parsed.tzinfo is not None and current_time.tzinfo is not None:
        current_time = current_time.astimezone(parsed.tzinfo)
    if parsed > current_time:
        return decision
    while parsed <= current_time:
        parsed += timedelta(days=1)
    return _copy_decision_with_value(decision, "trigger_at", parsed.isoformat())


def _copy_decision_with_value(decision: Any, field: str, value: Any) -> Any:
    if isinstance(decision, Mapping):
        return {**dict(decision), field: value}
    model_dump = getattr(decision, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        data[field] = value
        return SimpleNamespace(**data)
    try:
        data = vars(decision).copy()
    except TypeError:
        return decision
    data[field] = value
    return SimpleNamespace(**data)


def _should_clarify_date_only_create(input_message: str, decision: Any) -> bool:
    if not _decision_has_create_operation(decision):
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    has_date_reference = bool(
        _EXPLICIT_DATE_PATTERN.search(current_user_text)
        or _STANDALONE_DAY_OF_MONTH_PATTERN.search(current_user_text)
    )
    if not has_date_reference or _BARE_CLOCK_PATTERN.search(current_user_text):
        return False
    return True


def _decision_has_create_operation(decision: Any) -> bool:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        return True
    if action != "batch":
        return False
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        if str(_operation_value(operation, "action") or "").strip() == "create":
            return True
    return False


def _operation_value(operation: Any, field: str) -> Any:
    if isinstance(operation, Mapping):
        return operation.get(field)
    return getattr(operation, field, None)


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
    if _input_has_high_frequency_without_deadline(input_message):
        return True
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
    return False


def _has_explicit_deadline(decision: Any) -> bool:
    if str(_decision_value(decision, "deadline_at") or "").strip():
        return True
    operations = _decision_value(decision, "operations") or []
    return any(
        str(_decision_value(operation, "deadline_at") or "").strip()
        for operation in operations
    )


def _is_bounded_cadence_deadline_loss(input_message: str, decision: Any) -> bool:
    if not _input_has_bounded_cadence_deadline(input_message):
        return False
    if _has_explicit_deadline(decision):
        return False
    return _has_unbounded_recurring_rrule(decision)


def _has_unbounded_recurring_rrule(decision: Any) -> bool:
    rrules = [str(_decision_value(decision, "rrule") or "")]
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        rrules.append(str(_decision_value(operation, "rrule") or ""))
    return any(_is_unbounded_rrule(rrule) for rrule in rrules)


def _is_unbounded_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    if "FREQ=" not in rule:
        return False
    return "UNTIL=" not in rule and "COUNT=" not in rule


def _input_has_bounded_cadence_deadline(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    cadence_tokens = (
        "每天",
        "每日",
        "每晚",
        "每早",
        "每周",
        "每月",
        "每年",
        "每小时",
        "每分钟",
        "每隔",
        "daily",
        "weekly",
        "monthly",
        "hourly",
        "every ",
    )
    deadline_tokens = (
        "截止",
        "持续到",
        "结束",
        "之前",
        "以前",
        "until",
        "before",
        "through",
        " by ",
    )
    deadline_patterns = (
        r"\d{1,2}\s*月\s*\d{1,2}\s*(?:号|日)?\s*前",
        r"\d{1,2}\s*(?:号|日)\s*前",
        r"\d{1,2}\s*(?::\s*\d{1,2}|点)\s*前",
    )
    has_deadline = any(token in normalized for token in deadline_tokens) or any(
        re.search(pattern, normalized) for pattern in deadline_patterns
    )
    return any(token in normalized for token in cadence_tokens) and has_deadline


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
        "每个整点",
        "整点",
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


def _input_has_one_shot_deadline_without_trigger(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if _is_high_frequency_evidence(normalized):
        return False
    has_reminder_request = any(
        token in normalized
        for token in (
            "提醒",
            "叫我",
            "喊我",
            "通知",
            "remind",
            "notify",
            "alarm",
        )
    )
    if not has_reminder_request:
        return False
    has_deadline_word = any(
        token in normalized for token in ("之前", "以前", "前", "before", "by ")
    )
    has_clock = bool(
        re.search(r"\d{1,2}\s*[:：点]", normalized)
        or re.search(r"[一二三四五六七八九十两]+点", normalized)
    )
    return has_deadline_word and has_clock


def _input_has_concrete_time_without_reminder_content(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    has_concrete_time = bool(
        re.search(r"\d{1,2}\s*[:：点]", normalized)
        or re.search(r"[一二三四五六七八九十两]+点", normalized)
        or re.search(r"(今天|今晚|明天|后天|周[一二三四五六日天])", normalized)
    )
    if not has_concrete_time:
        return False
    return bool(
        re.search(
            r"(?:提醒我|提醒一下我|提醒一下|提醒|叫我|喊我)[。.!！?？\s]*$",
            normalized,
        )
    )


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


def _bounded_cadence_deadline_loss_clarification_result(
    decision: Any,
) -> CapabilityResult:
    title = str(_decision_value(decision, "title") or "").strip()
    subject = title or "这个重复提醒"
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": f"{subject}有截止条件，请确认截止日期和最后一次提醒时间。",
        },
        metadata={"durable_write": False},
    )


def _high_frequency_input_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "这个高频提醒要从什么时候开始，持续到什么时候结束？请告诉我开始时间和截止时间。",
        },
        metadata={"durable_write": False},
    )


def _fallback_clarification_for_input(
    input_message: str,
    fallback: CapabilityResult,
) -> CapabilityResult:
    if _input_has_high_frequency_without_deadline(input_message):
        return _high_frequency_input_clarification_result()
    if fallback.error == "ReminderDetectInvalidDecision":
        if _input_has_concrete_time_without_reminder_content(input_message):
            return _missing_reminder_content_clarification_result()
        if _input_has_one_shot_deadline_without_trigger(input_message):
            return _deadline_without_trigger_clarification_result()
    return fallback


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


def _deadline_without_trigger_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "这是截止时间。你想在这个时间之前的什么时候提醒你？",
        },
        metadata={"durable_write": False},
    )


def _date_only_missing_time_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "你想在那天几点提醒你？",
        },
        metadata={"durable_write": False},
    )


def _missing_reminder_content_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "你想让我提醒你做什么？",
        },
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
