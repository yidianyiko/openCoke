from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.conversation_runtime.models import (
    TERMINAL_DISPOSITIONS,
    ConversationRuntimeError,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.social_scheduling.models import SocialSchedulingOutcome
from coke.observability.turn_latency import turn_latency_span
from coke.turn.action_runner import ActionRunner
from coke.turn.agent import AgentRequest, AgentResult, AgentToolPorts, InteractionAgent
from coke.turn.context import ContextAssembler, ToolProfile, TurnMode, TurnTrigger
from coke.turn.focus import FocusResolver
from coke.turn.freshness import FreshnessGuard
from coke.turn.locks import ConversationLockManager
from coke.turn.memory import MemoryManager, MemoryPort
from coke.turn.output_protocol import OutputProtocolValidator, ValidatedOutput
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.reference_resolver import ReferenceResolver
from coke.turn.routing import derive_route
from coke.turn.semantic_interpreter import (
    SemanticDecision,
    SemanticInterpreter,
    SemanticInterpreterRequest,
)
from coke.turn.streaming import is_streaming_eligible
from coke.turn.v2.pipeline import SegmentDeliveryPort, TurnPipelineRequest

WAITING_TEXT = "我还在处理，稍等一下。"
LOGGER = logging.getLogger(__name__)
NOTIFICATION_VISIBLE_REPLY_REQUIRED = "notification_requires_visible_reply"
REMINDER_FIRE_VISIBLE_REPLY_REQUIRED = "reminder_fire_requires_visible_reply"
REMINDER_FIRE_FACT_MISMATCH = "reminder_fire_fact_mismatch"
INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON = "replaced_by_newer_inbound"
_CLOSE_BOUNDARY_OBSERVER: ContextVar[Callable[[], None] | None] = ContextVar(
    "coke_close_boundary_observer",
    default=None,
)


@contextmanager
def close_boundary_observer(observer: Callable[[], None]) -> Iterator[None]:
    token = _CLOSE_BOUNDARY_OBSERVER.set(observer)
    try:
        yield
    finally:
        _CLOSE_BOUNDARY_OBSERVER.reset(token)


def notify_close_boundary_committed() -> None:
    observer = _CLOSE_BOUNDARY_OBSERVER.get()
    if observer is not None:
        observer()


def is_newer_inbound_cancellation(error: asyncio.CancelledError) -> bool:
    return error.args[:1] == (INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON,)


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


class ReminderFireFactsPort(Protocol):
    def reminder_fire_render_facts(
        self,
        *,
        owner_account_id: str,
        fire_ids: list[str],
        viewer_account_id: str | None = None,
    ) -> list[Any]: ...


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
    delivery_source: str | None = None
    delivery_intent: str | None = None
    retry_attempt: int | None = None
    traceparent: str | None = None
    container: str | None = None
    context_token_source: str | None = None
    context_token_age_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    status: str
    error_code: str | None = None
    attempt: Any | None = None


WAITING_RETRYABLE_ERROR_CODES = frozenset(
    {
        "provider_network_error",
        "provider_down",
        "network_error",
        "transport_error",
        "request_timeout",
        "timeout",
        "connection_error",
        "http_5xx",
        "provider_timeout",
    }
)
WAITING_NON_RETRYABLE_ERROR_FRAGMENTS = (
    "context_token_required",
    "invalid_context_token",
    "invalid_token",
    "ret_-2",
    "session_window",
    "session_expired",
    "reconnection_required",
)


class WaitingDeliveryCircuitBreaker:
    def __init__(self, *, failure_threshold: int = 3) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self._failures_by_route: dict[tuple[str, str], int] = {}

    def allow(self, route_key: tuple[str, str]) -> bool:
        return self._failures_by_route.get(route_key, 0) < self.failure_threshold

    def observe(self, route_key: tuple[str, str], outcome: DeliveryOutcome) -> None:
        if outcome.status in {"sent", "delivered"}:
            self._failures_by_route.pop(route_key, None)
            return
        if not _waiting_delivery_retryable(outcome):
            return
        self._failures_by_route[route_key] = (
            self._failures_by_route.get(route_key, 0) + 1
        )


def send_waiting_delivery(
    *,
    outbound_delivery: OutboundDeliveryPort,
    account_id: str,
    conversation_id: str,
    turn_id: str,
    message_id: str | None,
    context_token: str | None,
    delivery_source: str,
    traceparent: str | None,
    context_token_source: str | None,
    context_token_age_seconds: int | None,
    turn_disposition: Callable[[str], Any] | None = None,
    retry_jitter: Callable[[int], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    circuit_breaker: WaitingDeliveryCircuitBreaker | None = None,
    logger: logging.Logger | None = None,
) -> tuple[DeliveryOutcome, ...]:
    retry_jitter = retry_jitter or (lambda _attempt: 0.25)
    sleep = sleep or time.sleep
    logger = logger or LOGGER
    outcomes: list[DeliveryOutcome] = []
    last_route_key: tuple[str, str] = (account_id, "unknown")
    for attempt_number in (1, 2):
        if attempt_number == 2:
            previous = outcomes[-1] if outcomes else None
            if previous is None or not _waiting_delivery_retryable(previous):
                break
            last_route_key = _waiting_delivery_route_key(account_id, previous)
            if circuit_breaker is not None and not circuit_breaker.allow(
                last_route_key
            ):
                logger.warning(
                    "waiting_reply_delivery_circuit_open",
                    extra={
                        "turn_id": turn_id,
                        "conversation_id": conversation_id,
                        "account_id": account_id,
                        "route_key": last_route_key[1],
                    },
                )
                break
            if _waiting_turn_terminal(turn_id, turn_disposition):
                break
            delay = max(0.0, float(retry_jitter(attempt_number)))
            if delay:
                sleep(delay)
            if _waiting_turn_terminal(turn_id, turn_disposition):
                break
        intent = f"{turn_id}:waiting:{attempt_number}"
        request = DeliveryRequest(
            account_id=account_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            message_type="waiting",
            visible_text=WAITING_TEXT,
            idempotency_key=intent,
            message_id=message_id,
            segments=(WAITING_TEXT,),
            context_token=context_token,
            delivery_source=delivery_source,
            delivery_intent=intent,
            retry_attempt=attempt_number,
            traceparent=traceparent,
            container=os.environ.get("HOSTNAME"),
            context_token_source=context_token_source,
            context_token_age_seconds=context_token_age_seconds,
        )
        outcome = _safe_delivery_outcome(outbound_delivery, request)
        outcomes.append(outcome)
        route_key = _waiting_delivery_route_key(account_id, outcome)
        last_route_key = route_key
        if circuit_breaker is not None:
            circuit_breaker.observe(route_key, outcome)
        if outcome.status == "failed":
            logger.warning(
                "waiting_reply_delivery_failed",
                extra={
                    "turn_id": turn_id,
                    "conversation_id": conversation_id,
                    "account_id": account_id,
                    "delivery_source": delivery_source,
                    "delivery_intent": intent,
                    "retry_attempt": attempt_number,
                    "error_code": outcome.error_code,
                    "route_key": route_key[1],
                    "traceparent": traceparent,
                    "context_token_source": context_token_source,
                    "context_token_age_seconds": context_token_age_seconds,
                },
            )
        else:
            logger.info(
                "waiting_reply_delivery_scheduled",
                extra={
                    "turn_id": turn_id,
                    "conversation_id": conversation_id,
                    "account_id": account_id,
                    "delivery_source": delivery_source,
                    "delivery_intent": intent,
                    "retry_attempt": attempt_number,
                    "delivery_status": outcome.status,
                    "route_key": route_key[1],
                },
            )
            break
    return tuple(outcomes)


def _safe_delivery_outcome(
    outbound_delivery: OutboundDeliveryPort,
    request: DeliveryRequest,
) -> DeliveryOutcome:
    try:
        raw_outcome = outbound_delivery.deliver(request)
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


def _waiting_delivery_retryable(outcome: DeliveryOutcome) -> bool:
    if outcome.status != "failed":
        return False
    error_code = str(outcome.error_code or "").casefold()
    if not error_code:
        return False
    if any(
        fragment in error_code for fragment in WAITING_NON_RETRYABLE_ERROR_FRAGMENTS
    ):
        return False
    return error_code in WAITING_RETRYABLE_ERROR_CODES


def _waiting_delivery_route_key(
    account_id: str,
    outcome: DeliveryOutcome,
) -> tuple[str, str]:
    attempt = outcome.attempt
    route_id = getattr(attempt, "route_id", None)
    provider_type = getattr(attempt, "provider_type", None)
    provider_route = route_id or provider_type or "unknown"
    return (account_id, str(provider_route))


def _waiting_turn_terminal(
    turn_id: str,
    turn_disposition: Callable[[str], Any] | None,
) -> bool:
    if turn_disposition is None:
        return False
    try:
        disposition = turn_disposition(turn_id)
    except Exception:
        return False
    value = getattr(disposition, "disposition", disposition)
    return str(value) in TERMINAL_DISPOSITIONS


@dataclass(frozen=True, slots=True)
class TurnRunResult:
    turn_id: str
    trigger_id: str
    trigger_type: str
    disposition: str
    reason_code: str | None
    visible_text: str | None = None
    async_task_id: str | None = None
    latest_causal_inbound_event_id: str | None = None
    coalesced_causal_inbound_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _AsyncState:
    task_id: str
    turn_id: str
    trigger_id: str
    trigger_type: str
    conversation_id: str
    account_id: str
    context_token: str | None
    onboarding_guidance_required: bool = False
    current_input_messages: tuple[Any, ...] = ()


class _V2RunnerDelivery(SegmentDeliveryPort):
    def __init__(self, runner: Any, trigger: TurnTrigger) -> None:
        self.runner = runner
        self.trigger = trigger
        self.outcomes: list[DeliveryOutcome] = []
        self.delivered_segment_count = 0
        self.close_boundary_committed = False

    def deliver(self, turn_id: str, segment: str) -> None:
        self.delivered_segment_count += 1
        outbound_messages = self._outbound_messages(turn_id)
        if outbound_messages and not self.close_boundary_committed:
            self.runner._commit_close_boundary()
            self.close_boundary_committed = True
        for request in self.runner._reply_delivery_requests(
            trigger=self.trigger,
            turn_id=turn_id,
            visible_text=segment,
            segments=(segment,),
            outbound_messages=outbound_messages,
            start_index=self.delivered_segment_count,
        ):
            outcome = self.runner._deliver(request)
            self.outcomes.append(outcome)
            self.runner._record_delivery_lifecycle(self.trigger, request, outcome)

    def _outbound_messages(self, turn_id: str) -> list[Any]:
        try:
            return [
                message
                for message in self.runner.conversation_runtime.outbound_messages_for_turn(
                    turn_id
                )
                if (getattr(message, "segment_index", None) or 0) > 0
            ]
        except ConversationRuntimeError:
            return []


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
        reminder_fire_facts: ReminderFireFactsPort | None = None,
        staged_command_materializer: Any | None = None,
        social_scheduling_service: Any | None = None,
        now: Callable[[], datetime] | None = None,
        account_timezone: Callable[[str], str | None] | None = None,
        claim_boundary_committer: Callable[[], None] | None = None,
        close_boundary_committer: Callable[[], None] | None = None,
        lock_wait_interval_s: float = 0.05,
        waiting_retry_jitter: Callable[[int], float] | None = None,
        waiting_retry_sleep: Callable[[float], None] | None = None,
        waiting_circuit_breaker: WaitingDeliveryCircuitBreaker | None = None,
        turn_pipeline: Any | None = None,
    ) -> None:
        self.conversation_runtime = conversation_runtime
        self.lock_manager = lock_manager
        self.pre_llm_gate = pre_llm_gate
        self.semantic_interpreter = semantic_interpreter
        self.memory_manager = MemoryManager(memory_port)
        self.interaction_agent = interaction_agent
        self.output_protocol = output_protocol
        self.action_runner = ActionRunner()
        self.outbound_delivery = outbound_delivery
        self.delivery_lifecycle = delivery_lifecycle
        self.reminder_fire_facts = reminder_fire_facts
        self.staged_command_materializer = staged_command_materializer
        self.social_scheduling_service = social_scheduling_service
        self.turn_pipeline = turn_pipeline
        self.tool_ports = tool_ports or AgentToolPorts()
        self.context_assembler = context_assembler or ContextAssembler()
        self.focus_resolver = focus_resolver or FocusResolver()
        self.reference_resolver = reference_resolver or ReferenceResolver()
        self._now = now or (lambda: datetime.now(UTC))
        self._account_timezone = account_timezone
        self._claim_boundary_committer = claim_boundary_committer or (lambda: None)
        self._close_boundary_committer = close_boundary_committer or (lambda: None)
        self._lock_wait_interval_s = lock_wait_interval_s
        self._waiting_retry_jitter = waiting_retry_jitter
        self._waiting_retry_sleep = waiting_retry_sleep
        self._waiting_circuit_breaker = (
            waiting_circuit_breaker or WaitingDeliveryCircuitBreaker()
        )
        self._async_states: dict[str, _AsyncState] = {}

    def run_inbound_turn(self, trigger: TurnTrigger) -> TurnRunResult:
        try:
            start = self.conversation_runtime.start_turn(
                conversation_id=trigger.conversation_id,
                trigger_id=trigger.trigger_id,
                trigger_type=trigger.trigger_type,
                mode=TurnMode.INTERACTIVE.value,
            )
        except ConversationRuntimeError as error:
            if error.code == "no_open_inbound_window":
                return self._result_from_disposition(
                    turn_id=trigger.trigger_id,
                    trigger=trigger,
                    disposition="superseded",
                    reason_code="input_window_already_closed",
                )
            raise
        self._commit_claim_boundary()
        with turn_latency_span(
            "turn.total",
            turn_id=start.turn.id,
            trigger_type=trigger.trigger_type,
            mode=TurnMode.INTERACTIVE.value,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
        ):
            replay_result = self._replayed_result(
                start.replayed,
                start.turn.id,
                trigger,
                current_input_messages=start.input_messages,
            )
            if replay_result is not None:
                return replay_result
            gate = self.pre_llm_gate.evaluate(trigger)
            self._commit_claim_boundary()
            if not gate.permitted:
                return self._run_access_denied_turn(
                    trigger=trigger,
                    gate=gate,
                    turn_id=start.turn.id,
                    input_from_seq=start.turn.input_from_seq,
                    input_to_seq=start.turn.input_to_seq,
                    current_input_messages=start.input_messages,
                )

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
                    current_input_messages=start.input_messages,
                )

            try:
                freshness_guard = FreshnessGuard(
                    conversation_runtime=self.conversation_runtime,
                    turn_id=start.turn.id,
                    input_from_seq=start.turn.input_from_seq,
                    input_to_seq=start.turn.input_to_seq,
                )
                focus_subject = self.focus_resolver.resolve(trigger.conversation_id)
                if self._use_v2_turn_pipeline(trigger):
                    return self._run_v2_inbound_turn(
                        trigger=trigger,
                        start=start,
                        gate=gate,
                        freshness_guard=freshness_guard,
                        focus_subject=focus_subject,
                    )
                with turn_latency_span(
                    "turn.semantic_interpreter",
                    turn_id=start.turn.id,
                    trigger_type=trigger.trigger_type,
                    mode=TurnMode.INTERACTIVE.value,
                    account_id=trigger.account_id,
                    conversation_id=trigger.conversation_id,
                ):
                    semantic_decision = self.semantic_interpreter.interpret(
                        SemanticInterpreterRequest(
                            account_id=trigger.account_id,
                            conversation_id=trigger.conversation_id,
                            payload=dict(trigger.payload),
                            trusted_facts=gate.trust_facts,
                            focus_subject=focus_subject,
                        )
                    )
                    semantic_decision = (
                        _clear_reference_clarification_with_single_focus(
                            semantic_decision, focus_subject
                        )
                    )
                    semantic_decision = (
                        _clear_context_clarification_for_followup_answer(
                            semantic_decision, trigger
                        )
                    )
                    semantic_decision = _require_agent_visibility_for_inbound_no_reply(
                        semantic_decision
                    )

                with turn_latency_span(
                    "turn.context_assembly",
                    turn_id=start.turn.id,
                    trigger_type=trigger.trigger_type,
                    mode=TurnMode.INTERACTIVE.value,
                    account_id=trigger.account_id,
                    conversation_id=trigger.conversation_id,
                ):
                    trusted_facts = _trusted_facts_for_agent(
                        gate.trust_facts,
                        trigger=trigger,
                        semantic_decision=semantic_decision,
                        now=self._now,
                        account_timezone=self._account_timezone,
                        onboarding_guidance_required=gate.activation_guidance_required,
                    )
                    trusted_facts = _add_recoverable_scheduling_context(
                        trusted_facts,
                        service=self._social_scheduling_service(),
                        trigger=trigger,
                        semantic_decision=semantic_decision,
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
                        tool_profile=_tool_profile_for_interactive_decision(
                            semantic_decision,
                            trusted_facts=trusted_facts,
                            tool_ports=self.tool_ports,
                        ),
                        onboarding_guidance_required=gate.activation_guidance_required,
                        turn_source=trusted_facts["turn_source"],
                        current_input_messages=start.input_messages,
                    )
                prepared_result = self._run_prepared_action_if_available(
                    trigger=trigger,
                    context=context,
                    semantic_decision=semantic_decision,
                    current_input_messages=start.input_messages,
                )
                if prepared_result is not None:
                    return prepared_result
                return self._invoke_agent_and_record(
                    trigger,
                    context,
                    semantic_decision,
                )
            except ConversationRuntimeError as error:
                return self._conversation_runtime_error_result(
                    start.turn.id,
                    trigger,
                    error,
                    current_input_messages=start.input_messages,
                )
            finally:
                lock.release()

    async def run_inbound_turn_async(self, trigger: TurnTrigger) -> TurnRunResult:
        try:
            start = self.conversation_runtime.start_turn(
                conversation_id=trigger.conversation_id,
                trigger_id=trigger.trigger_id,
                trigger_type=trigger.trigger_type,
                mode=TurnMode.INTERACTIVE.value,
            )
        except ConversationRuntimeError as error:
            if error.code == "no_open_inbound_window":
                return self._result_from_disposition(
                    turn_id=trigger.trigger_id,
                    trigger=trigger,
                    disposition="superseded",
                    reason_code="input_window_already_closed",
                )
            raise
        self._commit_claim_boundary()
        try:
            with turn_latency_span(
                "turn.total",
                turn_id=start.turn.id,
                trigger_type=trigger.trigger_type,
                mode=TurnMode.INTERACTIVE.value,
                account_id=trigger.account_id,
                conversation_id=trigger.conversation_id,
            ):
                replay_result = self._replayed_result(
                    start.replayed,
                    start.turn.id,
                    trigger,
                    current_input_messages=start.input_messages,
                )
                if replay_result is not None:
                    return replay_result
                gate = self.pre_llm_gate.evaluate(trigger)
                self._commit_claim_boundary()
                if not gate.permitted:
                    return await self._run_access_denied_turn_async(
                        trigger=trigger,
                        gate=gate,
                        turn_id=start.turn.id,
                        input_from_seq=start.turn.input_from_seq,
                        input_to_seq=start.turn.input_to_seq,
                        current_input_messages=start.input_messages,
                    )

                lock = await self._acquire_conversation_lock_async(
                    trigger.conversation_id
                )

                try:
                    freshness_guard = FreshnessGuard(
                        conversation_runtime=self.conversation_runtime,
                        turn_id=start.turn.id,
                        input_from_seq=start.turn.input_from_seq,
                        input_to_seq=start.turn.input_to_seq,
                    )
                    focus_subject = self.focus_resolver.resolve(trigger.conversation_id)
                    if self._use_v2_turn_pipeline(trigger):
                        return await self._run_v2_inbound_turn_async(
                            trigger=trigger,
                            start=start,
                            gate=gate,
                            freshness_guard=freshness_guard,
                            focus_subject=focus_subject,
                        )
                    with turn_latency_span(
                        "turn.semantic_interpreter",
                        turn_id=start.turn.id,
                        trigger_type=trigger.trigger_type,
                        mode=TurnMode.INTERACTIVE.value,
                        account_id=trigger.account_id,
                        conversation_id=trigger.conversation_id,
                    ):
                        semantic_decision = await self._interpret_semantic_async(
                            SemanticInterpreterRequest(
                                account_id=trigger.account_id,
                                conversation_id=trigger.conversation_id,
                                payload=dict(trigger.payload),
                                trusted_facts=gate.trust_facts,
                                focus_subject=focus_subject,
                            )
                        )
                        semantic_decision = (
                            _clear_reference_clarification_with_single_focus(
                                semantic_decision, focus_subject
                            )
                        )
                        semantic_decision = (
                            _clear_context_clarification_for_followup_answer(
                                semantic_decision, trigger
                            )
                        )
                        semantic_decision = (
                            _require_agent_visibility_for_inbound_no_reply(
                                semantic_decision
                            )
                        )

                    with turn_latency_span(
                        "turn.context_assembly",
                        turn_id=start.turn.id,
                        trigger_type=trigger.trigger_type,
                        mode=TurnMode.INTERACTIVE.value,
                        account_id=trigger.account_id,
                        conversation_id=trigger.conversation_id,
                    ):
                        trusted_facts = _trusted_facts_for_agent(
                            gate.trust_facts,
                            trigger=trigger,
                            semantic_decision=semantic_decision,
                            now=self._now,
                            account_timezone=self._account_timezone,
                            onboarding_guidance_required=gate.activation_guidance_required,
                        )
                        trusted_facts = _add_recoverable_scheduling_context(
                            trusted_facts,
                            service=self._social_scheduling_service(),
                            trigger=trigger,
                            semantic_decision=semantic_decision,
                        )
                        context = self.context_assembler.build(
                            trigger=trigger,
                            trusted_facts=trusted_facts,
                            semantic_decision=semantic_decision,
                            focus_subject=focus_subject,
                            reference_resolution=self.reference_resolver.resolve_all(
                                []
                            ),
                            memory_context=self.memory_manager.load(
                                account_id=trigger.account_id,
                                conversation_id=trigger.conversation_id,
                                long_term_enabled=bool(
                                    gate.trust_facts.get("memory_enabled", True)
                                ),
                            ),
                            freshness_guard=freshness_guard,
                            tool_profile=_tool_profile_for_interactive_decision(
                                semantic_decision,
                                trusted_facts=trusted_facts,
                                tool_ports=self.tool_ports,
                            ),
                            onboarding_guidance_required=gate.activation_guidance_required,
                            turn_source=trusted_facts["turn_source"],
                            current_input_messages=start.input_messages,
                        )
                    prepared_result = self._run_prepared_action_if_available(
                        trigger=trigger,
                        context=context,
                        semantic_decision=semantic_decision,
                        current_input_messages=start.input_messages,
                    )
                    if prepared_result is not None:
                        return prepared_result
                    return await self._invoke_agent_and_record_async(
                        trigger,
                        context,
                        semantic_decision,
                    )
                except ConversationRuntimeError as error:
                    return self._conversation_runtime_error_result(
                        start.turn.id,
                        trigger,
                        error,
                        current_input_messages=start.input_messages,
                    )
                finally:
                    lock.release()
        except asyncio.CancelledError as error:
            if is_newer_inbound_cancellation(error):
                self._record_interrupted_turn(start.turn.id)
            raise

    def _use_v2_turn_pipeline(self, trigger: TurnTrigger) -> bool:
        if os.environ.get("COKE_TURN_PIPELINE") == "v2":
            return True
        allowlist = os.environ.get("COKE_TURN_PIPELINE_ACCOUNTS", "")
        canary = {a.strip() for a in allowlist.split(",") if a.strip()}
        return trigger.account_id in canary

    def _run_v2_inbound_turn(
        self,
        *,
        trigger: TurnTrigger,
        start: Any,
        gate: GateDecision,
        freshness_guard: FreshnessGuard,
        focus_subject: Any | None,
    ) -> TurnRunResult:
        return asyncio.run(
            self._run_v2_inbound_turn_async(
                trigger=trigger,
                start=start,
                gate=gate,
                freshness_guard=freshness_guard,
                focus_subject=focus_subject,
            )
        )

    async def _run_v2_inbound_turn_async(
        self,
        *,
        trigger: TurnTrigger,
        start: Any,
        gate: GateDecision,
        freshness_guard: FreshnessGuard,
        focus_subject: Any | None,
    ) -> TurnRunResult:
        if self.turn_pipeline is None:
            disposition = self.conversation_runtime.mark_failed(
                start.turn.id,
                "turn_v2_pipeline_unavailable",
            )
            return self._result_from_disposition(
                turn_id=start.turn.id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=start.input_messages,
            )
        delivery = _V2RunnerDelivery(self, trigger)
        request = self._v2_pipeline_request(
            trigger=trigger,
            start=start,
            gate=gate,
            focus_subject=focus_subject,
        )
        pipeline_result = await self.turn_pipeline.run(
            request,
            freshness_guard,
            delivery=delivery,
        )
        close_result = pipeline_result.close_result
        if not close_result.committed:
            error = close_result.error
            if isinstance(error, ConversationRuntimeError):
                return self._conversation_runtime_error_result(
                    start.turn.id,
                    trigger,
                    error,
                    current_input_messages=start.input_messages,
                )
            disposition = self.conversation_runtime.mark_failed(
                start.turn.id,
                close_result.reason_code or "turn_v2_close_failed",
            )
            return self._result_from_disposition(
                turn_id=start.turn.id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=start.input_messages,
            )

        if not delivery.close_boundary_committed:
            self._commit_close_boundary()
        disposition = close_result.disposition
        disposition_value = getattr(disposition, "disposition", None)
        if not isinstance(disposition_value, str):
            disposition = self.conversation_runtime.mark_failed(
                start.turn.id,
                "turn_v2_close_missing_disposition",
            )
            return self._result_from_disposition(
                turn_id=start.turn.id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=start.input_messages,
            )
        visible_text = (
            "\n".join(pipeline_result.segments) if pipeline_result.segments else None
        )
        if disposition_value == "replied":
            delivered_reply = any(
                outcome.status in {"sent", "delivered"} for outcome in delivery.outcomes
            )
            onboarding_guidance_delivered = (
                gate.activation_guidance_required
                and bool(delivery.outcomes)
                and all(
                    outcome.status in {"sent", "delivered"}
                    for outcome in delivery.outcomes
                )
            )
            self._record_inbound_reply_completed_lifecycle(
                trigger,
                delivered=delivered_reply,
                onboarding_guidance_delivered=onboarding_guidance_delivered,
            )
        return self._result_from_disposition(
            turn_id=start.turn.id,
            trigger=trigger,
            disposition=disposition_value,
            reason_code=getattr(disposition, "reason_code", None),
            visible_text=visible_text,
            current_input_messages=start.input_messages,
        )

    def _v2_pipeline_request(
        self,
        *,
        trigger: TurnTrigger,
        start: Any,
        gate: GateDecision,
        focus_subject: Any | None,
    ) -> TurnPipelineRequest:
        now = self._now()
        trusted_facts = _trusted_facts_for_agent(
            gate.trust_facts,
            trigger=trigger,
            semantic_decision=None,
            now=lambda: now,
            account_timezone=self._account_timezone,
            onboarding_guidance_required=gate.activation_guidance_required,
        )
        return TurnPipelineRequest(
            turn_id=start.turn.id,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
            payload=dict(trigger.payload),
            trusted_facts=trusted_facts,
            focus_subject=focus_subject,
            conversation_history=self._v2_conversation_window(
                trigger.conversation_id,
                current_turn_id=start.turn.id,
            ),
            persona=_v2_persona(trusted_facts),
            assistant_name=str(trusted_facts.get("assistant_name") or "Coke"),
            user_address_name=str(trusted_facts.get("user_address_name") or ""),
            source_input_window=_turn_input_window(start.turn),
            pending_expires_at=now + timedelta(minutes=10),
            now=now,
            run_id=_agent_run_id_for_trigger(trigger, fallback=start.turn.id),
        )

    def _v2_conversation_window(
        self,
        conversation_id: str,
        *,
        current_turn_id: str,
        limit: int = 8,
        max_messages: int = 20,
    ) -> tuple[Mapping[str, Any], ...]:
        try:
            contexts = self.conversation_runtime.recent_turns_with_messages(
                conversation_id, limit=limit
            )
        except ConversationRuntimeError:
            return ()
        history: list[Mapping[str, Any]] = []
        for turn, input_messages, outbound_messages in reversed(contexts):
            if getattr(turn, "id", None) == current_turn_id:
                continue
            for message in input_messages:
                text = getattr(message, "text", None)
                if isinstance(text, str) and text:
                    item: dict[str, Any] = {"role": "user", "content": text}
                    seq = getattr(message, "seq", None)
                    if isinstance(seq, int):
                        item["seq"] = seq
                    history.append(item)
            for message in outbound_messages:
                text = getattr(message, "text", None)
                if isinstance(text, str) and text:
                    history.append({"role": "assistant", "content": text})
        if len(history) > max_messages:
            history = history[-max_messages:]
        return tuple(history)

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
            self._record_render_failure_lifecycle(
                trigger,
                state.turn_id,
                disposition.reason_code or "async_timeout_after_budget",
            )
            return self._result_from_disposition(
                turn_id=state.turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=state.current_input_messages,
            )
        validated = self.output_protocol.validate_first_answer(result.output)
        validated = _validate_for_trigger(trigger, validated)
        return self._record_validated_output(
            turn_id=state.turn_id,
            trigger=trigger,
            validated=validated,
            current_input_messages=state.current_input_messages,
            onboarding_guidance_required=state.onboarding_guidance_required,
        )

    def _run_access_denied_turn(
        self,
        *,
        trigger: TurnTrigger,
        gate: GateDecision,
        turn_id: str,
        input_from_seq: int | None = None,
        input_to_seq: int | None = None,
        current_input_messages: tuple[Any, ...] = (),
    ) -> TurnRunResult:
        render_trigger = TurnTrigger(
            trigger_id=f"{trigger.trigger_id}:access_denied",
            trigger_type="AccessDeniedTurn",
            mode=TurnMode.RENDER,
            conversation_id=trigger.conversation_id,
            account_id=trigger.account_id,
            channel_identity_id=trigger.channel_identity_id,
            agent_run_id=trigger.agent_run_id,
            payload={
                "access_denied": True,
                "denial_reason": gate.denial_reason,
                "facts": gate.access_facts,
            },
        )
        render_gate = GateDecision.allowed(
            trust_facts={
                "account_id": trigger.account_id,
                "denial_reason": gate.denial_reason,
                **gate.access_facts,
            }
        )
        lock = self.lock_manager.acquire(trigger.conversation_id)
        if lock is None:
            disposition = self.conversation_runtime.mark_failed(
                turn_id, "conversation_lock_unavailable"
            )
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=render_trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=current_input_messages,
            )
        try:
            freshness_guard = FreshnessGuard(
                conversation_runtime=self.conversation_runtime,
                turn_id=turn_id,
                input_from_seq=input_from_seq,
                input_to_seq=input_to_seq,
            )
            trusted_facts = _trusted_facts_for_agent(
                render_gate.trust_facts,
                trigger=render_trigger,
                semantic_decision=None,
                now=self._now,
                account_timezone=self._account_timezone,
            )
            context = self.context_assembler.build(
                trigger=render_trigger,
                trusted_facts=trusted_facts,
                semantic_decision=None,
                focus_subject=None,
                reference_resolution=None,
                memory_context=None,
                freshness_guard=freshness_guard,
                tool_profile=ToolProfile.render(constrained=True),
                turn_source=trusted_facts["turn_source"],
                current_input_messages=current_input_messages,
            )
            return self._invoke_agent_and_record(
                render_trigger,
                context,
                semantic_decision=None,
            )
        except ConversationRuntimeError as error:
            return self._conversation_runtime_error_result(
                turn_id,
                render_trigger,
                error,
                current_input_messages=current_input_messages,
            )
        finally:
            lock.release()

    async def _run_access_denied_turn_async(
        self,
        *,
        trigger: TurnTrigger,
        gate: GateDecision,
        turn_id: str,
        input_from_seq: int | None = None,
        input_to_seq: int | None = None,
        current_input_messages: tuple[Any, ...] = (),
    ) -> TurnRunResult:
        render_trigger = TurnTrigger(
            trigger_id=f"{trigger.trigger_id}:access_denied",
            trigger_type="AccessDeniedTurn",
            mode=TurnMode.RENDER,
            conversation_id=trigger.conversation_id,
            account_id=trigger.account_id,
            channel_identity_id=trigger.channel_identity_id,
            agent_run_id=trigger.agent_run_id,
            payload={
                "access_denied": True,
                "denial_reason": gate.denial_reason,
                "facts": gate.access_facts,
            },
        )
        render_gate = GateDecision.allowed(
            trust_facts={
                "account_id": trigger.account_id,
                "denial_reason": gate.denial_reason,
                **gate.access_facts,
            }
        )
        lock = await self._acquire_conversation_lock_async(trigger.conversation_id)
        try:
            freshness_guard = FreshnessGuard(
                conversation_runtime=self.conversation_runtime,
                turn_id=turn_id,
                input_from_seq=input_from_seq,
                input_to_seq=input_to_seq,
            )
            trusted_facts = _trusted_facts_for_agent(
                render_gate.trust_facts,
                trigger=render_trigger,
                semantic_decision=None,
                now=self._now,
                account_timezone=self._account_timezone,
            )
            context = self.context_assembler.build(
                trigger=render_trigger,
                trusted_facts=trusted_facts,
                semantic_decision=None,
                focus_subject=None,
                reference_resolution=None,
                memory_context=None,
                freshness_guard=freshness_guard,
                tool_profile=ToolProfile.render(constrained=True),
                turn_source=trusted_facts["turn_source"],
                current_input_messages=current_input_messages,
            )
            return await self._invoke_agent_and_record_async(
                render_trigger,
                context,
                semantic_decision=None,
            )
        except ConversationRuntimeError as error:
            return self._conversation_runtime_error_result(
                turn_id,
                render_trigger,
                error,
                current_input_messages=current_input_messages,
            )
        finally:
            lock.release()

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
        with turn_latency_span(
            "turn.total",
            turn_id=start.turn.id,
            trigger_type=trigger.trigger_type,
            mode=TurnMode.RENDER.value,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
        ):
            replay_result = self._replayed_result(
                start.replayed, start.turn.id, trigger
            )
            if replay_result is not None:
                return replay_result
            lock = self.lock_manager.acquire(trigger.conversation_id)
            if lock is None:
                disposition = self.conversation_runtime.mark_failed(
                    start.turn.id, "conversation_lock_unavailable"
                )
                self._record_render_failure_lifecycle(
                    trigger,
                    start.turn.id,
                    disposition.reason_code or "conversation_lock_unavailable",
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
                    input_from_seq=start.turn.input_from_seq,
                    input_to_seq=start.turn.input_to_seq,
                )
                with turn_latency_span(
                    "turn.context_assembly",
                    turn_id=start.turn.id,
                    trigger_type=trigger.trigger_type,
                    mode=TurnMode.RENDER.value,
                    account_id=trigger.account_id,
                    conversation_id=trigger.conversation_id,
                ):
                    trusted_facts = _trusted_facts_for_agent(
                        gate.trust_facts,
                        trigger=trigger,
                        semantic_decision=None,
                        now=self._now,
                        account_timezone=self._account_timezone,
                    )
                    try:
                        domain_result = _reminder_fire_domain_result(
                            self.reminder_fire_facts,
                            trigger,
                        )
                    except Exception as error:
                        reason_code = _render_fact_error_code(error)
                        disposition = self.conversation_runtime.mark_failed(
                            start.turn.id,
                            reason_code,
                        )
                        self._record_render_failure_lifecycle(
                            trigger=trigger,
                            turn_id=start.turn.id,
                            reason_code=reason_code,
                        )
                        return self._result_from_disposition(
                            turn_id=start.turn.id,
                            trigger=trigger,
                            disposition=disposition.disposition,
                            reason_code=disposition.reason_code,
                        )
                    if domain_result is not None:
                        trusted_facts["domain_result"] = domain_result
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
                        domain_result=domain_result,
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

    def _run_prepared_action_if_available(
        self,
        *,
        trigger: TurnTrigger,
        context: Any,
        semantic_decision: SemanticDecision,
        current_input_messages: tuple[Any, ...] = (),
    ) -> TurnRunResult | None:
        route = derive_route(semantic_decision)
        if route != "prepared_list":
            return None
        reminder_tool = self.tool_ports.reminder_tool
        if reminder_tool is None or not hasattr(
            reminder_tool, "execute_without_staging"
        ):
            return None
        with turn_latency_span(
            "turn.prepared_action",
            turn_id=context.freshness_guard.turn_id,
            trigger_type=trigger.trigger_type,
            mode=trigger.mode,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
            extra={"route": route, "action": "list_reminders"},
        ) as latency_fields:
            result = self.action_runner.run_plain_reminder_list(
                account_id=str(
                    context.trusted_facts.get("account_id") or trigger.account_id
                ),
                display_timezone=str(
                    context.trusted_facts.get("default_timezone") or "UTC"
                ),
                user_text=_user_text_from_payload(trigger.payload),
                reminder_tool=reminder_tool,
                guard=context.freshness_guard,
            )
            latency_fields["tool_count"] = len(result.tool_events)
        if not result.handled or result.validated is None:
            return None
        return self._record_validated_output(
            turn_id=context.freshness_guard.turn_id,
            trigger=trigger,
            validated=result.validated,
            current_input_messages=tuple(
                current_input_messages or getattr(context, "current_input_messages", ())
            ),
            tool_events=tuple(result.tool_events),
            onboarding_guidance_required=bool(
                getattr(context, "onboarding_guidance_required", False)
            ),
        )

    def _invoke_agent_and_record(
        self,
        trigger: TurnTrigger,
        context: Any,
        semantic_decision: SemanticDecision | None,
        *,
        current_input_messages: tuple[Any, ...] = (),
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
            current_input_messages=tuple(
                current_input_messages or getattr(context, "current_input_messages", ())
            ),
            run_id=_agent_run_id_for_trigger(
                trigger,
                fallback=context.freshness_guard.turn_id,
            ),
        )
        with turn_latency_span(
            "agent.primary",
            turn_id=agent_request.turn_id,
            trigger_type=trigger.trigger_type,
            mode=trigger.mode,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
        ) as latency_fields:
            agent_result = self.interaction_agent.invoke(agent_request)
            latency_fields["tool_count"] = len(agent_result.tool_events)
            latency_fields["timeout"] = agent_result.timed_out
        if agent_result.timed_out:
            return self._record_pending_async(trigger, context, agent_result)
        validated = self._validate_agent_output(
            trigger,
            agent_request,
            agent_result.output,
            tool_events=agent_result.tool_events,
        )
        record_tool_events = tuple(agent_result.tool_events)
        if not validated.valid:
            retry_request = _protocol_retry_request(agent_request, validated)
            previous_tool_events = tuple(agent_result.tool_events)
            with turn_latency_span(
                "agent.protocol_retry",
                turn_id=agent_request.turn_id,
                trigger_type=trigger.trigger_type,
                mode=trigger.mode,
                account_id=trigger.account_id,
                conversation_id=trigger.conversation_id,
                extra={"retry_attempt": 1},
            ) as latency_fields:
                agent_result = self.interaction_agent.invoke(retry_request)
                latency_fields["tool_count"] = len(agent_result.tool_events)
                latency_fields["timeout"] = agent_result.timed_out
            if agent_result.timed_out:
                return self._record_pending_async(trigger, context, agent_result)
            record_tool_events = previous_tool_events + tuple(agent_result.tool_events)
            validated = self._validate_agent_output(
                trigger,
                retry_request,
                agent_result.output,
                tool_events=record_tool_events,
            )
            if not validated.valid:
                fallback = _minimal_reminder_fire_reply(retry_request)
                if fallback is not None:
                    validated = fallback
                else:
                    recovery_text = _grounded_recovery_text(
                        retry_request,
                        tool_events=record_tool_events,
                    )
                    if recovery_text is not None:
                        return self._record_recovery_reply(
                            turn_id=context.freshness_guard.turn_id,
                            trigger=trigger,
                            recovery_text=recovery_text,
                            current_input_messages=agent_request.current_input_messages,
                            onboarding_guidance_required=bool(
                                getattr(
                                    context,
                                    "onboarding_guidance_required",
                                    False,
                                )
                            ),
                        )
        return self._record_validated_output(
            turn_id=context.freshness_guard.turn_id,
            trigger=trigger,
            validated=validated,
            current_input_messages=agent_request.current_input_messages,
            tool_events=record_tool_events,
            onboarding_guidance_required=bool(
                getattr(context, "onboarding_guidance_required", False)
            ),
        )

    async def _invoke_agent_and_record_async(
        self,
        trigger: TurnTrigger,
        context: Any,
        semantic_decision: SemanticDecision | None,
        *,
        current_input_messages: tuple[Any, ...] = (),
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
            current_input_messages=tuple(
                current_input_messages or getattr(context, "current_input_messages", ())
            ),
            run_id=_agent_run_id_for_trigger(
                trigger,
                fallback=context.freshness_guard.turn_id,
            ),
        )
        streamed_segment_count = 0
        streamed_reply_outcomes: tuple[DeliveryOutcome, ...] = ()
        with turn_latency_span(
            "agent.primary",
            turn_id=agent_request.turn_id,
            trigger_type=trigger.trigger_type,
            mode=trigger.mode,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
        ) as latency_fields:
            streaming_invoke = getattr(
                self.interaction_agent, "ainvoke_streaming", None
            )
            if (
                semantic_decision is not None
                and callable(streaming_invoke)
                and is_streaming_eligible(
                    trigger, semantic_decision, context.tool_profile
                )
            ):
                (
                    agent_result,
                    streamed_segment_count,
                    first_segment_ms,
                    streamed_reply_outcomes,
                ) = await self._consume_streaming_agent_reply(
                    trigger=trigger,
                    request=agent_request,
                    streaming_invoke=streaming_invoke,
                )
                latency_fields["streamed"] = streamed_segment_count > 0
                if first_segment_ms is not None:
                    latency_fields["first_segment_ms"] = first_segment_ms
            else:
                agent_result = await self.interaction_agent.ainvoke(agent_request)
            latency_fields["tool_count"] = len(agent_result.tool_events)
            latency_fields["timeout"] = agent_result.timed_out
        if agent_result.timed_out:
            return self._record_pending_async(trigger, context, agent_result)
        validated = self._validate_agent_output(
            trigger,
            agent_request,
            agent_result.output,
            tool_events=agent_result.tool_events,
        )
        record_tool_events = tuple(agent_result.tool_events)
        if not validated.valid:
            retry_request = _protocol_retry_request(agent_request, validated)
            previous_tool_events = tuple(agent_result.tool_events)
            with turn_latency_span(
                "agent.protocol_retry",
                turn_id=agent_request.turn_id,
                trigger_type=trigger.trigger_type,
                mode=trigger.mode,
                account_id=trigger.account_id,
                conversation_id=trigger.conversation_id,
                extra={"retry_attempt": 1},
            ) as latency_fields:
                agent_result = await self.interaction_agent.ainvoke(retry_request)
                latency_fields["tool_count"] = len(agent_result.tool_events)
                latency_fields["timeout"] = agent_result.timed_out
            if agent_result.timed_out:
                return self._record_pending_async(trigger, context, agent_result)
            record_tool_events = previous_tool_events + tuple(agent_result.tool_events)
            validated = self._validate_agent_output(
                trigger,
                retry_request,
                agent_result.output,
                tool_events=record_tool_events,
            )
            if not validated.valid:
                fallback = _minimal_reminder_fire_reply(retry_request)
                if fallback is not None:
                    validated = fallback
                else:
                    recovery_text = _grounded_recovery_text(
                        retry_request,
                        tool_events=record_tool_events,
                    )
                    if recovery_text is not None:
                        return self._record_recovery_reply(
                            turn_id=context.freshness_guard.turn_id,
                            trigger=trigger,
                            recovery_text=recovery_text,
                            current_input_messages=agent_request.current_input_messages,
                            onboarding_guidance_required=bool(
                                getattr(
                                    context,
                                    "onboarding_guidance_required",
                                    False,
                                )
                            ),
                        )
        return self._record_validated_output(
            turn_id=context.freshness_guard.turn_id,
            trigger=trigger,
            validated=validated,
            current_input_messages=agent_request.current_input_messages,
            tool_events=record_tool_events,
            onboarding_guidance_required=bool(
                getattr(context, "onboarding_guidance_required", False)
            ),
            skip_delivered_segment_count=streamed_segment_count,
            pre_delivered_reply_outcomes=streamed_reply_outcomes,
        )

    async def _consume_streaming_agent_reply(
        self,
        *,
        trigger: TurnTrigger,
        request: AgentRequest,
        streaming_invoke: Callable[[AgentRequest], Any],
    ) -> tuple[AgentResult, int, int | None, tuple[DeliveryOutcome, ...]]:
        started_at = time.perf_counter()
        streamed_segment_count = 0
        first_segment_ms: int | None = None
        reply_outcomes: list[DeliveryOutcome] = []
        final_result: AgentResult | None = None
        streaming_suppressed = False
        async for event in streaming_invoke(request):
            if isinstance(event, AgentResult):
                final_result = event
                break
            if (
                streaming_suppressed
                or streamed_segment_count > 0
                or not isinstance(event, str)
            ):
                continue
            segment = event.strip()
            if not segment:
                continue
            if _contains_serialized_tool_call(segment):
                streaming_suppressed = True
                continue
            first_segment_validation = self._validate_agent_output(
                trigger,
                request,
                {"type": "reply", "segments": [segment]},
                tool_events=(),
            )
            if not first_segment_validation.valid:
                streaming_suppressed = True
                continue
            first_segment_ms = max(
                0, int(round((time.perf_counter() - started_at) * 1000))
            )
            for delivery_request in self._reply_delivery_requests(
                trigger=trigger,
                turn_id=request.turn_id,
                visible_text=segment,
                segments=(segment,),
                outbound_messages=[],
                start_index=1,
            ):
                outcome = self._deliver(delivery_request)
                reply_outcomes.append(outcome)
                self._record_delivery_lifecycle(trigger, delivery_request, outcome)
            streamed_segment_count = 1
        if final_result is None:
            final_result = AgentResult.completed(None, blank_output=True)
        return (
            final_result,
            streamed_segment_count,
            first_segment_ms,
            tuple(reply_outcomes),
        )

    def _validate_agent_output(
        self,
        trigger: TurnTrigger,
        request: AgentRequest,
        output: Mapping[str, Any] | None,
        *,
        tool_events: tuple[Mapping[str, Any], ...] = (),
    ) -> ValidatedOutput:
        validated = self.output_protocol.validate_first_answer(output)
        social_outcomes = _social_scheduling_outcomes_from_tool_events(tool_events)
        claim_required = _requires_social_scheduling_claim(request)
        if (
            claim_required
            and not social_outcomes
            and self._has_current_turn_social_scheduling_create_stage(request.turn_id)
        ):
            claim_required = False
        validated = self.output_protocol.validate_social_scheduling_claim(
            validated,
            outcomes=social_outcomes,
            claim_required=claim_required,
            active_shared_reminder_exists=(
                self._active_shared_reminder_exists_for_request(request)
            ),
        )
        validated = _validate_for_trigger(trigger, validated)
        return _validate_reminder_fire_output(request, validated)

    async def _interpret_semantic_async(
        self, request: SemanticInterpreterRequest
    ) -> SemanticDecision:
        return await asyncio.to_thread(self.semantic_interpreter.interpret, request)

    def _social_scheduling_service(self) -> Any | None:
        if self.social_scheduling_service is not None:
            return self.social_scheduling_service
        tool = self.tool_ports.social_scheduling_tool
        return getattr(tool, "social_scheduling_service", None)

    def _active_shared_reminder_exists_for_request(
        self,
        request: AgentRequest,
    ) -> Callable[[str], bool] | None:
        service = self._social_scheduling_service()
        if service is None:
            return None

        def exists(shared_reminder_id: str) -> bool:
            try:
                reminder = service.view_shared_reminder(
                    request.account_id,
                    shared_reminder_id,
                )
            except Exception:
                return False
            return getattr(reminder, "status", None) == "active"

        return exists

    def _has_current_turn_social_scheduling_create_stage(self, turn_id: str) -> bool:
        repository = getattr(self.conversation_runtime, "repository", None)
        staged_commands_for_turn = getattr(repository, "staged_commands_for_turn", None)
        if not callable(staged_commands_for_turn):
            return False
        for command in staged_commands_for_turn(turn_id):
            if (
                getattr(command, "status", None) == "staged"
                and getattr(command, "domain", None) == "social_scheduling"
                and getattr(command, "operation", None)
                in {"create_shared_reminder", "detect_and_create_shared_reminder"}
            ):
                return True
        return False

    def _pending_clarification_context(
        self,
        *,
        trigger: TurnTrigger,
        gate: GateDecision,
        freshness_guard: FreshnessGuard,
        focus_subject: Any | None,
        current_input_messages: tuple[Any, ...],
    ) -> Any | None:
        trusted_facts = _trusted_facts_for_agent(
            gate.trust_facts,
            trigger=trigger,
            semantic_decision=None,
            now=self._now,
            account_timezone=self._account_timezone,
            onboarding_guidance_required=gate.activation_guidance_required,
        )
        trusted_facts = _add_pending_clarification_resolution(
            trusted_facts,
            conversation_runtime=self.conversation_runtime,
            trigger=trigger,
            current_turn_id=freshness_guard.turn_id,
        )
        if not _has_executable_pending_clarification(trusted_facts):
            return None
        return self.context_assembler.build(
            trigger=trigger,
            trusted_facts=trusted_facts,
            semantic_decision=None,
            focus_subject=focus_subject,
            reference_resolution=self.reference_resolver.resolve_all([]),
            memory_context=self.memory_manager.load(
                account_id=trigger.account_id,
                conversation_id=trigger.conversation_id,
                long_term_enabled=bool(gate.trust_facts.get("memory_enabled", True)),
            ),
            freshness_guard=freshness_guard,
            tool_profile=ToolProfile.interactive(self.tool_ports),
            onboarding_guidance_required=gate.activation_guidance_required,
            turn_source=trusted_facts["turn_source"],
            current_input_messages=current_input_messages,
        )

    async def _acquire_conversation_lock_async(self, conversation_id: str):
        while True:
            lock = self.lock_manager.acquire(conversation_id)
            if lock is not None:
                return lock
            await asyncio.sleep(self._lock_wait_interval_s)

    def _record_pending_async(
        self,
        trigger: TurnTrigger,
        context: Any,
        agent_result: AgentResult,
    ) -> TurnRunResult:
        current_input_messages = tuple(getattr(context, "current_input_messages", ()))
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
                current_input_messages=current_input_messages,
            )
        context.freshness_guard.guard_state_change()
        disposition = self.conversation_runtime.mark_pending_async_reply(
            turn_id=context.freshness_guard.turn_id,
            reason_code="sync_timeout",
            materialize_staged_command=self._materialize_staged_command,
        )
        waiting_message = self.conversation_runtime.record_outbound_message(
            context.freshness_guard.turn_id,
            WAITING_TEXT,
            segment_index=0,
            payload={"message_type": "waiting"},
        )
        async_state = _AsyncState(
            task_id=agent_result.task_id,
            turn_id=context.freshness_guard.turn_id,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            conversation_id=trigger.conversation_id,
            account_id=trigger.account_id,
            context_token=_context_token_from_trigger(trigger),
            onboarding_guidance_required=bool(
                getattr(context, "onboarding_guidance_required", False)
            ),
            current_input_messages=current_input_messages,
        )
        self._commit_close_boundary()
        self._async_states[agent_result.task_id] = async_state
        context_token = _context_token_from_trigger(trigger)
        send_waiting_delivery(
            outbound_delivery=self.outbound_delivery,
            account_id=trigger.account_id,
            conversation_id=trigger.conversation_id,
            turn_id=context.freshness_guard.turn_id,
            message_id=waiting_message.id,
            context_token=context_token,
            delivery_source="waiting_sync_timeout",
            traceparent=_traceparent_from_trigger(trigger),
            context_token_source="trigger_payload" if context_token else "none",
            context_token_age_seconds=None,
            turn_disposition=self.conversation_runtime.get_disposition,
            retry_jitter=self._waiting_retry_jitter,
            sleep=self._waiting_retry_sleep,
            circuit_breaker=self._waiting_circuit_breaker,
        )
        return self._result_from_disposition(
            turn_id=context.freshness_guard.turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=WAITING_TEXT,
            async_task_id=agent_result.task_id,
            current_input_messages=current_input_messages,
        )

    def _record_recovery_reply(
        self,
        *,
        turn_id: str,
        trigger: TurnTrigger,
        recovery_text: str,
        current_input_messages: tuple[Any, ...] = (),
        onboarding_guidance_required: bool = False,
    ) -> TurnRunResult:
        segments = (recovery_text,)
        disposition = self.conversation_runtime.commit_recovery_reply(
            turn_id=turn_id,
            segments=segments,
            reason_code="grounded_failure_recovery",
        )
        self._commit_close_boundary()
        visible_text = "\n".join(segments)
        outbound_messages = [
            message
            for message in self.conversation_runtime.outbound_messages_for_turn(turn_id)
            if (message.segment_index or 0) > 0
        ]
        delivered_reply = False
        reply_outcomes: list[DeliveryOutcome] = []
        for request in self._reply_delivery_requests(
            trigger=trigger,
            turn_id=turn_id,
            visible_text=visible_text,
            segments=segments,
            outbound_messages=outbound_messages,
        ):
            outcome = self._deliver(request)
            reply_outcomes.append(outcome)
            self._record_delivery_lifecycle(trigger, request, outcome)
            delivered_reply = delivered_reply or outcome.status in {
                "sent",
                "delivered",
            }
        onboarding_guidance_delivered = (
            onboarding_guidance_required
            and trigger.trigger_type == "InboundTurn"
            and bool(reply_outcomes)
            and all(
                outcome.status in {"sent", "delivered"} for outcome in reply_outcomes
            )
        )
        self._record_inbound_reply_completed_lifecycle(
            trigger,
            delivered=delivered_reply,
            onboarding_guidance_delivered=onboarding_guidance_delivered,
        )
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=visible_text,
            current_input_messages=current_input_messages,
        )

    def _record_validated_output(
        self,
        *,
        turn_id: str,
        trigger: TurnTrigger,
        validated: ValidatedOutput,
        current_input_messages: tuple[Any, ...] = (),
        tool_events: tuple[Mapping[str, Any], ...] = (),
        onboarding_guidance_required: bool = False,
        skip_delivered_segment_count: int = 0,
        pre_delivered_reply_outcomes: tuple[DeliveryOutcome, ...] = (),
    ) -> TurnRunResult:
        if not validated.valid:
            disposition = self.conversation_runtime.mark_failed(
                turn_id=turn_id,
                reason_code=validated.reason_code or "invalid_output_protocol",
            )
            self._record_render_failure_lifecycle(
                trigger,
                turn_id,
                disposition.reason_code or "invalid_output_protocol",
            )
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=current_input_messages,
            )
        if validated.kind == "no_reply":
            disposition = self.conversation_runtime.commit_no_reply(
                turn_id=turn_id,
                reason_code="intentional_no_reply",
                materialize_staged_command=self._materialize_staged_command,
            )
            self._record_render_failure_lifecycle(
                trigger,
                turn_id,
                disposition.reason_code or "intentional_no_reply",
            )
            self._commit_close_boundary()
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=current_input_messages,
            )

        segments = self._delivery_segments(trigger, validated.segments)
        disposition = self.conversation_runtime.commit_reply(
            turn_id=turn_id,
            segments=segments,
            reason_code=validated.reason_code or "reply_ready",
            materialize_staged_command=self._materialize_staged_command,
        )
        self._commit_close_boundary()
        self._record_social_scheduling_recovery_after_close(
            trigger=trigger,
            turn_id=turn_id,
            validated=validated,
            tool_events=tool_events,
            current_input_messages=current_input_messages,
        )
        visible_text = "\n".join(segments)
        outbound_messages = [
            message
            for message in self.conversation_runtime.outbound_messages_for_turn(turn_id)
            if (message.segment_index or 0) > 0
        ]
        reply_outcomes: list[DeliveryOutcome] = list(pre_delivered_reply_outcomes)
        delivered_reply = any(
            outcome.status in {"sent", "delivered"} for outcome in reply_outcomes
        )
        delivery_start_index = max(1, skip_delivered_segment_count + 1)
        remaining_segments = segments[skip_delivered_segment_count:]
        for request in self._reply_delivery_requests(
            trigger=trigger,
            turn_id=turn_id,
            visible_text=visible_text,
            segments=remaining_segments,
            outbound_messages=outbound_messages,
            start_index=delivery_start_index,
        ):
            outcome = self._deliver(request)
            reply_outcomes.append(outcome)
            self._record_delivery_lifecycle(trigger, request, outcome)
            delivered_reply = delivered_reply or outcome.status in {
                "sent",
                "delivered",
            }
        onboarding_guidance_delivered = (
            onboarding_guidance_required
            and trigger.trigger_type == "InboundTurn"
            and bool(reply_outcomes)
            and all(
                outcome.status in {"sent", "delivered"} for outcome in reply_outcomes
            )
        )
        self._record_inbound_reply_completed_lifecycle(
            trigger,
            delivered=delivered_reply,
            onboarding_guidance_delivered=onboarding_guidance_delivered,
        )
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=visible_text,
            current_input_messages=current_input_messages,
        )

    def _commit_close_boundary(self) -> None:
        self._close_boundary_committer()
        notify_close_boundary_committed()

    def _record_interrupted_turn(self, turn_id: str) -> None:
        self.conversation_runtime.mark_superseded(
            turn_id,
            reason_code="interrupted_by_newer_inbound",
        )
        self._close_boundary_committer()

    def _commit_claim_boundary(self) -> None:
        self._claim_boundary_committer()

    def _materialize_staged_command(self, command) -> None:
        if self.staged_command_materializer is None:
            raise ConversationRuntimeError("staged_command_materializer_missing")
        guard = FreshnessGuard(
            conversation_runtime=self.conversation_runtime,
            turn_id=command.turn_id,
        )
        self.staged_command_materializer.materialize(command, guard)

    def _record_social_scheduling_recovery_after_close(
        self,
        *,
        trigger: TurnTrigger,
        turn_id: str,
        validated: ValidatedOutput,
        tool_events: tuple[Mapping[str, Any], ...],
        current_input_messages: tuple[Any, ...],
    ) -> None:
        service = self._social_scheduling_service()
        if service is None or trigger.trigger_type != "InboundTurn":
            return
        _create_recoverable_intents_from_tool_events(
            service=service,
            trigger=trigger,
            turn_id=turn_id,
            validated=validated,
            tool_events=tool_events,
            current_input_messages=current_input_messages,
        )
        _consume_recoverable_intents_from_materialized_commands(
            service=service,
            conversation_runtime=self.conversation_runtime,
            turn_id=turn_id,
        )

    def _replayed_result(
        self,
        replayed: bool,
        turn_id: str,
        trigger: TurnTrigger,
        *,
        current_input_messages: tuple[Any, ...] = (),
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
            async_task_id = self._async_task_id_for_turn(turn_id)
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            visible_text=visible_text,
            async_task_id=async_task_id,
            current_input_messages=current_input_messages,
        )

    def _async_task_id_for_turn(self, turn_id: str) -> str | None:
        for task_id, state in self._async_states.items():
            if state.turn_id == turn_id:
                return task_id
        return None

    def _delivery_segments(
        self, trigger: TurnTrigger, segments: tuple[str, ...]
    ) -> tuple[str, ...]:
        # Interactive inbound replies may legitimately deliver as multiple
        # conversational bubbles. System-initiated product notifications must
        # deliver as a single message: each segment is a separate provider send
        # bound by the WeChat per-send context-token window, and losing a later
        # send (ilink ret_-2) would strand the content segment and leave the
        # recipient with a contentless header while the creator is falsely told
        # it was delivered. See
        # docs/issues/2026-06-09-shared-reminder-invite-content-segment-lost.md.
        if trigger.trigger_type == "InboundTurn" or len(segments) <= 1:
            return segments
        return ("\n".join(segments),)

    def _reply_delivery_requests(
        self,
        *,
        trigger: TurnTrigger,
        turn_id: str,
        visible_text: str,
        segments: tuple[str, ...],
        outbound_messages: list[Any],
        start_index: int = 1,
    ) -> list[DeliveryRequest]:
        recipients = _recipient_account_ids(trigger)
        multiple = len(recipients) > 1
        ordered_messages = sorted(
            outbound_messages,
            key=lambda message: (
                getattr(message, "segment_index", None) or 0,
                message.id,
            ),
        )
        requests: list[DeliveryRequest] = []
        for account_id in recipients:
            for index, segment in enumerate(segments, start=start_index):
                message_id = _outbound_message_id_for_segment(ordered_messages, index)
                idempotency_key = f"{turn_id}:reply:{index}"
                if multiple or account_id != trigger.account_id:
                    idempotency_key = f"{idempotency_key}:{account_id}"
                context_token = _context_token_from_trigger(trigger)
                requests.append(
                    DeliveryRequest(
                        account_id=account_id,
                        conversation_id=trigger.conversation_id,
                        turn_id=turn_id,
                        message_type="reply",
                        visible_text=segment,
                        idempotency_key=idempotency_key,
                        message_id=message_id,
                        segments=(segment,),
                        context_token=context_token,
                        delivery_source="reply",
                        delivery_intent=idempotency_key,
                        retry_attempt=1,
                        traceparent=_traceparent_from_trigger(trigger),
                        container=os.environ.get("HOSTNAME"),
                        context_token_source=(
                            "trigger_payload" if context_token else "none"
                        ),
                    )
                )
        return requests

    def _deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        return _safe_delivery_outcome(self.outbound_delivery, request)

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

    def _record_render_failure_lifecycle(
        self,
        trigger: TurnTrigger,
        turn_id: str,
        reason_code: str,
    ) -> None:
        if self.delivery_lifecycle is None:
            return
        recorder = getattr(self.delivery_lifecycle, "record_render_failure", None)
        if not callable(recorder):
            return
        recorder(trigger=trigger, turn_id=turn_id, reason_code=reason_code)

    def _record_inbound_reply_completed_lifecycle(
        self,
        trigger: TurnTrigger,
        *,
        delivered: bool,
        onboarding_guidance_delivered: bool,
    ) -> None:
        if self.delivery_lifecycle is None or trigger.trigger_type != "InboundTurn":
            return
        recorder = getattr(
            self.delivery_lifecycle,
            "record_inbound_reply_completed",
            None,
        )
        if not callable(recorder):
            return
        recorder(
            trigger=trigger,
            delivered=delivered,
            onboarding_guidance_delivered=onboarding_guidance_delivered,
        )

    def _conversation_runtime_error_result(
        self,
        turn_id: str,
        trigger: TurnTrigger,
        error: ConversationRuntimeError,
        *,
        current_input_messages: tuple[Any, ...] = (),
    ) -> TurnRunResult:
        if error.code == "turn_superseded":
            disposition = self.conversation_runtime.get_disposition(turn_id)
            self._record_render_failure_lifecycle(
                trigger,
                turn_id,
                disposition.reason_code or "turn_superseded",
            )
            return self._result_from_disposition(
                turn_id=turn_id,
                trigger=trigger,
                disposition=disposition.disposition,
                reason_code=disposition.reason_code,
                current_input_messages=current_input_messages,
            )
        disposition = self.conversation_runtime.mark_failed(turn_id, error.code)
        self._record_render_failure_lifecycle(
            trigger,
            turn_id,
            disposition.reason_code or error.code,
        )
        return self._result_from_disposition(
            turn_id=turn_id,
            trigger=trigger,
            disposition=disposition.disposition,
            reason_code=disposition.reason_code,
            current_input_messages=current_input_messages,
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
        current_input_messages: tuple[Any, ...] = (),
    ) -> TurnRunResult:
        latest_causal_id, coalesced_causal_ids = _causal_ids_from_input_messages(
            current_input_messages
        )
        return TurnRunResult(
            turn_id=turn_id,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            disposition=disposition,
            reason_code=reason_code,
            visible_text=visible_text,
            async_task_id=async_task_id,
            latest_causal_inbound_event_id=latest_causal_id,
            coalesced_causal_inbound_event_ids=coalesced_causal_ids,
        )


def _causal_ids_from_input_messages(
    current_input_messages: tuple[Any, ...],
) -> tuple[str | None, tuple[str, ...]]:
    causal_ids = tuple(
        causal_id
        for message in current_input_messages
        if isinstance(
            causal_id := getattr(message, "causal_inbound_event_id", None),
            str,
        )
        and causal_id
    )
    if not causal_ids:
        return None, ()
    latest = causal_ids[-1]
    return latest, tuple(
        causal_id for causal_id in causal_ids[:-1] if causal_id != latest
    )


def _v2_persona(trusted_facts: Mapping[str, Any]) -> str:
    parts = []
    for key in ("persona", "speaking_style", "background", "extra_rules"):
        value = trusted_facts.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def _turn_input_window(turn: Any) -> tuple[int, int] | None:
    input_from_seq = getattr(turn, "input_from_seq", None)
    input_to_seq = getattr(turn, "input_to_seq", None)
    if isinstance(input_from_seq, int) and isinstance(input_to_seq, int):
        return (input_from_seq, input_to_seq)
    return None


def _create_recoverable_intents_from_tool_events(
    *,
    service: Any,
    trigger: TurnTrigger,
    turn_id: str,
    validated: ValidatedOutput,
    tool_events: tuple[Mapping[str, Any], ...],
    current_input_messages: tuple[Any, ...],
) -> None:
    claim = validated.domain_claim
    if (
        not isinstance(claim, Mapping)
        or claim.get("domain") != "social_scheduling"
        or claim.get("status")
        not in {"blocked_unmatched_friend", "blocked_ambiguous_friend"}
    ):
        return
    source_from_seq, source_to_seq, source_message_ids = _source_input_window(
        current_input_messages
    )
    for event in tool_events:
        outcome_mapping = _social_scheduling_outcome_from_event(event)
        if outcome_mapping is None:
            continue
        if outcome_mapping.get("outcome_id") != claim.get("outcome_id"):
            continue
        unresolved = _unresolved_friend_reference_from_event(event)
        if unresolved is None:
            continue
        outcome = _social_scheduling_outcome_model(outcome_mapping)
        if outcome is None:
            continue
        service.create_recoverable_intent_from_outcome(
            conversation_id=trigger.conversation_id,
            creator_account_id=trigger.account_id,
            outcome=outcome,
            unresolved_reference_text=unresolved,
            source_turn_id=turn_id,
            source_input_from_seq=source_from_seq,
            source_input_to_seq=source_to_seq,
            source_message_ids=source_message_ids,
        )


def _consume_recoverable_intents_from_materialized_commands(
    *,
    service: Any,
    conversation_runtime: ConversationRuntimeService,
    turn_id: str,
) -> None:
    repository = getattr(conversation_runtime, "repository", None)
    staged_commands_for_turn = getattr(repository, "staged_commands_for_turn", None)
    if not callable(staged_commands_for_turn):
        return
    for command in staged_commands_for_turn(turn_id):
        if (
            getattr(command, "status", None) != "materialized"
            or getattr(command, "domain", None) != "social_scheduling"
            or getattr(command, "operation", None)
            not in {"create_shared_reminder", "detect_and_create_shared_reminder"}
        ):
            continue
        payload = getattr(command, "command_payload", {})
        if not isinstance(payload, Mapping):
            continue
        intent_id = payload.get("recoverable_scheduling_intent_id")
        facts_hash = payload.get("facts_hash")
        if not isinstance(intent_id, str) or not isinstance(facts_hash, str):
            continue
        try:
            service.consume_recoverable_intent(
                intent_id,
                facts_hash=facts_hash,
                consumed_turn_id=turn_id,
            )
        except ValueError:
            continue


def _social_scheduling_outcomes_from_tool_events(
    tool_events: tuple[Mapping[str, Any], ...],
) -> list[Mapping[str, Any]]:
    outcomes: list[Mapping[str, Any]] = []
    for event in tool_events:
        outcome = _social_scheduling_outcome_from_event(event)
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


def _social_scheduling_outcome_from_event(
    event: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    facts = event.get("facts")
    if not isinstance(facts, Mapping):
        return None
    outcome = facts.get("social_scheduling_outcome")
    if not isinstance(outcome, Mapping):
        return None
    return dict(outcome)


def _social_scheduling_outcome_model(
    outcome: Mapping[str, Any],
) -> SocialSchedulingOutcome | None:
    local_trigger_at = _optional_local_datetime(outcome.get("local_trigger_at"))
    if outcome.get("local_trigger_at") is not None and local_trigger_at is None:
        return None
    participant_ids = outcome.get("participant_account_ids")
    if not isinstance(participant_ids, list | tuple):
        participant_ids = ()
    return SocialSchedulingOutcome(
        outcome_id=str(outcome.get("outcome_id") or ""),
        operation=str(outcome.get("operation") or ""),
        status=str(outcome.get("status") or "invalid"),  # type: ignore[arg-type]
        staged_command_id=_optional_str(outcome.get("staged_command_id")),
        shared_reminder_id=_optional_str(outcome.get("shared_reminder_id")),
        title=_optional_str(outcome.get("title")),
        local_trigger_at=local_trigger_at,
        captured_timezone=_optional_str(outcome.get("captured_timezone")),
        duration_minutes=_optional_int(outcome.get("duration_minutes")),
        participant_account_ids=tuple(str(item) for item in participant_ids),
        blocker=_optional_str(outcome.get("blocker")),
        facts_hash=_optional_str(outcome.get("facts_hash")),
        recoverable_scheduling_intent_id=_optional_str(
            outcome.get("recoverable_scheduling_intent_id")
        ),
    )


def _unresolved_friend_reference_from_event(event: Mapping[str, Any]) -> str | None:
    facts = event.get("facts")
    if not isinstance(facts, Mapping):
        return None
    follow_up_facts = facts.get("follow_up_facts")
    if isinstance(follow_up_facts, Mapping):
        value = follow_up_facts.get("unresolved_reference_text")
        if isinstance(value, str) and value.strip():
            return value.strip()
    outcome = facts.get("social_scheduling_outcome")
    if isinstance(outcome, Mapping):
        value = outcome.get("unresolved_reference_text")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_input_window(
    current_input_messages: tuple[Any, ...],
) -> tuple[int, int, tuple[str, ...]]:
    seqs = [
        seq
        for message in current_input_messages
        if isinstance(seq := getattr(message, "seq", None), int)
    ]
    message_ids = tuple(
        message_id
        for message in current_input_messages
        if isinstance(message_id := getattr(message, "message_id", None), str)
        and message_id
    )
    if not seqs:
        return 0, 0, message_ids
    return min(seqs), max(seqs), message_ids


def _optional_local_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _agent_run_id_for_trigger(trigger: TurnTrigger, *, fallback: str) -> str:
    value = trigger.agent_run_id
    return value if isinstance(value, str) and value else fallback


def _reminder_fire_domain_result(
    provider: ReminderFireFactsPort | None,
    trigger: TurnTrigger,
) -> dict[str, Any] | None:
    if trigger.trigger_type != "ReminderFireTurn":
        return None
    if provider is None:
        raise ValueError("reminder_fire_facts_unavailable")
    fire_ids = _string_list(trigger.payload.get("fire_ids"))
    facts = provider.reminder_fire_render_facts(
        owner_account_id=trigger.account_id,
        fire_ids=fire_ids,
        viewer_account_id=trigger.account_id,
    )
    reminders = [_object_mapping(fact) for fact in facts]
    return {
        "domain": "reminder",
        "intent": "render reminder fire fact",
        "action": "ReminderFireTurn",
        "effect": "ready",
        "intent_fulfilled": True,
        "visible_summary": "; ".join(
            str(item.get("title") or "") for item in reminders
        ),
        "reply_contract": "render_reminder_fire",
        "privacy_notes": [
            (
                "Render only these reminder facts; do not use chat history for "
                "title, time, participant, duration, or kind."
            )
        ],
        "facts": {
            "viewer_account_id": trigger.account_id,
            "fire_ids": fire_ids,
            "reminders": reminders,
        },
    }


def _object_mapping(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {key: item for key, item in vars(value).items() if not key.startswith("_")}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list | tuple):
        values = list(value)
    else:
        values = []
    return [item for item in values if isinstance(item, str) and item]


def _render_fact_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    message = str(error)
    return message if message else "render_facts_unavailable"


def _validate_for_trigger(
    trigger: TurnTrigger,
    validated: ValidatedOutput,
) -> ValidatedOutput:
    if (
        trigger.trigger_type == "NotificationTurn"
        and validated.valid
        and validated.kind == "no_reply"
    ):
        return ValidatedOutput(
            valid=False,
            kind=None,
            reason_code=NOTIFICATION_VISIBLE_REPLY_REQUIRED,
            retry_guidance=(
                "NotificationTurn must render a visible reply from notification "
                "facts; no_reply is not allowed."
            ),
        )
    return validated


def _validate_reminder_fire_output(
    request: AgentRequest,
    validated: ValidatedOutput,
) -> ValidatedOutput:
    if request.trigger_type != "ReminderFireTurn":
        return validated
    facts = _reminder_fire_guard_facts(request)
    if not facts:
        return ValidatedOutput(
            valid=False,
            kind=None,
            reason_code=REMINDER_FIRE_FACT_MISMATCH,
            retry_guidance="reminder_fire_trusted_facts_required",
        )
    if not validated.valid or validated.kind != "reply":
        return ValidatedOutput(
            valid=False,
            kind=None,
            reason_code=REMINDER_FIRE_VISIBLE_REPLY_REQUIRED,
            retry_guidance="reminder_fire_must_reply_from_trusted_facts",
        )
    text = "\n".join(validated.segments)
    if _contains_serialized_tool_call(text):
        return ValidatedOutput(
            valid=False,
            kind=None,
            reason_code=REMINDER_FIRE_FACT_MISMATCH,
            retry_guidance="serialized_tool_call_output_requires_native_tool_call",
        )
    for fact in facts:
        if not _reminder_fire_fact_ready(fact):
            return ValidatedOutput(
                valid=False,
                kind=None,
                reason_code=REMINDER_FIRE_FACT_MISMATCH,
                retry_guidance="reminder_fire_trusted_facts_required",
            )
        title = str(fact.get("title") or "").strip()
        if title not in text:
            return ValidatedOutput(
                valid=False,
                kind=None,
                reason_code=REMINDER_FIRE_FACT_MISMATCH,
                retry_guidance="reminder_fire_title_must_match_trusted_fact",
            )
        if not _has_trusted_time_or_remaining_token(text, fact, request):
            return ValidatedOutput(
                valid=False,
                kind=None,
                reason_code=REMINDER_FIRE_FACT_MISMATCH,
                retry_guidance="reminder_fire_time_must_match_trusted_fact",
            )
    return validated


@dataclass(frozen=True, slots=True)
class _RecoveryGrounding:
    intent: str
    ask: str


def _grounded_recovery_text(
    request: AgentRequest,
    *,
    tool_events: tuple[Mapping[str, Any], ...],
) -> str | None:
    if request.trigger_type != "InboundTurn":
        return None
    grounding = (
        _recovery_grounding_from_staged_commands(request)
        or _recovery_grounding_from_tool_events(tool_events)
        or _recovery_grounding_from_input(request)
    )
    if grounding is None:
        return None
    return f"我没能帮你完成「{grounding.intent}」，{grounding.ask}"


def _recovery_grounding_from_staged_commands(
    request: AgentRequest,
) -> _RecoveryGrounding | None:
    runtime = getattr(request.freshness_guard, "conversation_runtime", None)
    repository = getattr(runtime, "repository", None)
    staged_commands_for_turn = getattr(repository, "staged_commands_for_turn", None)
    if not callable(staged_commands_for_turn):
        return None
    for command in staged_commands_for_turn(request.turn_id):
        if getattr(command, "status", None) != "staged":
            continue
        intent = _recovery_intent_from_staged_command(command)
        if intent is not None:
            return _RecoveryGrounding(
                intent=intent,
                ask="请再说一次或确认后重试。",
            )
    return None


def _recovery_intent_from_staged_command(command: Any) -> str | None:
    payload = getattr(command, "command_payload", {})
    if isinstance(payload, Mapping):
        raw_text = _clean_recovery_text(payload.get("raw_text"))
        title = _clean_recovery_text(payload.get("title"))
        if (
            raw_text is not None
            and title is None
            and getattr(command, "operation", None)
            == "detect_and_create_shared_reminder"
        ):
            return raw_text
    preview_facts = getattr(command, "preview_facts", {})
    if isinstance(preview_facts, Mapping):
        outcome = preview_facts.get("social_scheduling_outcome")
        if isinstance(outcome, Mapping):
            intent = _recovery_intent_from_social_outcome(outcome)
            if intent is not None:
                return intent
    if not isinstance(payload, Mapping):
        return None
    title = _clean_recovery_text(
        payload.get("title")
        or payload.get("content")
        or payload.get("text")
        or payload.get("summary")
    )
    local_time = _clean_recovery_text(
        payload.get("local_trigger_at") or payload.get("due_at") or payload.get("time")
    )
    participants = _clean_recovery_text(_recovery_participants(payload))
    pieces = [piece for piece in (title, local_time, participants) if piece]
    if pieces:
        return " ".join(pieces)
    operation = _clean_recovery_text(getattr(command, "operation", None))
    if operation is None:
        return None
    return operation.replace("_", " ")


def _recovery_grounding_from_tool_events(
    tool_events: tuple[Mapping[str, Any], ...],
) -> _RecoveryGrounding | None:
    for event in tool_events:
        if not isinstance(event, Mapping):
            continue
        facts = event.get("facts")
        if not isinstance(facts, Mapping):
            continue
        outcome = facts.get("social_scheduling_outcome")
        outcome_mapping = outcome if isinstance(outcome, Mapping) else None
        intent = (
            _recovery_intent_from_social_outcome(outcome_mapping)
            if outcome_mapping is not None
            else None
        )
        if intent is None:
            intent = _clean_recovery_text(facts.get("title"))
        ask = _recovery_ask_from_structured_facts(facts, outcome_mapping)
        if ask is not None:
            return _RecoveryGrounding(
                intent=intent or "这次请求",
                ask=ask,
            )
    return None


def _recovery_ask_from_structured_facts(
    facts: Mapping[str, Any],
    outcome: Mapping[str, Any] | None,
) -> str | None:
    follow_up_facts = facts.get("follow_up_facts")
    if not isinstance(follow_up_facts, Mapping):
        follow_up_facts = {}
    status = _clean_recovery_text(
        (outcome or {}).get("status") or facts.get("status") or facts.get("type")
    )
    missing = _clean_recovery_text(follow_up_facts.get("missing"))
    blocker = _clean_recovery_text(
        (outcome or {}).get("blocker") or follow_up_facts.get("reason")
    )
    if missing == "time" or status in {
        "needs_time",
        "needs_past_time_confirmation",
        "needs_incomplete_date_clarification",
    }:
        return "请补充具体时间后再发一次。"
    if missing == "title" or status == "needs_title":
        return "请补充要安排的内容后再发一次。"
    if missing in {"participants", "participant"} or status == "needs_participants":
        return "请补充参与人后再发一次。"
    if blocker == "ambiguous_friend":
        return "请确认具体是哪位参与人后再发一次。"
    if blocker in {"unmatched_friend", "receiver_not_active_friend"}:
        return "请确认参与人名称后再发一次。"
    if blocker in {"receiver_conflict", "unreachable_participant"}:
        return "请调整参与人或时间后再发一次。"
    if outcome is not None:
        return "请再说一次或补充关键信息。"
    return None


def _recovery_grounding_from_input(request: AgentRequest) -> _RecoveryGrounding | None:
    texts = [
        text
        for message in request.current_input_messages
        if (text := _clean_recovery_text(getattr(message, "text", None))) is not None
    ]
    if not texts:
        payload_text = _clean_recovery_text(request.payload.get("text"))
        if payload_text is not None:
            texts.append(payload_text)
    if not texts:
        return None
    return _RecoveryGrounding(
        intent="；".join(texts),
        ask="请再说一次或补充关键信息。",
    )


def _recovery_intent_from_social_outcome(
    outcome: Mapping[str, Any] | None,
) -> str | None:
    if outcome is None:
        return None
    title = _clean_recovery_text(outcome.get("title"))
    local_time = _clean_recovery_text(outcome.get("local_trigger_at"))
    participants = _clean_recovery_text(_recovery_participants(outcome))
    pieces = [piece for piece in (title, local_time, participants) if piece]
    if not pieces:
        return None
    return " ".join(pieces)


def _recovery_participants(source: Mapping[str, Any]) -> str | None:
    value = source.get("participant_account_ids") or source.get("receiver_account_ids")
    if isinstance(value, str):
        return value
    if isinstance(value, list | tuple):
        participants = [item for item in value if isinstance(item, str) and item]
        if participants:
            return "、".join(participants)
    return None


def _clean_recovery_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\n", " ").strip()
    if not text:
        return None
    if len(text) > 120:
        return f"{text[:117]}..."
    return text


def _minimal_reminder_fire_reply(request: AgentRequest) -> ValidatedOutput | None:
    if request.trigger_type != "ReminderFireTurn":
        return None
    facts = _reminder_fire_guard_facts(request)
    if not facts or any(not _reminder_fire_fact_ready(fact) for fact in facts):
        return None
    segments: list[str] = []
    for fact in facts:
        local_due = _parse_datetime(str(fact["local_due_at"]))
        if local_due is None:
            return None
        segments.append(
            f'{fact["title"]} {local_due:%Y-%m-%d %H:%M} {fact["timezone"]}'
        )
    return ValidatedOutput(
        valid=True,
        kind="reply",
        segments=tuple(segments),
        reason_code="reply_ready",
    )


def _reminder_fire_guard_facts(request: AgentRequest) -> list[Mapping[str, Any]]:
    domain_result = request.trusted_facts.get("domain_result")
    if not isinstance(domain_result, Mapping):
        return []
    if domain_result.get("reply_contract") != "render_reminder_fire":
        return []
    facts = domain_result.get("facts")
    if not isinstance(facts, Mapping):
        return []
    reminders = facts.get("reminders")
    if not isinstance(reminders, list):
        return []
    return [reminder for reminder in reminders if isinstance(reminder, Mapping)]


def _reminder_fire_fact_ready(fact: Mapping[str, Any]) -> bool:
    required = (
        "fire_id",
        "reminder_id",
        "title",
        "owner_account_id",
        "viewer_account_id",
        "due_at",
        "local_due_at",
        "timezone",
        "duration_minutes",
        "kind",
    )
    return all(str(fact.get(key) or "").strip() for key in required)


def _has_trusted_time_or_remaining_token(
    text: str,
    fact: Mapping[str, Any],
    request: AgentRequest,
) -> bool:
    tokens = _trusted_time_tokens(fact)
    tokens.extend(_trusted_remaining_tokens(fact, request))
    return any(token and token in text for token in tokens)


def _trusted_time_tokens(fact: Mapping[str, Any]) -> list[str]:
    local_due_at = str(fact.get("local_due_at") or "").strip()
    local_due = _parse_datetime(local_due_at)
    tokens = [local_due_at]
    if local_due is not None:
        tokens.extend(
            [
                f"{local_due:%Y-%m-%d %H:%M}",
                f"{local_due:%H:%M}",
            ]
        )
    return list(dict.fromkeys(token for token in tokens if token))


def _trusted_remaining_tokens(
    fact: Mapping[str, Any],
    request: AgentRequest,
) -> list[str]:
    due_at = _parse_datetime(str(fact.get("due_at") or ""))
    current_time = _parse_datetime(str(request.trusted_facts.get("current_time") or ""))
    if due_at is None or current_time is None:
        return []
    minutes = round((due_at - current_time).total_seconds() / 60)
    tokens = [
        f"{minutes}分钟",
        f"{minutes} minutes",
        f"{minutes} minute",
    ]
    if minutes % 60 == 0:
        hours = minutes // 60
        tokens.extend(
            [
                f"{hours}小时",
                f"{hours} hour",
                f"{hours} hours",
            ]
        )
    return tokens


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _contains_serialized_tool_call(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "<tool_call",
            "</tool_call",
            "<minimax:tool_call",
            "<invoke name=",
            "</arg_value>",
            "_model_supplied_args",
        )
    )


def _trusted_facts_for_agent(
    trust_facts: dict[str, Any],
    *,
    trigger: TurnTrigger,
    semantic_decision: SemanticDecision | None,
    now: Callable[[], datetime],
    account_timezone: Callable[[str], str | None] | None = None,
    onboarding_guidance_required: bool = False,
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
    if onboarding_guidance_required:
        facts["onboarding_guidance"] = _onboarding_guidance_fact(facts)
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


def _add_recoverable_scheduling_context(
    trusted_facts: Mapping[str, Any],
    *,
    service: Any | None,
    trigger: TurnTrigger,
    semantic_decision: SemanticDecision,
) -> dict[str, Any]:
    facts = dict(trusted_facts)
    action = semantic_decision.follow_up_action
    if (
        service is None
        or action is None
        or action.type != "resolve_friend_reference_correction"
        or action.scope != "immediately_preceding_unresolved_intent"
    ):
        return facts
    intent = service.recoverable_intent_for_correction(
        conversation_id=trigger.conversation_id,
        prior_reference_text=action.prior_reference_text,
    )
    if intent is None:
        return facts
    resolution = service.resolve_active_friend_reference(
        trigger.account_id,
        action.corrected_friend_text,
    )
    if resolution.status == "matched" and resolution.matched_account_id:
        facts["recoverable_scheduling_intent"] = {
            "id": intent.id,
            "operation": intent.operation,
            "facts_hash": intent.facts_hash,
            "title": intent.title,
            "local_trigger_at": intent.local_trigger_at.isoformat(),
            "captured_timezone": intent.captured_timezone,
            "duration_minutes": intent.duration_minutes,
            "unresolved_reference_text": intent.unresolved_reference_text,
            "corrected_friend_text": action.corrected_friend_text,
            "resolved_friend_account_id": resolution.matched_account_id,
            "source_turn_id": intent.source_turn_id,
            "instruction": (
                "Use this trusted recoverable intent only for the current turn. "
                "Call social_scheduling_tool create_shared_reminder with "
                "recoverable_scheduling_intent_id and facts_hash; do not store "
                "the corrected friend as an alias."
            ),
        }
        return facts
    facts["recoverable_scheduling_intent_resolution"] = {
        "status": resolution.status,
        "prior_reference_text": action.prior_reference_text,
        "corrected_friend_text": action.corrected_friend_text,
        "candidate_account_ids": list(resolution.candidates),
        "instruction": (
            "Ask one concise confirmation about which active friend to use. "
            "Do not treat this as approval for a pending command."
        ),
    }
    return facts


def _onboarding_guidance_fact(facts: Mapping[str, Any]) -> dict[str, Any]:
    memory_enabled = bool(facts.get("memory_enabled", True))
    supported_capabilities = [
        "reminders",
        "shared_reminders_with_friends",
        "availability_checks",
    ]
    if memory_enabled:
        supported_capabilities.append("long_term_memory_preferences")
    guidance = {
        "assistant_name": facts.get("assistant_name") or "Coke",
        "supported_capabilities": supported_capabilities,
        "memory_enabled": memory_enabled,
        "proactive_enabled": bool(facts.get("proactive_enabled", True)),
        "instruction": (
            "Offer concise first-use guidance while still responding to the user's "
            "current message. Mention only supported capabilities."
        ),
    }
    user_address_name = facts.get("user_address_name")
    if isinstance(user_address_name, str) and user_address_name.strip():
        guidance["user_address_name"] = user_address_name.strip()
    agent_settings = facts.get("agent_settings")
    if isinstance(agent_settings, Mapping):
        guidance["configured_settings"] = {
            key: agent_settings[key]
            for key in (
                "assistant_name",
                "user_address_name",
                "persona",
                "speaking_style",
                "extra_rules",
                "proactive_enabled",
                "memory_enabled",
            )
            if key in agent_settings and agent_settings[key] not in (None, "")
        }
    return guidance


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


SHORT_AFFIRMATIVE_TEXTS = {
    "yes",
    "y",
    "yeah",
    "yep",
    "ok",
    "okay",
    "sure",
    "confirm",
    "confirmed",
    "是",
    "是的",
    "对",
    "对的",
    "嗯",
    "好",
    "好的",
    "可以",
    "确认",
}


def _clear_context_clarification_for_followup_answer(
    decision: SemanticDecision,
    trigger: TurnTrigger,
) -> SemanticDecision:
    if decision.required_clarification != "ask_context":
        return decision
    if decision.ambiguity != "missing_context":
        return decision
    if not _is_concise_followup_answer_payload(trigger.payload):
        return decision
    return replace(decision, ambiguity="clear", required_clarification="none")


def _is_concise_followup_answer_payload(payload: Mapping[str, Any]) -> bool:
    text = str(payload.get("text") or payload.get("input") or "").strip()
    if not text:
        return False
    normalized = text.casefold().strip(" \t\r\n.!?。！？~～")
    if normalized in SHORT_AFFIRMATIVE_TEXTS:
        return True
    if any(mark in text for mark in ("?", "？")):
        return False
    return len(text) <= 40 and len(text.split()) <= 4


def _tool_profile_for_interactive_decision(
    semantic_decision: SemanticDecision,
    *,
    trusted_facts: Mapping[str, Any],
    tool_ports: AgentToolPorts,
) -> ToolProfile:
    if "recoverable_scheduling_intent_resolution" in trusted_facts:
        return ToolProfile.clarification()
    if semantic_decision.required_clarification != "none":
        return ToolProfile.clarification()
    return ToolProfile.interactive(tool_ports)


def _requires_social_scheduling_claim(request: AgentRequest) -> bool:
    if request.trigger_type != "InboundTurn":
        return False
    if not getattr(request.tool_profile, "intent_tools_enabled", False):
        return False
    if getattr(request.tool_profile, "social_scheduling_tool", None) is None:
        return False
    semantic = request.trusted_facts.get("semantic_decision")
    if not isinstance(semantic, Mapping):
        return "recoverable_scheduling_intent" in request.trusted_facts
    return (
        semantic.get("intent_family") == "scheduling"
        and semantic.get("intent_action") == "create_shared_reminder"
    )


def _require_agent_visibility_for_inbound_no_reply(
    decision: SemanticDecision,
) -> SemanticDecision:
    if decision.reply_necessity != "intentional_no_reply":
        return decision
    return replace(decision, reply_necessity="reply_needed")


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


def _user_text_from_payload(payload: Mapping[str, Any]) -> str:
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return json.dumps(payload, ensure_ascii=False, default=str)


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


def _outbound_message_id_for_segment(
    outbound_messages: list[Any], segment_index: int
) -> str | None:
    for message in outbound_messages:
        if getattr(message, "segment_index", None) == segment_index:
            return message.id
    return None


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


def _traceparent_from_trigger(trigger: TurnTrigger) -> str | None:
    direct = trigger.payload.get("traceparent")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    nested = trigger.payload.get("payload")
    if isinstance(nested, dict):
        traceparent = nested.get("traceparent")
        if isinstance(traceparent, str) and traceparent.strip():
            return traceparent.strip()
    return None
