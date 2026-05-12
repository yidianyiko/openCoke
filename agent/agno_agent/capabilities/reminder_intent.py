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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
from agent.prompt.reminder_few_shot import format_reminder_few_shots_for_prompt
from conf.config import CONF
from dao.pending_workflow_dao import PendingWorkflowDAO

logger = logging.getLogger(__name__)
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS = 30.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS = 45.0
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS = 20.0


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
            try:
                raw_content = json.loads(content)
            except Exception:
                return content
            if isinstance(raw_content, Mapping) and "workflow_update" in raw_content:
                fallback_content = dict(raw_content)
                raw_workflow_update = fallback_content.pop("workflow_update")
                try:
                    fallback_decision = ReminderDetectDecision.model_validate(
                        fallback_content
                    )
                except Exception:
                    return content
                decision_values = fallback_decision.model_dump()
                decision_values["workflow_update"] = raw_workflow_update
                return SimpleNamespace(**decision_values)
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
All batch create decisions require top-level schedule_basis and schedule_evidence; do not put them only inside operations.
Clarify and discussion retries must return empty action and empty operations.
Do not use conversation history or infer missing details from prior turns.
Chinese clock separators such as "：" and "∶" are concrete local time separators; parse "22∶12" the same as "22:12".
A reminder request with concrete time but no reminder content clarifies, except bare call/wake/alarm-me requests where the reminder verb is the content. Do not create a generic title="提醒" reminder.
Status-only or referential fragments such as "not done yet", "还没做", "这件事", or "that" are not reminder content unless current-turn task text or recent context names the task; clarify for the task/content.
Bare call/wake/alarm-me with a concrete clock time is complete: return a CRUD create decision, use the call/wake/alarm verb phrase as title, resolve bare clocks to the next future local occurrence, and do not ask for reminder content or date.
One-shot deadline wording such as "before/by 22:30" is not a concrete trigger_at; clarify for when to remind unless the user explicitly says to remind at that deadline.
Event time plus an advance offset is complete: if the user says an event is at T and asks to remind X before/提前X提醒, set trigger_at to T minus X; a vague advance request without an offset clarifies for how long before the event.
For recurring cadence wording with an end phrase such as "到/直到/until + clock/date", treat that end phrase as deadline_at. Use trigger_at for the first future occurrence in the cadence, not for the ending deadline unless it is also the first occurrence.
Need/intention statements such as "I need to do X at Y" are discussion, not clarify, unless the user asks you to remind, notify, alarm, call, check in, nudge, or supervise.
Meta discussion or complaints about reminder/alarm behavior, acknowledgement, whether replies are required, or how reminders stay active are discussion unless the same message asks for a concrete reminder operation.
Plans to test, improve, or discuss reminder functionality/capability are discussion unless the same message asks for a concrete reminder operation.
Do not ask whether to set a reminder for ordinary plans or need/intention statements; return discussion.
Pomodoro/tomato timer starts are timed reminder requests: if the user asks to start a new Pomodoro/tomato timer and asks to be reminded at the end/time without an explicit duration, use 25 minutes after Time as trigger_at.
Relative delays such as after 1 min, 20min later, 过20min, or in 10 minutes are concrete; resolve them from Time to trigger_at. If task/content appears before the reminder verb in the same message, use it as title.
Completion-conditioned reminders such as after I finish/read/watch this are not schedulable without a clock or duration; clarify for when to remind.
If a bare local clock time has already passed and the user did not explicitly say today, resolve the next future occurrence.
Undesignated local clock times attached to a reminder task are concrete; if the clock has passed, resolve the next future local occurrence and do not ask for date or trigger_at.
Day-of-month wording before the reminder verb and clock, such as "22号早上9点提醒我", is an explicit reminder date; preserve that day in trigger_at.
Do not use RRULE or explicit_cadence unless the user supplies recurrence frequency or interval wording.
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
A bounded window with explicit start date, start clock, end clock, cadence, and reminder content is complete; use trigger_at for the first occurrence and deadline_at for the window end.
Weekly recurrence with listed weekdays must include every listed weekday in BYDAY; do not keep only the first weekday.
Weekday ranges such as 周一到周五 or 星期一到星期五 are listed weekdays; expand them in BYDAY, for example BYDAY=MO,TU,WE,TH,FR.
Weekday names used as a recurrence cadence are concrete; create the weekly recurrence and do not ask which calendar date.
If an interval schedule includes a manual correction or exception to occurrence times, clarify for the exact occurrence list instead of approximating with RRULE.
For a bounded cadence, wording that stops the cadence at or after the same deadline is the deadline boundary, not a manual correction or occurrence-time exception.
{workflow_block}

### Reminder Few-Shot Decisions
{format_reminder_few_shots_for_prompt()}

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
            if _input_is_reminder_feature_work_topic(
                input_message
            ) or _input_is_reminder_behavior_meta_discussion(input_message):
                return _no_action_discussion_result()
            retry_reason = "primary detector timed out"
            if _input_has_relative_delay_and_preceding_task_content(input_message):
                retry_reason = (
                    "primary detector timed out on a relative-delay reminder whose "
                    "task/content appears before the reminder verb; use the preceding "
                    "task/content as the create title and resolve the relative delay"
                )
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=retry_reason,
                timeout_seconds=_agent_runtime_reminder_detect_timeout_retry_seconds(),
            )
            if retry_decision is None:
                return _fallback_clarification_for_input(
                    input_message,
                    _timeout_clarification_result(),
                )
            decision = retry_decision
        if _input_is_reminder_feature_work_topic(
            input_message
        ) or _input_is_reminder_behavior_meta_discussion(input_message):
            return _no_action_discussion_result()
        if _is_unrecognized_decision(
            decision
        ) and _input_is_standalone_reminder_opt_out(input_message):
            return _no_action_discussion_result()
        if _is_unrecognized_decision(decision) and self.retry_agent is not None:
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector returned invalid structured output; "
                    "retry with a schema-valid ReminderDetectDecision"
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
            elif retry_decision is None:
                return _fallback_clarification_for_input(
                    input_message,
                    _timeout_clarification_result(),
                )
            else:
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
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
        if _is_clarification_decision(
            decision
        ) and (
            _input_is_standalone_reminder_opt_out(input_message)
            or _input_is_reminder_behavior_meta_discussion(input_message)
            or _input_is_reminder_feature_work_topic(input_message)
        ):
            return _no_action_discussion_result()
        if _is_clarification_decision(decision) and self.retry_agent is not None:
            retry_reason = "primary detector returned no executable decision"
            if _input_has_complete_weekday_range_recurring_reminder(input_message):
                retry_reason = (
                    "primary detector returned clarification for a complete "
                    "weekday-range recurring reminder; the weekday range, clock, "
                    "and reminder content are present, so return a CRUD create "
                    "with weekly RRULE BYDAY=MO,TU,WE,TH,FR instead of asking "
                    "which day or time"
                )
            elif _input_has_relative_delay_and_preceding_task_content(input_message):
                retry_reason = (
                    "primary detector returned clarification for a relative-delay "
                    "reminder whose task/content appears before the reminder verb; "
                    "use the preceding task/content as the create title and resolve "
                    "the relative delay"
                )
            elif _input_has_mixed_clocked_reminder_clause(input_message):
                retry_reason = (
                    "primary detector returned clarification even though the current "
                    "message contains concrete clock-governed reminder clauses; "
                    "return executable create/batch operations for concrete "
                    "clock-governed reminder clauses and drop date-only or no-clock "
                    "clauses instead of inventing default times"
                )
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=retry_reason,
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
            retry_reason = "primary detector returned no executable decision"
            if _input_has_complete_weekday_range_recurring_reminder(input_message):
                retry_reason = (
                    "primary detector returned no executable decision for a "
                    "complete weekday-range recurring reminder; the weekday range, "
                    "clock, and reminder content are present, so return a CRUD "
                    "create with weekly RRULE BYDAY=MO,TU,WE,TH,FR instead of "
                    "asking which day or time"
                )
            elif _input_has_relative_delay_and_preceding_task_content(input_message):
                retry_reason = (
                    "primary detector returned no executable decision for a "
                    "relative-delay reminder whose task/content appears before the "
                    "reminder verb; use the preceding task/content as the create "
                    "title and resolve the relative delay"
                )
            elif _input_has_mixed_clocked_reminder_clause(input_message):
                retry_reason = (
                    "primary detector returned no executable decision even though "
                    "the current message contains concrete clock-governed reminder "
                    "clauses; return executable create/batch operations for concrete "
                    "clock-governed reminder clauses and drop date-only or no-clock "
                    "clauses instead of inventing default times"
                )
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=retry_reason,
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
        if _should_execute_decision(
            decision
        ) and _input_has_large_today_time_range_points_request(input_message):
            return _ambiguous_time_range_clarification_result()
        if _should_execute_decision(
            decision
        ) and _is_today_time_range_points_incomplete_or_recurring(
            input_message, decision
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector compressed today's task-range reminder into "
                    "a recurring or incomplete create; use action=batch with "
                    "one-shot create operations for the future task start points"
                ),
            )
            if _should_execute_decision(
                retry_decision
            ) and not _is_today_time_range_points_incomplete_or_recurring(
                input_message, retry_decision
            ):
                decision = retry_decision
            elif retry_decision is not None and _is_unrecognized_decision(
                retry_decision
            ):
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
            else:
                return _ambiguous_time_range_clarification_result()
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
        if (
            _should_execute_decision(decision)
            and _input_has_next_whole_hour_reference(input_message)
            and _is_unbounded_high_frequency_cadence(decision, input_message=input_message)
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector treated a next whole hour reference as an "
                    "hourly cadence; next whole hour is a one-shot reminder, not "
                    "a recurring schedule"
                ),
            )
            if _should_execute_decision(retry_decision) and not (
                _is_unbounded_high_frequency_cadence(
                    retry_decision,
                    input_message=input_message,
                )
            ):
                decision = retry_decision
            else:
                return _unbounded_high_frequency_cadence_clarification_result(
                    decision
                )
        if _should_execute_decision(decision) and _is_unbounded_high_frequency_cadence(
            decision, input_message=input_message
        ):
            return _unbounded_high_frequency_cadence_clarification_result(decision)
        if (
            _should_execute_decision(decision)
            and _input_is_standalone_reminder_opt_out(input_message)
            and str(_decision_value(decision, "action") or "").strip()
            in {"delete", "cancel"}
        ):
            return _no_action_discussion_result()
        if _should_execute_decision(
            decision
        ) and _input_is_standalone_reminder_acknowledgement(input_message):
            return _no_action_discussion_result()
        if _input_is_reminder_behavior_meta_discussion(
            input_message
        ) or _input_is_reminder_feature_work_topic(input_message):
            return _no_action_discussion_result()
        workflow_outcome = self._persist_workflow_update(
            decision,
            run_context,
            active_workflow,
        )
        if workflow_outcome.concurrent_drop:
            return _fresh_workflow_state_result(workflow_outcome.fresh_workflow)
        if _is_clarification_decision(decision):
            if _input_is_standalone_reminder_opt_out(
                input_message
            ) or _input_is_reminder_behavior_meta_discussion(
                input_message
            ) or _input_is_reminder_feature_work_topic(input_message):
                return _no_action_discussion_result()
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

        decision = _normalize_relative_delay_create_trigger(
            input_message,
            decision,
            run_context,
        )
        decision = _normalize_past_bare_create_trigger(
            input_message,
            decision,
            run_context,
        )
        decision = _drop_ungoverned_batch_plan_operations(input_message, decision)
        decision = _drop_batch_operations_without_local_schedule_evidence(
            input_message, decision
        )
        if _should_clarify_date_only_create(input_message, decision):
            return _date_only_missing_time_clarification_result()
        if _should_clarify_ambiguous_time_range_create(input_message, decision):
            return _ambiguous_time_range_clarification_result()
        if _should_clarify_completion_condition_create(input_message, decision):
            return _completion_condition_missing_time_clarification_result()
        if _should_clarify_status_only_content_create(input_message, decision):
            return _missing_reminder_content_clarification_result()
        if (
            (
                _should_retry_for_title_schedule_evidence_leak(decision)
                or _should_retry_for_weekday_mismatch(
                    input_message, decision, run_context
                )
            )
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector returned schedule evidence inside the title "
                    "or a trigger_at weekday that conflicts with the user's weekday; "
                    "keep schedule evidence out of title and preserve weekday"
                ),
            )
            if (
                _should_execute_decision(retry_decision)
                and not _should_retry_for_title_schedule_evidence_leak(retry_decision)
                and not _should_retry_for_weekday_mismatch(
                    input_message, retry_decision, run_context
                )
            ):
                decision = retry_decision
            else:
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
        if (
            _should_retry_for_ungoverned_single_create_title(input_message, decision)
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector chose a create title is not governed by "
                    "the reminder verb because it appears before the reminder verb; "
                    "use the task governed by the reminder verb as the title"
                ),
            )
            if _should_execute_decision(
                retry_decision
            ) and not _should_retry_for_ungoverned_single_create_title(
                input_message, retry_decision
            ):
                decision = retry_decision
            else:
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
        if (
            _should_retry_for_day_of_month_mismatch(
                input_message, decision, run_context
            )
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector dropped an explicit day-of-month date; "
                    "preserve date wording like 22号 before the reminder clock "
                    "in trigger_at"
                ),
            )
            if _should_execute_decision(
                retry_decision
            ) and not _should_retry_for_day_of_month_mismatch(
                input_message, retry_decision, run_context
            ):
                decision = retry_decision
            else:
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
        if (
            _should_retry_for_missing_scheduled_clauses(input_message, decision)
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "primary detector returned fewer create operations than explicit "
                    "scheduled reminder/check-in/report clauses in the current "
                    "message; preserve each explicit scheduled clause, including "
                    "dot-separated times like 23.00, as a create operation"
                ),
            )
            if _should_execute_decision(
                retry_decision
            ) and not _should_retry_for_missing_scheduled_clauses(
                input_message, retry_decision
            ):
                decision = retry_decision
            else:
                return _fallback_clarification_for_input(
                    input_message,
                    _invalid_decision_clarification_result(),
                )
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
                    "next future occurrence. If the request starts a Pomodoro/tomato "
                    "timer without an explicit duration, use 25 minutes after Time "
                    "as trigger_at"
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
        if (
            not workflow_outcome.had_update
            and _should_retry_for_bounded_recurring_no_future_failure(
                input_message, decision, result
            )
            and self.retry_agent is not None
        ):
            retry_decision = await self._run_retry_detector(
                input_message,
                detector_run_context,
                session_state,
                reason=(
                    "reminder tool rejected a bounded recurring cadence because "
                    "the recurrence has no future fire time; keep the supplied "
                    "deadline as deadline_at, and set trigger_at to the first "
                    "future occurrence before that deadline"
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


def _should_retry_for_bounded_recurring_no_future_failure(
    input_message: str,
    decision: Any,
    result: Any,
) -> bool:
    if not _input_has_bounded_cadence_deadline(input_message):
        return False
    if not _decision_has_recurring_create(decision):
        return False
    if getattr(result, "ok", None) is not False:
        return False
    if str(getattr(result, "error", "") or "") != "InvalidSchedule":
        return False
    content = getattr(result, "content", None)
    summary = ""
    if isinstance(content, Mapping):
        summary = str(content.get("summary") or "")
    return "no future fire time" in summary.lower() or "没有未来" in summary


_BARE_CLOCK_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：∶.]\s*\d{1,2}|\d{1,2}\s*(?:点|时)|"
    r"[零一二两三四五六七八九十百半]+\s*(?:点|时))"
)
_AMBIGUOUS_ADJACENT_HOUR_RANGE_PATTERN = re.compile(
    r"(?:一二|二三|两三|三四|四五|五六|六七|七八|八九|九十)\s*(?:点|时)"
    r"|(?:\d{1,2})\s*(?:-|~|到|至)\s*(?:\d{1,2})\s*(?:点|时)"
)
_CLOCK_RANGE_PATTERN = re.compile(
    r"\d{1,2}\s*(?:[:：∶]\s*\d{1,2})?\s*(?:-|~|到|至)\s*"
    r"\d{1,2}\s*(?:[:：∶]\s*\d{1,2})?"
)
_EXPLICIT_DATE_PATTERN = re.compile(
    r"(今天|今日|今晚|今早|明天|明早|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,4}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|\d{1,2}[/-]\d{1,2})",
    re.IGNORECASE,
)
_STANDALONE_DAY_OF_MONTH_PATTERN = re.compile(r"(?<!\d)\d{1,2}\s*[日号](?!\d)")
_WEEKDAY_RANGE_PATTERN = re.compile(
    r"(?:周|星期|礼拜)([一二三四五六日天1-7])\s*(?:到|至|-|—|~)\s*"
    r"(?:周|星期|礼拜)([一二三四五六日天1-7])"
)
_INPUT_MESSAGE_PREFIX_PATTERN = re.compile(r"^(?:（[^）]*）\s*)+")
_REMINDER_VERB_PATTERN = re.compile(
    r"提醒我|叫我|喊我|通知我|监督我|问我|检查我|"
    r"remind me|call me|notify me|nudge me",
    re.IGNORECASE,
)
_SCHEDULE_BACK_REFERENCE_PATTERN = re.compile(
    r"上述这些时间|上面这些时间|这些时间|这几个时间|以上时间|上述时间"
)
_COMPLETION_CONDITION_PATTERN = re.compile(
    r"(?:看|读|写|做|弄|搞|处理|完成|结束|学|背|练).{0,8}(?:完|好|结束|完成)(?:后|之后)?"
    r"|after\s+(?:i\s+|you\s+)?(?:finish|complete|am\s+done|are\s+done)",
    re.IGNORECASE,
)
_RELATIVE_DELAY_PATTERN = re.compile(
    r"(?:过\s*(?P<prefix_amount>\d+|[零〇一二两三四五六七八九十]{1,4})\s*"
    r"(?P<prefix_unit>minutes?|mins?|分钟|分|小时|个小时|天|日))"
    r"|(?:(?P<suffix_amount>\d+|[零〇一二两三四五六七八九十]{1,4})\s*"
    r"(?P<suffix_unit>minutes?|mins?|分钟|分|小时|个小时|天|日)\s*"
    r"(?:后|之后|以后|later))"
    r"|(?:(?P<timer_amount>\d+|[零〇一二两三四五六七八九十]{1,4})\s*"
    r"(?P<timer_unit>minutes?|mins?|分钟|分|小时|个小时|天|日)\s*"
    r"(?:计时|倒计时))",
    re.IGNORECASE,
)
_VAGUE_ADVANCE_REMINDER_PATTERN = re.compile(
    r"提前\s*(?:提醒我|提醒一下我|提醒一下|提醒|叫我|喊我|通知我|"
    r"remind me|notify me|nudge me)",
    re.IGNORECASE,
)
_STATUS_ONLY_REMINDER_TITLE_PATTERN = re.compile(
    r"^(?:都|也|还|这|那|这个|那个|这些|那些|它|事情|事|东西|任务|it|that|this)*"
    r"(?:还没|还没有|没|没有|未|尚未|not)"
    r"(?:做|弄|搞|处理|完成|finish|done)(?:完|好|掉|了)?$",
    re.IGNORECASE,
)
_SINGLE_BARE_CLOCK_EXTRACTION_PATTERN = re.compile(
    r"(?P<hour>\d{1,2})\s*[:：.]\s*(?P<minute>\d{1,2})"
    r"|(?P<hour_only>\d{1,2})\s*(?:点|时)(?P<half>半)?"
    r"(?:\s*差\s*(?P<hour_only_minus_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?"
    r"|\s*(?:过)?\s*(?P<hour_only_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?)?"
    r"|(?P<chinese_hour>[零〇一二两三四五六七八九十]{1,3})\s*(?:点|时)(?P<chinese_half>半)?"
    r"(?:\s*差\s*(?P<chinese_minus_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?"
    r"|\s*(?:过)?\s*(?P<chinese_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?)?"
)
_PM_DAY_PERIOD_PATTERN = re.compile(r"(下午|晚上|今晚|傍晚|每晚)")
_AM_DAY_PERIOD_PATTERN = re.compile(r"(早上|早晨|上午|凌晨|清晨|今早|明早)")


def _normalize_relative_delay_create_trigger(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> Any:
    action = str(_decision_value(decision, "action") or "").strip()
    if action not in {"create", "batch"}:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    delay = _single_relative_delay(current_user_text)
    if delay is None:
        return decision
    normalized_trigger_at = _relative_delay_trigger_at(run_context, delay)

    if action == "batch":
        operations = list(_decision_value(decision, "operations") or [])
        if len(operations) != 1:
            return decision
        operation = operations[0]
        if str(_operation_value(operation, "action") or "").strip() != "create":
            return decision
        trigger_at = str(_operation_value(operation, "trigger_at") or "").strip()
        if not trigger_at or trigger_at == normalized_trigger_at:
            return decision
        return _copy_decision_with_operations(
            decision,
            [_copy_operation_with_value(operation, "trigger_at", normalized_trigger_at)],
        )

    trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
    if not trigger_at or trigger_at == normalized_trigger_at:
        return decision
    return _copy_decision_with_value(decision, "trigger_at", normalized_trigger_at)


def _single_relative_delay(current_user_text: str) -> timedelta | None:
    matches = list(_RELATIVE_DELAY_PATTERN.finditer(current_user_text))
    if len(matches) != 1:
        return None
    match = matches[0]
    amount_text = (
        match.group("prefix_amount")
        or match.group("suffix_amount")
        or match.group("timer_amount")
        or ""
    )
    amount = int(amount_text) if amount_text.isdigit() else _parse_chinese_hour(amount_text)
    if amount is None or amount <= 0:
        return None
    unit = (
        match.group("prefix_unit")
        or match.group("suffix_unit")
        or match.group("timer_unit")
        or ""
    )
    if unit.lower() in {"分钟", "分", "min", "mins", "minute", "minutes"}:
        return timedelta(minutes=amount)
    if unit in {"小时", "个小时"}:
        return timedelta(hours=amount)
    if unit in {"天", "日"}:
        return timedelta(days=amount)
    return None


def _input_has_relative_delay_and_preceding_task_content(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    delay_match = _RELATIVE_DELAY_PATTERN.search(current_user_text)
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if delay_match is None or reminder_match is None:
        return False
    prefix = current_user_text[: min(delay_match.start(), reminder_match.start())]
    prefix = re.sub(
        r"(?:\bok+\b|好的|好|行|嗯|请|麻烦|帮我|记得|please|[,，。；;、\s])+",
        "",
        prefix,
        flags=re.IGNORECASE,
    )
    return bool(prefix)


_NEXT_WHOLE_HOUR_PATTERN = re.compile(
    r"(?:下个|下一个|下次|next)\s*(?:整点|whole hour)",
    re.IGNORECASE,
)


def _input_has_next_whole_hour_reference(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    return bool(_NEXT_WHOLE_HOUR_PATTERN.search(current_user_text))


def _input_has_mixed_clocked_reminder_clause(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return False
    if not _BARE_CLOCK_PATTERN.search(current_user_text):
        return False
    if not (
        _REMINDER_VERB_PATTERN.search(current_user_text)
        or re.search(r"要|询问我|问问我|告诉我", current_user_text)
    ):
        return False
    return bool(
        _EXPLICIT_DATE_PATTERN.search(current_user_text)
        or _STANDALONE_DAY_OF_MONTH_PATTERN.search(current_user_text)
    )


def _input_has_complete_weekday_range_recurring_reminder(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return False
    if not _WEEKDAY_RANGE_PATTERN.search(current_user_text):
        return False
    if not _BARE_CLOCK_PATTERN.search(current_user_text):
        return False
    return bool(_REMINDER_VERB_PATTERN.search(current_user_text))


def _relative_delay_trigger_at(
    run_context: AgentRunContext,
    delay: timedelta,
) -> str:
    current_time = run_context.current_time
    if current_time.tzinfo is None:
        try:
            timezone = ZoneInfo(run_context.user.timezone or "UTC")
        except ZoneInfoNotFoundError:
            timezone = ZoneInfo("UTC")
        current_time = current_time.replace(tzinfo=timezone)
    return (current_time + delay).replace(microsecond=0).isoformat()


def _normalize_past_bare_create_trigger(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> Any:
    action = str(_decision_value(decision, "action") or "").strip()
    if action not in {"create", "batch"}:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not _BARE_CLOCK_PATTERN.search(current_user_text):
        return decision
    if _EXPLICIT_DATE_PATTERN.search(current_user_text):
        return decision

    if action == "batch":
        operations = list(_decision_value(decision, "operations") or [])
        if not operations:
            return decision
        normalized_operations = []
        changed = False
        for operation in operations:
            if str(_operation_value(operation, "action") or "").strip() != "create":
                normalized_operations.append(operation)
                continue
            trigger_at = str(_operation_value(operation, "trigger_at") or "").strip()
            normalized_trigger_at = _next_future_trigger_at(
                trigger_at, run_context.current_time
            )
            if normalized_trigger_at and normalized_trigger_at != trigger_at:
                normalized_operations.append(
                    _copy_operation_with_value(
                        operation,
                        "trigger_at",
                        normalized_trigger_at,
                    )
                )
                changed = True
                continue
            normalized_operations.append(operation)
        if changed:
            return _copy_decision_with_operations(decision, normalized_operations)
        return decision

    trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
    if not trigger_at:
        return decision
    normalized_trigger_at = _next_future_trigger_at_for_single_bare_clock(
        current_user_text,
        run_context,
    ) or _next_future_trigger_at(trigger_at, run_context.current_time)
    if normalized_trigger_at and normalized_trigger_at != trigger_at:
        return _copy_decision_with_value(decision, "trigger_at", normalized_trigger_at)
    return decision


def _next_future_trigger_at_for_single_bare_clock(
    current_user_text: str,
    run_context: AgentRunContext,
) -> str:
    matches = list(_SINGLE_BARE_CLOCK_EXTRACTION_PATTERN.finditer(current_user_text))
    if len(matches) != 1:
        return ""
    parsed = _parse_bare_clock_match(current_user_text, matches[0])
    if parsed is None:
        return ""
    hour, minute = parsed
    try:
        timezone = ZoneInfo(run_context.user.timezone or "UTC")
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    current_time = run_context.current_time
    if current_time.tzinfo is None:
        current_local = current_time.replace(tzinfo=timezone)
    else:
        current_local = current_time.astimezone(timezone)
    if _should_treat_bare_clock_as_same_afternoon(
        current_user_text,
        matches[0],
        hour=hour,
        minute=minute,
        current_local=current_local,
    ):
        hour += 12
    candidate = current_local.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate <= current_local:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def _should_treat_bare_clock_as_same_afternoon(
    current_user_text: str,
    match: re.Match[str],
    *,
    hour: int,
    minute: int,
    current_local: datetime,
) -> bool:
    if not (1 <= hour < 12 and current_local.hour >= 12):
        return False
    prefix = current_user_text[max(0, match.start() - 6) : match.start()]
    if _AM_DAY_PERIOD_PATTERN.search(prefix) or _PM_DAY_PERIOD_PATTERN.search(prefix):
        return False
    pm_hour = hour + 12
    if pm_hour not in {current_local.hour, current_local.hour + 1}:
        return False
    candidate = current_local.replace(
        hour=pm_hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    return candidate > current_local


def _parse_bare_clock_match(
    current_user_text: str,
    match: re.Match[str],
) -> tuple[int, int] | None:
    prefix = current_user_text[max(0, match.start() - 6) : match.start()]
    period_applied = False
    if match.group("hour") is not None:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
    elif match.group("hour_only") is not None:
        hour = int(match.group("hour_only"))
        minus_text = match.group("hour_only_minus_minute")
        minute_text = match.group("hour_only_minute")
        if minus_text:
            parsed_minus = _parse_clock_minute(minus_text)
            if parsed_minus is None or not (1 <= parsed_minus <= 59):
                return None
            if 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
                hour += 12
                period_applied = True
            hour, minute = _subtract_clock_minutes(hour, parsed_minus)
        else:
            minute = (
                _parse_clock_minute(minute_text)
                if minute_text
                else (30 if match.group("half") else 0)
            )
    else:
        hour = _parse_chinese_hour(match.group("chinese_hour") or "")
        minus_text = match.group("chinese_minus_minute")
        minute_text = match.group("chinese_minute")
        if hour is None:
            return None
        if minus_text:
            parsed_minus = _parse_clock_minute(minus_text)
            if parsed_minus is None or not (1 <= parsed_minus <= 59):
                return None
            if 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
                hour += 12
                period_applied = True
            hour, minute = _subtract_clock_minutes(hour, parsed_minus)
        else:
            minute = (
                _parse_chinese_minute(minute_text)
                if minute_text
                else (30 if match.group("chinese_half") else 0)
            )
    if hour is None or minute is None or not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    if not period_applied and 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
        hour += 12
    return hour, minute


_CHINESE_DIGIT_VALUES = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_chinese_hour(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in _CHINESE_DIGIT_VALUES:
        return _CHINESE_DIGIT_VALUES[text]
    if text == "十":
        return 10
    if text.startswith("十"):
        suffix = text[1:]
        if suffix in _CHINESE_DIGIT_VALUES:
            return 10 + _CHINESE_DIGIT_VALUES[suffix]
        return None
    if text.endswith("十"):
        prefix = text[:-1]
        if prefix in _CHINESE_DIGIT_VALUES:
            return _CHINESE_DIGIT_VALUES[prefix] * 10
        return None
    if "十" in text:
        prefix, suffix = text.split("十", 1)
        if prefix in _CHINESE_DIGIT_VALUES and suffix in _CHINESE_DIGIT_VALUES:
            return _CHINESE_DIGIT_VALUES[prefix] * 10 + _CHINESE_DIGIT_VALUES[suffix]
    return None


def _parse_chinese_minute(value: str) -> int | None:
    text = str(value or "").strip()
    if len(text) == 2 and text[0] in {"零", "〇"} and text[1] in _CHINESE_DIGIT_VALUES:
        return _CHINESE_DIGIT_VALUES[text[1]]
    return _parse_chinese_hour(text)


def _parse_clock_minute(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return _parse_chinese_minute(text)


def _subtract_clock_minutes(hour: int, minutes_before: int) -> tuple[int, int]:
    total_minutes = (hour % 24) * 60 - minutes_before
    total_minutes %= 24 * 60
    return total_minutes // 60, total_minutes % 60


def _next_future_trigger_at(trigger_at: str, current_time: datetime) -> str:
    if not trigger_at:
        return ""
    try:
        parsed = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is not None and current_time.tzinfo is not None:
        current_time = current_time.astimezone(parsed.tzinfo)
    if parsed > current_time:
        return trigger_at
    while parsed <= current_time:
        parsed += timedelta(days=1)
    return parsed.isoformat()


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


def _copy_operation_with_value(operation: Any, field: str, value: Any) -> Any:
    if isinstance(operation, Mapping):
        return {**dict(operation), field: value}
    model_dump = getattr(operation, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        data[field] = value
        return SimpleNamespace(**data)
    try:
        data = vars(operation).copy()
    except TypeError:
        return operation
    data[field] = value
    return SimpleNamespace(**data)


def _drop_ungoverned_batch_plan_operations(input_message: str, decision: Any) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "batch":
        return decision
    operations = list(_decision_value(decision, "operations") or [])
    if len(operations) <= 1:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if _SCHEDULE_BACK_REFERENCE_PATTERN.search(current_user_text):
        return decision
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if reminder_match is not None:
        reminder_start = reminder_match.start()
        kept_operations = []
        changed = False
        for operation in operations:
            if str(_operation_value(operation, "action") or "").strip() != "create":
                kept_operations.append(operation)
                continue
            title = str(_operation_value(operation, "title") or "").strip()
            if not title:
                kept_operations.append(operation)
                continue
            first_title_at = current_user_text.find(title)
            if first_title_at < 0:
                kept_operations.append(operation)
                continue
            later_title_at = current_user_text.find(title, reminder_start)
            if first_title_at < reminder_start and later_title_at < 0:
                changed = True
                continue
            kept_operations.append(operation)
        if changed and kept_operations:
            decision = _copy_decision_with_operations(decision, kept_operations)
    return _drop_ungoverned_cadence_task_operations(current_user_text, decision)


def _drop_batch_operations_without_local_schedule_evidence(
    input_message: str, decision: Any
) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "batch":
        return decision
    operations = list(_decision_value(decision, "operations") or [])
    if len(operations) <= 1:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    kept_operations = []
    changed = False
    for operation in operations:
        if str(_operation_value(operation, "action") or "").strip() != "create":
            kept_operations.append(operation)
            continue
        title = str(_operation_value(operation, "title") or "").strip()
        if not title or current_user_text.find(title) < 0:
            kept_operations.append(operation)
            continue
        if _title_has_local_schedule_context(current_user_text, title):
            kept_operations.append(operation)
            continue
        changed = True
    if not changed or not kept_operations:
        return decision
    return _copy_decision_with_operations(decision, kept_operations)


def _drop_ungoverned_cadence_task_operations(text: str, decision: Any) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "batch":
        return decision
    operations = list(_decision_value(decision, "operations") or [])
    if len(operations) <= 1:
        return decision
    has_high_frequency_recurring_create = any(
        str(_operation_value(operation, "action") or "").strip() == "create"
        and _is_high_frequency_rrule(str(_operation_value(operation, "rrule") or ""))
        for operation in operations
    )
    if not has_high_frequency_recurring_create:
        return decision

    kept_operations = []
    changed = False
    for operation in operations:
        if str(_operation_value(operation, "action") or "").strip() != "create":
            kept_operations.append(operation)
            continue
        title = str(_operation_value(operation, "title") or "").strip()
        rrule = str(_operation_value(operation, "rrule") or "").strip()
        if rrule and not _is_high_frequency_rrule(rrule):
            kept_operations.append(operation)
            continue
        if title and (
            _title_has_local_reminder_verb_context(text, title)
            or (rrule and _title_has_local_cadence_context(text, title))
        ):
            kept_operations.append(operation)
            continue
        changed = True
    if not changed or not kept_operations:
        return decision
    return _copy_decision_with_operations(decision, kept_operations)


def _title_has_local_reminder_verb_context(text: str, title: str) -> bool:
    start = 0
    while True:
        position = text.find(title, start)
        if position < 0:
            return False
        clause_start = _previous_clause_boundary(text, position)
        clause = text[clause_start : position + len(title)]
        if _REMINDER_VERB_PATTERN.search(clause):
            return True
        start = position + len(title)


def _title_has_local_cadence_context(text: str, title: str) -> bool:
    start = 0
    while True:
        position = text.find(title, start)
        if position < 0:
            return False
        clause_start = _previous_clause_boundary(text, position)
        clause_end = _next_clause_boundary(text, position + len(title))
        clause = text[clause_start:clause_end]
        if _is_high_frequency_evidence(clause):
            return True
        start = position + len(title)


def _title_has_local_schedule_context(text: str, title: str) -> bool:
    start = 0
    while True:
        position = text.find(title, start)
        if position < 0:
            return False
        clause_start = _previous_clause_boundary(text, position)
        clause_end = _next_clause_boundary(text, position + len(title))
        clause = text[clause_start:clause_end]
        if _BARE_CLOCK_PATTERN.search(clause) or _RELATIVE_DELAY_PATTERN.search(
            clause
        ):
            return True
        start = position + len(title)


def _previous_clause_boundary(text: str, position: int) -> int:
    boundary = 0
    for separator in "，,。；;！？!?\n":
        index = text.rfind(separator, 0, position)
        if index >= boundary:
            boundary = index + 1
    return boundary


def _next_clause_boundary(text: str, position: int) -> int:
    boundary = len(text)
    for separator in "，,。；;！？!?\n":
        index = text.find(separator, position)
        if index != -1 and index < boundary:
            boundary = index
    return boundary


def _copy_decision_with_operations(decision: Any, operations: list[Any]) -> Any:
    if isinstance(decision, Mapping):
        return {**dict(decision), "operations": operations}
    model_dump = getattr(decision, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        data["operations"] = operations
        return SimpleNamespace(**data)
    try:
        data = vars(decision).copy()
    except TypeError:
        return decision
    data["operations"] = operations
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


def _should_clarify_ambiguous_time_range_create(
    input_message: str, decision: Any
) -> bool:
    if not _decision_has_create_operation(decision):
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    return bool(_AMBIGUOUS_ADJACENT_HOUR_RANGE_PATTERN.search(current_user_text))


def _should_clarify_completion_condition_create(
    input_message: str, decision: Any
) -> bool:
    if not _decision_has_create_operation(decision):
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not _REMINDER_VERB_PATTERN.search(current_user_text):
        return False
    if not _COMPLETION_CONDITION_PATTERN.search(current_user_text):
        return False
    if (
        _RELATIVE_DELAY_PATTERN.search(current_user_text)
        or _BARE_CLOCK_PATTERN.search(current_user_text)
        or _EXPLICIT_DATE_PATTERN.search(current_user_text)
        or _STANDALONE_DAY_OF_MONTH_PATTERN.search(current_user_text)
    ):
        return False
    return True


def _should_clarify_status_only_content_create(input_message: str, decision: Any) -> bool:
    if not _decision_has_create_operation(decision):
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not _REMINDER_VERB_PATTERN.search(current_user_text):
        return False
    if not _BARE_CLOCK_PATTERN.search(current_user_text):
        return False
    if _input_has_concrete_time_without_reminder_content(current_user_text):
        return True
    for title in _decision_titles(decision):
        normalized_title = re.sub(r"\s+", "", title).strip().lower()
        if _STATUS_ONLY_REMINDER_TITLE_PATTERN.fullmatch(normalized_title):
            return True
    return False


def _should_retry_for_ungoverned_single_create_title(
    input_message: str, decision: Any
) -> bool:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if reminder_match is None:
        return False
    title = str(_decision_value(decision, "title") or "").strip()
    if not title:
        return False
    first_title_at = current_user_text.find(title)
    if first_title_at < 0 or first_title_at >= reminder_match.start():
        return False
    if _input_has_relative_delay_and_preceding_task_content(input_message):
        return False
    if _input_has_next_whole_hour_reference(input_message):
        return False
    if current_user_text.find(title, reminder_match.start()) >= 0:
        return False
    return not _title_has_local_reminder_verb_context(current_user_text, title)


def _should_retry_for_title_schedule_evidence_leak(decision: Any) -> bool:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return False
    title = str(_decision_value(decision, "title") or "").strip()
    return bool(title and re.search(r"提前", title))


_CHINESE_WEEKDAY_INDEX = {
    "一": 0,
    "1": 0,
    "二": 1,
    "2": 1,
    "三": 2,
    "3": 2,
    "四": 3,
    "4": 3,
    "五": 4,
    "5": 4,
    "六": 5,
    "6": 5,
    "日": 6,
    "天": 6,
    "7": 6,
}
_EXPLICIT_WEEKDAY_PATTERN = re.compile(r"(?:下周|本周|这周|这星期|下星期|星期|周)([一二三四五六日天1-7])")


def _should_retry_for_weekday_mismatch(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> bool:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if _WEEKDAY_RANGE_PATTERN.search(current_user_text):
        return False
    weekday = _explicit_weekday_index(current_user_text)
    if weekday is None:
        return False
    trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
    if not trigger_at:
        return False
    try:
        parsed = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(run_context.user.timezone or "UTC"))
        except ZoneInfoNotFoundError:
            return False
    else:
        try:
            parsed = parsed.astimezone(ZoneInfo(run_context.user.timezone or "UTC"))
        except ZoneInfoNotFoundError:
            return False
    return parsed.weekday() != weekday


def _explicit_weekday_index(text: str) -> int | None:
    match = _EXPLICIT_WEEKDAY_PATTERN.search(text)
    if match is None:
        return None
    return _CHINESE_WEEKDAY_INDEX.get(match.group(1))


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


def _should_retry_for_missing_scheduled_clauses(
    input_message: str, decision: Any
) -> bool:
    expected_count = _explicit_scheduled_clause_count(input_message)
    if expected_count < 2:
        return False
    return _decision_create_operation_count(decision) < expected_count


def _explicit_scheduled_clause_count(input_message: str) -> int:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return 0
    if not (
        _REMINDER_VERB_PATTERN.search(current_user_text)
        or re.search(r"询问我|告诉我|问问我|check in|report", current_user_text, re.I)
    ):
        return 0
    # A task range such as "11:30-13:30" names one scheduled task clause:
    # the start time is the reminder trigger and the end time is context.
    normalized = re.sub(
        r"(\d{1,2}[:：]\d{2})\s*[-–—]\s*\d{1,2}[:：]\d{2}",
        r"\1",
        current_user_text,
    )
    matches = {
        re.sub(r"\s+", "", match.group(0))
        for match in _SINGLE_BARE_CLOCK_EXTRACTION_PATTERN.finditer(normalized)
    }
    return len(matches)


def _decision_create_operation_count(decision: Any) -> int:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        return 1
    if action != "batch":
        return 0
    return sum(
        1
        for operation in (_decision_value(decision, "operations") or [])
        if str(_operation_value(operation, "action") or "").strip() == "create"
    )


def _should_retry_for_day_of_month_mismatch(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> bool:
    expected_day = _explicit_schedule_day_of_month_before_reminder_verb(input_message)
    if expected_day is None:
        return False
    try:
        timezone = ZoneInfo(run_context.user.timezone or "UTC")
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    for trigger_at in _create_trigger_values(decision):
        try:
            parsed = datetime.fromisoformat(str(trigger_at).replace("Z", "+00:00"))
        except Exception:
            continue
        if parsed.tzinfo is None:
            local = parsed.replace(tzinfo=timezone)
        else:
            local = parsed.astimezone(timezone)
        if local.day != expected_day:
            return True
    return False


def _explicit_schedule_day_of_month_before_reminder_verb(
    input_message: str,
) -> int | None:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return None
    verb_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    search_end = verb_match.start() if verb_match else len(current_user_text)
    prefix = current_user_text[:search_end]
    for match in _STANDALONE_DAY_OF_MONTH_PATTERN.finditer(prefix):
        after_day = prefix[match.end() :].lstrip()
        if after_day.startswith(("前", "之前", "以前")):
            continue
        try:
            day = int(re.search(r"\d{1,2}", match.group(0)).group(0))
        except Exception:
            continue
        if not 1 <= day <= 31:
            continue
        if _BARE_CLOCK_PATTERN.search(after_day):
            return day
    return None


def _create_trigger_values(decision: Any) -> tuple[str, ...]:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
        return (trigger_at,) if trigger_at else ()
    if action != "batch":
        return ()
    values: list[str] = []
    for operation in _decision_value(decision, "operations") or []:
        if str(_operation_value(operation, "action") or "").strip() != "create":
            continue
        trigger_at = str(_operation_value(operation, "trigger_at") or "").strip()
        if trigger_at:
            values.append(trigger_at)
    return tuple(values)


def _is_today_time_range_points_incomplete_or_recurring(
    input_message: str, decision: Any
) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not _input_has_today_time_range_points_request(current_user_text):
        return False
    action = str(_decision_value(decision, "action") or "").strip()
    if action != "batch":
        return True
    if _decision_has_recurring_create(decision):
        return True
    create_count = sum(
        1
        for operation in (_decision_value(decision, "operations") or [])
        if str(_operation_value(operation, "action") or "").strip() == "create"
    )
    return create_count < 2


def _input_has_today_time_range_points_request(text: str) -> bool:
    normalized = str(text or "").strip()
    if "今天" not in normalized or "这些时间点" not in normalized:
        return False
    if "提醒" not in normalized:
        return False
    return len(_CLOCK_RANGE_PATTERN.findall(normalized)) >= 2


def _input_has_large_today_time_range_points_request(text: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", text).strip()
    if not _input_has_today_time_range_points_request(current_user_text):
        return False
    return len(_CLOCK_RANGE_PATTERN.findall(current_user_text)) >= 4


def _decision_has_recurring_create(decision: Any) -> bool:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        return bool(str(_decision_value(decision, "rrule") or "").strip())
    if action != "batch":
        return False
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        if (
            str(_operation_value(operation, "action") or "").strip() == "create"
            and str(_operation_value(operation, "rrule") or "").strip()
        ):
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
    if _has_explicit_deadline(decision):
        return False
    rrules = [str(_decision_value(decision, "rrule") or "")]
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        rrules.append(str(_decision_value(operation, "rrule") or ""))
    if any(_is_bounded_high_frequency_rrule(rrule) for rrule in rrules):
        return False
    if any(_is_unbounded_high_frequency_rrule(rrule) for rrule in rrules):
        return True
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
        "每个整点",
        "整点",
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
        r"(?:到|直到)\s*(?:今天|今晚|明天|明晚|晚上|下午|中午|早上|上午)?\s*\d{1,2}\s*(?::\s*\d{1,2}|点)",
        r"(?:到|直到)\s*(?:今天|今晚|明天|明晚|晚上|下午|中午|早上|上午)?\s*[零一二两三四五六七八九十百半]+\s*点",
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


def _is_bounded_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    if not _is_high_frequency_rrule(rule):
        return False
    return "UNTIL=" in rule or "COUNT=" in rule


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
    if _input_has_next_whole_hour_reference(normalized):
        return False
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
            r"(?:提醒我一下|提醒我|提醒一下我|提醒一下|提醒|叫我|喊我)"
            r"(?:吧|哦|噢|啊|呀|啦|哈|呢)?[。.!！?？~～\s]*$",
            normalized,
        )
    )


def _input_has_event_time_with_vague_advance_request(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if not _VAGUE_ADVANCE_REMINDER_PATTERN.search(normalized):
        return False
    if not _BARE_CLOCK_PATTERN.search(normalized):
        return False
    return bool(_REMINDER_VERB_PATTERN.search(normalized))


def _input_is_plain_schedule_statement_without_reminder_request(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if _is_high_frequency_evidence(normalized):
        return False
    reminder_request_tokens = (
        "提醒",
        "叫我",
        "喊我",
        "通知",
        "闹钟",
        "叫醒",
        "监督",
        "打卡",
        "remind",
        "notify",
        "alarm",
        "wake me",
        "call me",
        "check in",
        "nudge",
    )
    if any(token in normalized for token in reminder_request_tokens):
        return False
    has_schedule_time = bool(
        _BARE_CLOCK_PATTERN.search(normalized)
        or _EXPLICIT_DATE_PATTERN.search(normalized)
        or re.search(r"\b(?:today|tomorrow|tonight)\b", normalized)
    )
    if not has_schedule_time:
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", normalized))


def _input_is_standalone_reminder_opt_out(text: str) -> bool:
    normalized = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", str(text or "")).strip().lower()
    if not normalized:
        return False
    if re.search(r"\b(?:cancel|delete|remove|stop)\b", normalized):
        return False
    if (
        _BARE_CLOCK_PATTERN.search(normalized)
        or _EXPLICIT_DATE_PATTERN.search(normalized)
        or re.search(r"\b(?:today|tomorrow|tonight|at|by|before|after)\b", normalized)
    ):
        return False
    words = re.findall(r"[a-z']+", normalized)
    if len(words) > 8:
        return False
    return bool(
        re.search(
            r"\b(?:no|without)\s+reminders?\b|"
            r"\bdon't\s+need\s+(?:any\s+)?reminders?\b|"
            r"\bdo\s+not\s+need\s+(?:any\s+)?reminders?\b|"
            r"\bno\s+need\s+for\s+reminders?\b",
            normalized,
        )
    )


def _input_is_standalone_reminder_acknowledgement(text: str) -> bool:
    normalized = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", str(text or "")).strip().lower()
    if not normalized:
        return False
    if (
        _BARE_CLOCK_PATTERN.search(normalized)
        or _EXPLICIT_DATE_PATTERN.search(normalized)
        or re.search(r"\b(?:today|tomorrow|tonight|at|by|before|after)\b", normalized)
    ):
        return False
    if re.search(r"取消|删除|停止|停掉|完成|做完|不用|不要|别提醒|不提醒", normalized):
        return False
    if not re.search(r"谢谢|谢啦|感谢|thanks?|thank\s+you", normalized, re.IGNORECASE):
        return False
    if not re.search(
        r"闹钟|提醒|叫我|喊我|alarm|reminder|notification|nudge",
        normalized,
        re.IGNORECASE,
    ):
        return False
    words = re.findall(r"[a-z']+", normalized)
    if words and len(words) > 8:
        return False
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    return len(chinese_chars) <= 12


def _input_is_reminder_behavior_meta_discussion(text: str) -> bool:
    normalized = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", str(text or "")).strip().lower()
    if not normalized:
        return False
    if (
        _BARE_CLOCK_PATTERN.search(normalized)
        or _EXPLICIT_DATE_PATTERN.search(normalized)
        or _RELATIVE_DELAY_PATTERN.search(normalized)
        or re.search(r"\b(?:today|tomorrow|tonight|at|by|before|after|in)\b", normalized)
    ):
        return False
    if not re.search(
        r"闹钟|提醒|叫我|喊我|alarm|reminder|notification|nudge",
        normalized,
        re.IGNORECASE,
    ):
        return False
    if re.search(r"取消|删除|停止|停掉|完成|做完|不用|不要|别提醒|不提醒", normalized):
        return False
    return bool(
        re.search(
            r"当.*闹钟|闹钟.*(?:就行|模式)|保持提醒|回复.*提醒|还得回复|"
            r"提醒.*(?:机制|规则|方式|逻辑|怎么|为什么|保持|回复)|"
            r"(?:how|why).*(?:reminder|alarm|notification)",
            normalized,
            re.IGNORECASE,
        )
    )


def _input_is_reminder_feature_work_topic(text: str) -> bool:
    normalized = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", str(text or "")).strip().lower()
    if not normalized:
        return False
    if _REMINDER_VERB_PATTERN.search(normalized):
        return False
    has_feature_reference = bool(
        re.search(
            r"提醒\s*(?:功能|能力|系统|模块)|"
            r"(?:reminder|alarm|notification)\s+"
            r"(?:feature|functionality|capability|system|module)",
            normalized,
            re.IGNORECASE,
        )
    )
    if not has_feature_reference:
        return False
    return bool(
        re.search(
            r"测试|增强|改进|优化|讨论|研究|能力|功能|"
            r"\b(?:test|improve|enhance|discuss|research)\b",
            normalized,
            re.IGNORECASE,
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
    if _input_is_standalone_reminder_opt_out(input_message):
        return _no_action_discussion_result()
    if _input_has_high_frequency_without_deadline(input_message):
        return _high_frequency_input_clarification_result()
    if _input_is_plain_schedule_statement_without_reminder_request(input_message):
        return _no_action_discussion_result()
    if fallback.error in {
        "ReminderDetectInvalidDecision",
        "ReminderDetectTimeout",
    } and _input_has_date_reference_without_clock(input_message):
        return _date_only_missing_time_clarification_result()
    if fallback.error in {
        "ReminderDetectInvalidDecision",
        "ReminderDetectTimeout",
    } and _input_has_event_time_with_vague_advance_request(input_message):
        return _advance_offset_missing_clarification_result()
    if fallback.error == "ReminderDetectInvalidDecision":
        if _input_has_concrete_time_without_reminder_content(input_message):
            return _missing_reminder_content_clarification_result()
        if _input_has_one_shot_deadline_without_trigger(input_message):
            return _deadline_without_trigger_clarification_result()
    return fallback


def _input_has_date_reference_without_clock(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not _REMINDER_VERB_PATTERN.search(current_user_text):
        return False
    if _input_has_concrete_time_without_reminder_content(current_user_text):
        return False
    has_date_reference = bool(
        _EXPLICIT_DATE_PATTERN.search(current_user_text)
        or _STANDALONE_DAY_OF_MONTH_PATTERN.search(current_user_text)
    )
    return has_date_reference and not bool(_BARE_CLOCK_PATTERN.search(current_user_text))


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


def _no_action_discussion_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={"action": "none", "intent_type": "discussion"},
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


def _ambiguous_time_range_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "这个时间范围不够精确，你想在具体几点提醒你？",
        },
        metadata={"durable_write": False},
    )


def _completion_condition_missing_time_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "我不能自动知道你什么时候完成。请告诉我具体什么时候提醒你。",
        },
        metadata={"durable_write": False},
    )


def _advance_offset_missing_clarification_result() -> CapabilityResult:
    return CapabilityResult(
        name="reminder",
        ok=True,
        content={
            "action": "clarify",
            "intent_type": "clarify",
            "summary": "你想提前多久提醒你？",
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
