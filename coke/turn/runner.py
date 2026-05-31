from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.turn.agent import AgentRequest, AgentResult, AgentToolPorts, InteractionAgent
from coke.turn.context import ContextAssembler, ToolProfile, TurnMode, TurnTrigger
from coke.turn.focus import FocusResolver
from coke.turn.freshness import FreshnessGuard
from coke.turn.locks import ConversationLockManager
from coke.turn.memory import MemoryManager, MemoryPort
from coke.turn.output_protocol import OutputProtocolValidator, ValidatedOutput
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.reference_resolver import ReferenceResolver
from coke.turn.semantic_interpreter import (
    SemanticDecision,
    SemanticInterpreter,
    SemanticInterpreterRequest,
)

WAITING_TEXT = "Still working on it."


class OutboundDeliveryPort(Protocol):
    def deliver(self, request: DeliveryRequest) -> Any: ...


class DeliveryLifecyclePort(Protocol):
    def record_delivery(
        self,
        *,
        trigger: TurnTrigger,
        request: DeliveryRequest,
        outcome: "DeliveryOutcome",
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DeliveryRequest:
    account_id: str
    conversation_id: str
    turn_id: str
    message_type: str
    visible_text: str
    idempotency_key: str
    message_id: str | None = None
    segments: tuple[str, ...] = ()
    context_token: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    status: str
    error_code: str | None = None
    attempt: Any | None = None


@dataclass(frozen=True, slots=True)
class TurnRunResult:
    turn_id: str
    trigger_id: str
    trigger_type: str
    disposition: str
    reason_code: str | None
    visible_text: str | None = None
    async_task_id: str | None = None


@dataclass(frozen=True, slots=True)
class _AsyncState:
    task_id: str
    turn_id: str
    trigger_id: str
    trigger_type: str
    conversation_id: str
    account_id: str
    based_on_inbound_seq: int | None
    context_token: str | None


class TurnRunner:
    def __init__(
        self,
        *,
        conversation_runtime: ConversationRuntimeService,
        lock_manager: ConversationLockManager,
        pre_llm_gate: PreLLMGateService,
        semantic_interpreter: SemanticInterpreter,
        memory_port: MemoryPort | None,
        interaction_agent: InteractionAgent,
        output_protocol: OutputProtocolValidator,
        outbound_delivery: OutboundDeliveryPort,
        tool_ports: AgentToolPorts | None = None,
        context_assembler: ContextAssembler | None = None,
        focus_resolver: FocusResolver | None = None,
        reference_resolver: ReferenceResolver | None = None,
        delivery_lifecycle: DeliveryLifecyclePort | None = None,
        now: Callable[[], datetime] | None = None,
        account_timezone: Callable[[str], str | None] | None = None,
    ) -> None:
        self.conversation_runtime = conversation_runtime
        self.lock_manager = lock_manager
        self.pre_llm_gate = pre_llm_gate
        self.semantic_interpreter = semantic_interpreter
        self.memory_manager = MemoryManager(memory_port)
        self.interaction_agent = interaction_agent
        self.output_protocol = output_protocol
        self.outbound_delivery = outbound_delivery
        self.delivery_lifecycle = delivery_lifecycle
        self.tool_ports = tool_ports or AgentToolPorts()
        self.context_assembler = context_assembler or ContextAssembler()
        self.focus_resolver = focus_resolver or FocusResolver()
        self.reference_resolver = reference_resolver or ReferenceResolver()
        self._now = now or (lambda: datetime.now(UTC))
        self._account_timezone = account_timezone
        self._async_states: dict[str, _AsyncState] = {}

    def run_inbound_turn(self, trigger: TurnTrigger) -> TurnRunResult:
        gate = self.pre_llm_gate.evaluate(trigger)
        if not gate.permitted:
            return self._run_access_denied_turn(trigger, gate)

        start = self.conversation_runtime.start_turn(
            conversation_id=trigger.conversation_id,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            mode=TurnMode.INTERACTIVE.value,
        )
        replay_result = self._replayed_result(start.replayed, start.turn.id, trigger)
        if replay_result is not None:
            return replay_result
        lock = self.lock_manager.acquire(trigger.conversation_id)
        if lock is None:
            disposition = self.conversation_runtime.mark_failed(
                start.turn.id, "conversation_lock_unavailable"
            )
            return self._result_from_disposition(
                turn_id=start.turn.id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )

        try:
            freshness_guard = FreshnessGuard(
                conversation_runtime=self.conversation_runtime,
                turn_id=start.turn.id,
                based_on_inbound_seq=start.turn.based_on_inbound_seq,
            )
            focus_subject = self.focus_resolver.resolve(trigger.conversation_id)
            semantic_decision = self.semantic_interpreter.interpret(
                SemanticInterpreterRequest(
                    account_id=trigger.account_id,
                    conversation_id=trigger.conversation_id,
                    payload=dict(trigger.payload),
                    trusted_facts=gate.trust_facts,
                    focus_subject=focus_subject,
                )
            )
            semantic_decision = _clear_reference_clarification_with_single_focus(
                semantic_decision, focus_subject
            )
            if semantic_decision.reply_necessity == "intentional_no_reply":
                disposition = self.conversation_runtime.commit_no_reply(
                    turn_id=start.turn.id,
                    based_on_inbound_seq=start.turn.based_on_inbound_seq,
                    reason_code="intentional_no_reply",
                )
                return self._result_from_disposition(
                    turn_id=start.turn.id,
                    trigger=trigger,
                    disposition=disposition.disposition,
                    reason_code=disposition.reason_code,
                )

            trusted_facts = _trusted_facts_for_agent(
                gate.trust_facts,
                trigger=trigger,
                semantic_decision=semantic_decision,
                now=self._now,
                account_timezone=self._account_timezone,
            )
            context = self.context_assembler.build(
                trigger=trigger,
                trusted_facts=trusted_facts,
                semantic_decision=semantic_decision,
                focus_subject=focus_subject,
                reference_resolution=self.reference_resolver.resolve_all([]),
                memory_context=self.memory_manager.load(
                    account_id=trigger.account_id,
                    conversation_id=trigger.conversation_id,
                    long_term_enabled=bool(
                        gate.trust_facts.get("memory_enabled", True)
                    ),
                ),
                freshness_guard=freshness_guard,
                tool_profile=(
                    ToolProfile.clarification()
                    if semantic_decision.required_clarification != "none"
                    else ToolProfile.interactive(self.tool_ports)
                ),
                onboarding_guidance_required=gate.activation_guidance_required,
                turn_source=trusted_facts["turn_source"],
            )
            return self._invoke_agent_and_record(trigger, context, semantic_decision)
        except ConversationRuntimeError as error:
            return self._conversation_runtime_error_result(
                start.turn.id, trigger, error
            )
        finally:
            lock.release()

    def run_render_turn(self, trigger: TurnTrigger) -> TurnRunResult:
        gate = GateDecision.allowed(trust_facts={"account_id": trigger.account_id})
        return self._run_render_with_gate(
            trigger=trigger,
            gate=gate,
            constrained=False,
        )

    def complete_async_reply(self, task_id: str | None) -> TurnRunResult:
        if task_id is None or task_id not in self._async_states:
            raise ValueError("async_task_not_found")
        state = self._async_states.pop(task_id)
        result = self.interaction_agent.complete_async(task_id)
        trigger = TurnTrigger(
            trigger_id=state.trigger_id,
            trigger_type=state.trigger_type,
            mode=TurnMode.INTERACTIVE,
            conversation_id=state.conversation_id,
            account_id=state.account_id,
            payload=(
                {"context_token": state.context_token} if state.context_token else {}
            ),
        )
        if result.timed_out:
            disposition = self.conversation_runtime.mark_failed(
                state.turn_id, "async_timeout_after_budget"
            )
            return self._result_from_disposition(
                turn_id=state.turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )
        validated = self.output_protocol.validate_first_answer(result.output)
        return self._record_validated_output(
            turn_id=state.turn_id,
            trigger=trigger,
            based_on_inbound_seq=state.based_on_inbound_seq,
            validated=validated,
        )

    def _run_access_denied_turn(
        self, trigger: TurnTrigger, gate: GateDecision
    ) -> TurnRunResult:
        render_trigger = TurnTrigger(
            trigger_id=f"{trigger.trigger_id}:access_denied",
            trigger_type="AccessDeniedTurn",
            mode=TurnMode.RENDER,
            conversation_id=trigger.conversation_id,
            account_id=trigger.account_id,
            channel_identity_id=trigger.channel_identity_id,
            payload={
                "access_denied": True,
                "denial_reason": gate.denial_reason,
                "facts": gate.access_facts,
            },
        )
        return self._run_render_with_gate(
            trigger=render_trigger,
            gate=GateDecision.allowed(
                trust_facts={
                    "account_id": trigger.account_id,
                    "denial_reason": gate.denial_reason,
                    **gate.access_facts,
                }
            ),
            constrained=True,
        )

    def _run_render_with_gate(
        self,
        *,
        trigger: TurnTrigger,
        gate: GateDecision,
        constrained: bool,
    ) -> TurnRunResult:
        start = self.conversation_runtime.start_turn(
            conversation_id=trigger.conversation_id,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            mode=TurnMode.RENDER.value,
        )
        replay_result = self._replayed_result(start.replayed, start.turn.id, trigger)
        if replay_result is not None:
            return replay_result
        lock = self.lock_manager.acquire(trigger.conversation_id)
        if lock is None:
            disposition = self.conversation_runtime.mark_failed(
                start.turn.id, "conversation_lock_unavailable"
            )
            return self._result_from_disposition(
                turn_id=start.turn.id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )
        try:
            freshness_guard = FreshnessGuard(
                conversation_runtime=self.conversation_runtime,
                turn_id=start.turn.id,
                based_on_inbound_seq=start.turn.based_on_inbound_seq,
            )
            trusted_facts = _trusted_facts_for_agent(
                gate.trust_facts,
                trigger=trigger,
                semantic_decision=None,
                now=self._now,
                account_timezone=self._account_timezone,
            )
            context = self.context_assembler.build(
                trigger=trigger,
                trusted_facts=trusted_facts,
                semantic_decision=None,
                focus_subject=None,
                reference_resolution=None,
                memory_context=None,
                freshness_guard=freshness_guard,
                tool_profile=ToolProfile.render(constrained=constrained),
                turn_source=trusted_facts["turn_source"],
            )
            return self._invoke_agent_and_record(
                trigger, context, semantic_decision=None
            )
        except ConversationRuntimeError as error:
            return self._conversation_runtime_error_result(
                start.turn.id, trigger, error
            )
        finally:
            lock.release()

    def _invoke_agent_and_record(
        self,
        trigger: TurnTrigger,
        context: Any,
        semantic_decision: SemanticDecision | None,
    ) -> TurnRunResult:
        agent_request = AgentRequest(
            turn_id=context.freshness_guard.turn_id,
            conversation_id=trigger.conversation_id,
            account_id=trigger.account_id,
            mode=trigger.mode,
            trigger_type=trigger.trigger_type,
            payload=trigger.payload,
            trusted_facts=context.trusted_facts,
            tool_profile=context.tool_profile,
            freshness_guard=context.freshness_guard,
            context=context,
        )
        agent_result = self.interaction_agent.invoke(agent_request)
        if agent_result.timed_out:
            return self._record_pending_async(trigger, context, agent_result)
        validated = self.output_protocol.validate_first_answer(agent_result.output)
        if not validated.valid:
            agent_result = self.interaction_agent.invoke(
                _protocol_retry_request(agent_request, validated)
            )
            if agent_result.timed_out:
                return self._record_pending_async(trigger, context, agent_result)
            validated = self.output_protocol.validate_first_answer(agent_result.output)
        return self._record_validated_output(
            turn_id=context.freshness_guard.turn_id,
            trigger=trigger,
            based_on_inbound_seq=context.freshness_guard.based_on_inbound_seq,
            validated=validated,
        )

    def _record_pending_async(
        self,
        trigger: TurnTrigger,
        context: Any,
        agent_result: AgentResult,
    ) -> TurnRunResult:
        if agent_result.task_id is None:
            disposition = self.conversation_runtime.mark_failed(
                context.freshness_guard.turn_id,
                "async_task_missing",
            )
            return self._result_from_disposition(
                turn_id=context.freshness_guard.turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )
        context.freshness_guard.guard_state_change()
        disposition = self.conversation_runtime.mark_pending_async_reply(
            turn_id=context.freshness_guard.turn_id,
            based_on_inbound_seq=context.freshness_guard.based_on_inbound_seq,
            reason_code="sync_timeout",
        )
        waiting_message = self.conversation_runtime.record_outbound_message(
            context.freshness_guard.turn_id,
            WAITING_TEXT,
            segment_index=0,
            payload={"message_type": "waiting"},
        )
        self.outbound_delivery.deliver(
            DeliveryRequest(
                account_id=trigger.account_id,
                conversation_id=trigger.conversation_id,
                turn_id=context.freshness_guard.turn_id,
                message_type="waiting",
                visible_text=WAITING_TEXT,
                idempotency_key=f"{trigger.trigger_id}:waiting",
                message_id=waiting_message.id,
                segments=(WAITING_TEXT,),
                context_token=_context_token_from_trigger(trigger),
            )
        )
        self._async_states[agent_result.task_id] = _AsyncState(
            task_id=agent_result.task_id,
            turn_id=context.freshness_guard.turn_id,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            conversation_id=trigger.conversation_id,
            account_id=trigger.account_id,
            based_on_inbound_seq=context.freshness_guard.based_on_inbound_seq,
            context_token=_context_token_from_trigger(trigger),
        )
        return self._result_from_disposition(
            turn_id=context.freshness_guard.turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=WAITING_TEXT,
            async_task_id=agent_result.task_id,
        )

    def _record_validated_output(
        self,
        *,
        turn_id: str,
        trigger: TurnTrigger,
        based_on_inbound_seq: int | None,
        validated: ValidatedOutput,
    ) -> TurnRunResult:
        if not validated.valid:
            disposition = self.conversation_runtime.mark_failed(
                turn_id=turn_id,
                reason_code=validated.reason_code or "invalid_output_protocol",
            )
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )
        if validated.kind == "no_reply":
            disposition = self.conversation_runtime.commit_no_reply(
                turn_id=turn_id,
                based_on_inbound_seq=based_on_inbound_seq,
                reason_code="intentional_no_reply",
            )
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )

        self.conversation_runtime.guard_state_change(turn_id, based_on_inbound_seq)
        disposition = self.conversation_runtime.commit_reply(
            turn_id=turn_id,
            based_on_inbound_seq=based_on_inbound_seq,
            segments=validated.segments,
            reason_code=validated.reason_code or "reply_ready",
        )
        self.conversation_runtime.guard_state_change(turn_id, based_on_inbound_seq)
        visible_text = "\n".join(validated.segments)
        outbound_messages = [
            message
            for message in self.conversation_runtime.outbound_messages_for_turn(turn_id)
            if (message.segment_index or 0) > 0
        ]
        for request in self._reply_delivery_requests(
            trigger=trigger,
            turn_id=turn_id,
            visible_text=visible_text,
            segments=validated.segments,
            outbound_messages=outbound_messages,
        ):
            outcome = self._deliver(request)
            self._record_delivery_lifecycle(trigger, request, outcome)
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=visible_text,
        )

    def _replayed_result(
        self,
        replayed: bool,
        turn_id: str,
        trigger: TurnTrigger,
    ) -> TurnRunResult | None:
        if not replayed:
            return None
        try:
            disposition = self.conversation_runtime.get_disposition(turn_id)
        except ConversationRuntimeError:
            return None
        visible_text = None
        async_task_id = None
        if disposition.disposition == "replied":
            messages = self.conversation_runtime.outbound_messages_for_turn(turn_id)
            visible_text = "\n".join(
                message.text or ""
                for message in sorted(
                    messages,
                    key=lambda message: (message.segment_index or 0, message.id),
                )
            )
        elif disposition.disposition == "pending_async_reply":
            async_task_id = None
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=visible_text,
            async_task_id=async_task_id,
        )

    def _reply_delivery_requests(
        self,
        *,
        trigger: TurnTrigger,
        turn_id: str,
        visible_text: str,
        segments: tuple[str, ...],
        outbound_messages: list[Any],
    ) -> list[DeliveryRequest]:
        recipients = _recipient_account_ids(trigger)
        multiple = len(recipients) > 1
        message_id = _first_outbound_message_id(outbound_messages)
        requests: list[DeliveryRequest] = []
        for account_id in recipients:
            idempotency_key = f"{turn_id}:reply"
            if multiple or account_id != trigger.account_id:
                idempotency_key = f"{idempotency_key}:{account_id}"
            requests.append(
                DeliveryRequest(
                    account_id=account_id,
                    conversation_id=trigger.conversation_id,
                    turn_id=turn_id,
                    message_type="reply",
                    visible_text=visible_text,
                    idempotency_key=idempotency_key,
                    message_id=message_id,
                    segments=segments,
                    context_token=_context_token_from_trigger(trigger),
                )
            )
        return requests

    def _deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        try:
            raw_outcome = self.outbound_delivery.deliver(request)
        except Exception as error:
            return DeliveryOutcome(
                status="failed",
                error_code=str(getattr(error, "code", None) or type(error).__name__),
            )
        return DeliveryOutcome(
            status=str(getattr(raw_outcome, "status", "delivered")),
            error_code=getattr(raw_outcome, "error_code", None),
            attempt=raw_outcome,
        )

    def _record_delivery_lifecycle(
        self,
        trigger: TurnTrigger,
        request: DeliveryRequest,
        outcome: DeliveryOutcome,
    ) -> None:
        if self.delivery_lifecycle is None:
            return
        self.delivery_lifecycle.record_delivery(
            trigger=trigger,
            request=request,
            outcome=outcome,
        )

    def _conversation_runtime_error_result(
        self,
        turn_id: str,
        trigger: TurnTrigger,
        error: ConversationRuntimeError,
    ) -> TurnRunResult:
        if error.code == "turn_superseded":
            disposition = self.conversation_runtime.get_disposition(turn_id)
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
            )
        disposition = self.conversation_runtime.mark_failed(turn_id, error.code)
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
        )

    def _result_from_disposition(
        self,
        *,
        turn_id: str,
        trigger: TurnTrigger,
        disposition: str,
        reason_code: str | None,
        visible_text: str | None = None,
        async_task_id: str | None = None,
    ) -> TurnRunResult:
        return TurnRunResult(
            turn_id=turn_id,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            disposition=disposition,
            reason_code=reason_code,
            visible_text=visible_text,
            async_task_id=async_task_id,
        )


def _protocol_retry_request(
    request: AgentRequest, validated: ValidatedOutput
) -> AgentRequest:
    return replace(
        request,
        trusted_facts={
            **dict(request.trusted_facts),
            "protocol_retry": {
                "reason_code": validated.reason_code or "invalid_output_protocol",
                "attempt": 2,
                "guidance": validated.retry_guidance,
            },
        },
    )


def _trusted_facts_for_agent(
    trust_facts: dict[str, Any],
    *,
    trigger: TurnTrigger,
    semantic_decision: SemanticDecision | None,
    now: Callable[[], datetime],
    account_timezone: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    facts = {
        **dict(trust_facts),
        "turn_source": _turn_source_for_trigger(trigger),
    }
    facts.update(
        _current_time_facts(
            facts,
            trigger=trigger,
            now=now,
            account_timezone=account_timezone,
        )
    )
    if semantic_decision is not None:
        facts["semantic_decision"] = _semantic_decision_fact(semantic_decision)
    if (
        semantic_decision is not None
        and semantic_decision.required_clarification != "none"
    ):
        facts["required_clarification"] = {
            "signal": semantic_decision.required_clarification,
            "ambiguity": semantic_decision.ambiguity,
            "instruction": "Ask exactly this clarification before any domain action.",
        }
    return facts


REFERENCE_CLARIFICATIONS = {"ask_context", "ask_reference_choice"}
REFERENCE_AMBIGUITIES = {"ambiguous_reference", "missing_context"}
REMINDER_FOCUS_ACTIONS = {
    "update_reminder",
    "complete_reminder",
    "delete_reminder",
    "clear_trigger_time",
    "schedule_unscheduled",
}


def _clear_reference_clarification_with_single_focus(
    decision: SemanticDecision,
    focus_subject: Any | None,
) -> SemanticDecision:
    if not _has_single_focus(focus_subject, "reminder"):
        return decision
    if decision.intent_family != "reminder_op":
        return decision
    if decision.intent_action not in REMINDER_FOCUS_ACTIONS:
        return decision
    if decision.required_clarification not in REFERENCE_CLARIFICATIONS:
        return decision
    if decision.ambiguity not in REFERENCE_AMBIGUITIES:
        return decision
    return replace(decision, ambiguity="clear", required_clarification="none")


def _has_single_focus(focus_subject: Any | None, subject_type: str) -> bool:
    if focus_subject is None:
        return False
    if isinstance(focus_subject, Mapping):
        focus_type = focus_subject.get("subject_type")
        object_ids = focus_subject.get("object_ids")
    else:
        focus_type = getattr(focus_subject, "subject_type", None)
        object_ids = getattr(focus_subject, "object_ids", None)
    if focus_type != subject_type or isinstance(object_ids, str):
        return False
    try:
        return len(tuple(object_ids or ())) == 1
    except TypeError:
        return False


def _current_time_facts(
    facts: dict[str, Any],
    *,
    trigger: TurnTrigger,
    now: Callable[[], datetime],
    account_timezone: Callable[[str], str | None] | None,
) -> dict[str, str]:
    timezone_name, timezone = _timezone_for_agent(
        facts,
        trigger=trigger,
        account_timezone=account_timezone,
    )
    current = now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return {
        "default_timezone": timezone_name,
        "current_time": current.astimezone(timezone).isoformat(),
    }


def _timezone_for_agent(
    facts: dict[str, Any],
    *,
    trigger: TurnTrigger,
    account_timezone: Callable[[str], str | None] | None,
) -> tuple[str, ZoneInfo | Any]:
    for candidate in (
        facts.get("default_timezone"),
        trigger.payload.get("default_timezone"),
        trigger.payload.get("timezone"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return _zoneinfo_or_utc(candidate.strip())
    if account_timezone is not None:
        candidate = account_timezone(trigger.account_id)
        if isinstance(candidate, str) and candidate.strip():
            return _zoneinfo_or_utc(candidate.strip())
    return "UTC", UTC


def _zoneinfo_or_utc(timezone_name: str) -> tuple[str, ZoneInfo | Any]:
    try:
        return timezone_name, ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return "UTC", UTC


def _semantic_decision_fact(decision: SemanticDecision) -> dict[str, Any]:
    return asdict(decision)


def _turn_source_for_trigger(trigger: TurnTrigger) -> dict[str, Any]:
    trigger_type = trigger.trigger_type
    if trigger_type == "InboundTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": True,
            "instruction": (
                "This is a real message from the user. Reply to the user's "
                "latest message."
            ),
        }
    if trigger_type == "ReminderFireTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render the reminder fact to the user. Do not answer the "
                "reminder title as if the user said it."
            ),
        }
    if trigger_type == "ProactiveFireTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "This turn was initiated by Coke. Render the planned action. "
                "Do not answer it as a user question."
            ),
        }
    if trigger_type == "NotificationTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render the notification fact. Do not answer it as if the user "
                "said it."
            ),
        }
    if trigger_type == "AccessDeniedTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render the access recovery fact. Do not continue normal user "
                "intent execution."
            ),
        }
    if trigger_type == "NightlySummaryTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render the no-trigger-time reminder summary. Do not treat the "
                "summary items as a user message."
            ),
        }
    if trigger_type == "UndeliveredResendTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render previously undelivered reminder facts. Do not present "
                "them as new user requests."
            ),
        }
    return {
        "trigger_type": trigger_type,
        "user_spoke_this_turn": False,
        "instruction": (
            "Render the trusted trigger fact. Do not answer it as a user message."
        ),
    }


def _recipient_account_ids(trigger: TurnTrigger) -> list[str]:
    if trigger.trigger_type == "NotificationTurn":
        raw_recipients = trigger.payload.get("recipient_account_ids")
        if isinstance(raw_recipients, list | tuple):
            recipients = [
                account_id
                for account_id in raw_recipients
                if isinstance(account_id, str) and account_id
            ]
            if recipients:
                return list(dict.fromkeys(recipients))
    return [trigger.account_id]


def _first_outbound_message_id(outbound_messages: list[Any]) -> str | None:
    if not outbound_messages:
        return None
    ordered = sorted(
        outbound_messages,
        key=lambda message: (getattr(message, "segment_index", None) or 0, message.id),
    )
    return ordered[0].id


def _context_token_from_trigger(trigger: TurnTrigger) -> str | None:
    direct = trigger.payload.get("context_token")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    nested = trigger.payload.get("payload")
    if isinstance(nested, dict):
        token = nested.get("context_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None
