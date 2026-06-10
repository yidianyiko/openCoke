from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from coke.turn.v2.close import CloseCoordinator, CloseRequest, CloseResult
from coke.turn.v2.contracts import (
    ActionOutcome,
    CompiledPlan,
    PendingClarification,
    SettledOutcome,
    TurnPlan,
)
from coke.turn.v2.execute import ActionExecutor, ActionHandler
from coke.turn.v2.express import ExpressRequest
from coke.turn.v2.pending import PendingClarificationPort
from coke.turn.v2.plan import Planner, PlanRequest
from coke.turn.v2.plan_compile import compile_plan


class ExpressPort(Protocol):
    def render(self, request: ExpressRequest) -> tuple[str, ...]: ...

    def render_streaming(self, request: ExpressRequest) -> Any: ...


class SegmentDeliveryPort(Protocol):
    def deliver(self, turn_id: str, segment: str) -> None: ...


class NullSegmentDelivery:
    def deliver(self, turn_id: str, segment: str) -> None:
        return None


@dataclass(frozen=True, slots=True)
class TurnPipelineRequest:
    turn_id: str
    account_id: str
    conversation_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    trusted_facts: Mapping[str, Any] = field(default_factory=dict)
    focus_subject: Any | None = None
    conversation_history: Sequence[Mapping[str, Any]] = ()
    persona: str = ""
    assistant_name: str = "Coke"
    user_address_name: str = ""
    source_input_window: tuple[int, int] | None = None
    pending_expires_at: datetime | None = None
    now: datetime | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "trusted_facts", dict(self.trusted_facts))
        object.__setattr__(
            self,
            "conversation_history",
            tuple(dict(item) for item in self.conversation_history),
        )


@dataclass(frozen=True, slots=True)
class TurnPipelineResult:
    plan: TurnPlan
    compiled_plan: CompiledPlan
    settled_outcome: SettledOutcome
    segments: tuple[str, ...]
    close_result: CloseResult
    streamed: bool


class TurnPipeline:
    def __init__(
        self,
        *,
        planner: Planner,
        handlers: Mapping[str, ActionHandler],
        express: ExpressPort,
        close_coordinator: CloseCoordinator,
        pending_store: PendingClarificationPort,
        delivery: SegmentDeliveryPort | None = None,
        compile: Callable[[TurnPlan], CompiledPlan] = compile_plan,
    ) -> None:
        self._planner = planner
        self._executor = ActionExecutor(handlers)
        self._express = express
        self._close_coordinator = close_coordinator
        self._pending_store = pending_store
        self._delivery = delivery or NullSegmentDelivery()
        self._compile = compile

    async def run(
        self,
        request: TurnPipelineRequest,
        guard: Any,
        delivery: SegmentDeliveryPort | None = None,
    ) -> TurnPipelineResult:
        delivery_port = delivery or self._delivery
        pending = self._pending_store.open_for_conversation(
            request.conversation_id,
            now=request.now,
        )
        plan = self._planner.plan(_plan_request(request, pending))
        compiled_plan = self._compile(plan)
        settled_outcome = self._executor.execute(
            compiled_plan, guard, _action_context(request)
        )
        staged_command_ids = _staged_command_ids(settled_outcome)
        resolves_pending_fingerprint = _resolved_pending_fingerprint(plan, pending)

        if plan.reply_necessity == "intentional_no_reply":
            segments: tuple[str, ...] = ()
            streamed = False
        elif staged_command_ids:
            segments = self._express.render(_express_request(request, settled_outcome))
            streamed = False
        else:
            streamed_segments: list[str] = []
            async for segment in self._express.render_streaming(
                _express_request(request, settled_outcome)
            ):
                streamed_segments.append(segment)
                delivery_port.deliver(request.turn_id, segment)
            segments = tuple(streamed_segments)
            streamed = True

        close_result = self._close_coordinator.commit(
            CloseRequest(
                turn_id=request.turn_id,
                conversation_id=request.conversation_id,
                plan=plan,
                settled_outcome=settled_outcome,
                segments=segments,
                selected_staged_command_ids=staged_command_ids,
                source_input_window=request.source_input_window,
                pending_expires_at=request.pending_expires_at,
            ),
            guard,
        )
        if close_result.committed:
            if resolves_pending_fingerprint is not None:
                self._pending_store.consume(
                    request.conversation_id,
                    resolves_pending_fingerprint,
                    now=request.now,
                )
            if staged_command_ids:
                for segment in segments:
                    delivery_port.deliver(request.turn_id, segment)

        return TurnPipelineResult(
            plan=plan,
            compiled_plan=compiled_plan,
            settled_outcome=close_result.settled_outcome,
            segments=segments if close_result.committed or streamed else (),
            close_result=close_result,
            streamed=streamed,
        )


def _action_context(request: TurnPipelineRequest) -> dict[str, Any]:
    # Authenticated trusted context injected into every action's params. The
    # planner never provides account ids or timezone; they come from the turn.
    timezone = str(request.trusted_facts.get("default_timezone") or "UTC")
    return {
        "account_id": request.account_id,
        "owner_account_id": request.account_id,
        "creator_account_id": request.account_id,
        "requester_account_id": request.account_id,
        "conversation_id": request.conversation_id,
        "captured_timezone": timezone,
        "requester_timezone": timezone,
        "display_timezone": timezone,
    }


def _plan_request(
    request: TurnPipelineRequest,
    pending: PendingClarification | None,
) -> PlanRequest:
    trusted_facts = dict(request.trusted_facts)
    if pending is not None:
        trusted_facts["pending_clarification"] = _pending_payload(pending)
    return PlanRequest(
        account_id=request.account_id,
        conversation_id=request.conversation_id,
        payload=request.payload,
        trusted_facts=trusted_facts,
        conversation_history=request.conversation_history,
        focus_subject=request.focus_subject,
    )


def _express_request(
    request: TurnPipelineRequest,
    settled_outcome: SettledOutcome,
) -> ExpressRequest:
    return ExpressRequest(
        turn_id=request.turn_id,
        conversation_id=request.conversation_id,
        account_id=request.account_id,
        settled_outcome=settled_outcome,
        conversation_history=request.conversation_history,
        persona=request.persona,
        assistant_name=request.assistant_name,
        user_address_name=request.user_address_name,
        payload=request.payload,
        run_id=request.run_id,
    )


def _staged_command_ids(settled_outcome: SettledOutcome) -> tuple[str, ...]:
    return tuple(
        outcome.staged_command_id
        for outcome in settled_outcome.outcomes
        if outcome.staged_command_id
    )


def _resolved_pending_fingerprint(
    plan: TurnPlan,
    pending: PendingClarification | None,
) -> str | None:
    if pending is None:
        return None
    fingerprint = pending.unresolved_action_fingerprint
    for action in plan.actions:
        if action.params.get("resolves_pending_fingerprint") == fingerprint:
            return fingerprint
    return None


def _pending_payload(pending: PendingClarification) -> dict[str, Any]:
    return {
        "unresolved_action_fingerprint": pending.unresolved_action_fingerprint,
        "candidates": [dict(candidate) for candidate in pending.candidates],
        "source_input_window": list(pending.source_input_window),
        "expires_at": pending.expires_at.isoformat(),
        "status": pending.status,
    }
