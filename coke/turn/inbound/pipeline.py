from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from coke.turn.inbound.close import CloseCoordinator, CloseRequest, CloseResult
from coke.turn.inbound.contracts import (
    ActionOutcome,
    CompiledPlan,
    PendingClarification,
    SettledOutcome,
    TurnPlan,
)
from coke.turn.inbound.execute import ActionExecutor, ActionHandler
from coke.turn.inbound.express import ExpressOutputError, ExpressRequest
from coke.turn.inbound.pending import PendingClarificationPort
from coke.turn.inbound.plan import Planner, PlanRequest
from coke.turn.inbound.plan_compile import compile_plan
from coke.turn.inbound.time_display import attach_time_display_fields


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
    current_input_messages: Sequence[Mapping[str, Any]] = ()
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
            "current_input_messages",
            tuple(dict(item) for item in self.current_input_messages),
        )
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
            compiled_plan,
            guard,
            turn_id=request.turn_id,
            action_context=_action_context(request),
        )
        resolves_pending_fingerprint = _resolved_pending_fingerprint(plan, pending)

        if (
            plan.reply_necessity == "intentional_no_reply"
            and not settled_outcome.outcomes
        ):
            segments: tuple[str, ...] = ()
            streamed = False
            close_result = self._close_coordinator.commit(
                CloseRequest(
                    turn_id=request.turn_id,
                    conversation_id=request.conversation_id,
                    plan=plan,
                    settled_outcome=settled_outcome,
                    segments=segments,
                    source_input_window=request.source_input_window,
                    pending_expires_at=request.pending_expires_at,
                ),
                guard,
            )
            delivery_segments: tuple[str, ...] = ()
            recovered = False
        else:
            try:
                streamed_segments: list[str] = []
                async for segment in self._express.render_streaming(
                    _express_request(request, settled_outcome)
                ):
                    streamed_segments.append(segment)
                segments = tuple(streamed_segments)
                streamed = True
                close_result = self._close_coordinator.commit(
                    CloseRequest(
                        turn_id=request.turn_id,
                        conversation_id=request.conversation_id,
                        plan=plan,
                        settled_outcome=settled_outcome,
                        segments=segments,
                        source_input_window=request.source_input_window,
                        pending_expires_at=request.pending_expires_at,
                    ),
                    guard,
                )
                delivery_segments = segments
                recovered = False
            except ExpressOutputError:
                segments = _recovery_segments_from_settled_outcome(settled_outcome)
                streamed = False
                close_result = self._close_coordinator.commit_recovery(
                    CloseRequest(
                        turn_id=request.turn_id,
                        conversation_id=request.conversation_id,
                        plan=plan,
                        settled_outcome=settled_outcome,
                        segments=segments,
                        source_input_window=request.source_input_window,
                        pending_expires_at=request.pending_expires_at,
                    ),
                    guard,
                )
                delivery_segments = segments
                recovered = True
        if close_result.committed:
            if resolves_pending_fingerprint is not None:
                self._pending_store.consume(
                    request.conversation_id,
                    resolves_pending_fingerprint,
                    now=request.now,
                )
            for segment in delivery_segments:
                delivery_port.deliver(request.turn_id, segment)

        return TurnPipelineResult(
            plan=plan,
            compiled_plan=compiled_plan,
            settled_outcome=close_result.settled_outcome,
            segments=segments if close_result.committed else (),
            close_result=close_result,
            streamed=streamed and not recovered,
        )


def _action_context(request: TurnPipelineRequest) -> dict[str, Any]:
    # Authenticated trusted context injected into every action's params. The
    # planner never provides account ids or timezone; they come from the turn.
    timezone = str(request.trusted_facts.get("default_timezone") or "UTC")
    context = {
        "account_id": request.account_id,
        "owner_account_id": request.account_id,
        "creator_account_id": request.account_id,
        "requester_account_id": request.account_id,
        "conversation_id": request.conversation_id,
        "captured_timezone": timezone,
        "requester_timezone": timezone,
        "display_timezone": timezone,
    }
    current_input_text = _current_input_text(request)
    if current_input_text is not None:
        context["_current_input_text"] = current_input_text
    return context


def _current_input_text(request: TurnPipelineRequest) -> str | None:
    texts = [
        text
        for message in request.current_input_messages
        if isinstance(text := message.get("content"), str) and text.strip()
    ]
    if not texts:
        payload_text = request.payload.get("text")
        if isinstance(payload_text, str) and payload_text.strip():
            texts.append(payload_text)
    if not texts:
        return None
    return "\n".join(text.strip() for text in texts)


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
        current_input_messages=request.current_input_messages,
        conversation_history=request.conversation_history,
        focus_subject=request.focus_subject,
    )


def _express_request(
    request: TurnPipelineRequest,
    settled_outcome: SettledOutcome,
) -> ExpressRequest:
    onboarding_guidance = request.trusted_facts.get("onboarding_guidance")
    current_time = str(request.trusted_facts.get("current_time") or "")
    default_timezone = str(
        request.trusted_facts.get("default_timezone")
        or request.trusted_facts.get("timezone")
        or "UTC"
    )
    return ExpressRequest(
        turn_id=request.turn_id,
        conversation_id=request.conversation_id,
        account_id=request.account_id,
        current_time=current_time,
        default_timezone=default_timezone,
        settled_outcome=_settled_outcome_with_time_display(
            settled_outcome,
            current_time=current_time,
            default_timezone=default_timezone,
        ),
        current_input_messages=request.current_input_messages,
        conversation_history=request.conversation_history,
        persona=request.persona,
        assistant_name=request.assistant_name,
        user_address_name=request.user_address_name,
        payload=request.payload,
        run_id=request.run_id,
        onboarding_guidance=(
            dict(onboarding_guidance)
            if isinstance(onboarding_guidance, Mapping)
            else None
        ),
    )


def _settled_outcome_with_time_display(
    settled_outcome: SettledOutcome,
    *,
    current_time: str,
    default_timezone: str,
) -> SettledOutcome:
    return SettledOutcome(
        outcomes=tuple(
            ActionOutcome(
                category=outcome.category,
                status=outcome.status,
                data=attach_time_display_fields(
                    outcome.data,
                    now=current_time,
                    timezone_name=default_timezone,
                ),
            )
            for outcome in settled_outcome.outcomes
        )
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


def _recovery_segments_from_settled_outcome(
    settled_outcome: SettledOutcome,
) -> tuple[str, ...]:
    return (_recovery_text_from_settled_outcome(settled_outcome),)


def _recovery_text_from_settled_outcome(settled_outcome: SettledOutcome) -> str:
    if not settled_outcome.outcomes:
        return "我这边处理时正常回复失败了，请再说一次。"
    if len(settled_outcome.outcomes) > 1:
        return "我已经处理了这次请求，但正常回复失败了。请查看结果或再说一次。"

    outcome = settled_outcome.outcomes[0]
    summary = _outcome_summary(outcome.data)
    suffix = f"：{summary}" if summary else ""
    if outcome.status == "needs_past_time_confirmation":
        return f"这个时间看起来已经过去了{suffix}。请确认是否仍要继续。"
    if outcome.category == "done":
        verb = _done_recovery_verb(outcome.status)
        return f"我已经{verb}{suffix}。刚才正常回复失败了。"
    if outcome.category in {"needs_choice", "needs_input", "needs_confirmation"}:
        return f"还需要你确认或补充信息{suffix}。刚才正常回复失败了。"
    if outcome.category == "not_possible":
        return f"这次请求没有完成{suffix}。刚才正常回复失败了。"
    return f"我已经处理了这次请求{suffix}。刚才正常回复失败了。"


def _done_recovery_verb(status: str) -> str:
    if status in {"created", "scheduled"}:
        return "创建"
    if status in {"updated", "rescheduled"}:
        return "更新"
    if status in {"cancelled", "deleted", "completed"}:
        return "处理"
    if status == "partial":
        return "完成了部分操作"
    return "完成"


def _outcome_summary(data: Mapping[str, Any]) -> str | None:
    parts: list[str] = []
    for key in (
        "content",
        "title",
        "text",
        "summary",
        "time_phrase",
        "local_trigger_at",
        "trigger_at",
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    if not parts:
        reminder = data.get("reminder")
        if isinstance(reminder, Mapping):
            return _outcome_summary(reminder)
    if not parts:
        succeeded = data.get("succeeded")
        if isinstance(succeeded, Sequence) and not isinstance(succeeded, str):
            for item in succeeded:
                if isinstance(item, Mapping):
                    summary = _outcome_summary(item)
                    if summary:
                        parts.append(summary)
                        break
    return " ".join(dict.fromkeys(parts)) or None
