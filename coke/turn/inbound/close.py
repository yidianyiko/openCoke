from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol, Sequence

from coke.turn.inbound.contracts import (
    ActionOutcome,
    PendingClarification,
    SettledOutcome,
    TurnPlan,
)
from coke.turn.inbound.pending import PendingClarificationPort


class TurnClosePort(Protocol):
    def commit_reply(
        self,
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "reply_ready",
        materialize_staged_command: Callable[[Any], Any] | None = None,
    ) -> Any: ...

    def commit_no_reply(
        self,
        turn_id: str,
        reason_code: str = "intentional_no_reply",
        materialize_staged_command: Callable[[Any], Any] | None = None,
    ) -> Any: ...

    def commit_recovery_reply(
        self,
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "grounded_failure_recovery",
    ) -> Any: ...


class CloseFreshnessGuard(Protocol):
    def guard_state_change(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CloseRequest:
    turn_id: str
    conversation_id: str
    plan: TurnPlan
    settled_outcome: SettledOutcome
    segments: tuple[str, ...]
    selected_staged_command_ids: tuple[str, ...] = ()
    source_input_window: tuple[int, int] | None = None
    pending_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(
            self,
            "selected_staged_command_ids",
            tuple(self.selected_staged_command_ids),
        )


@dataclass(frozen=True, slots=True)
class CloseResult:
    committed: bool
    disposition: Any | None
    settled_outcome: SettledOutcome
    selected_staged_command_ids: tuple[str, ...]
    reason_code: str | None = None
    error: Exception | None = None


class CloseCoordinator:
    def __init__(
        self,
        close_port: TurnClosePort,
        *,
        pending_store: PendingClarificationPort | None = None,
        materialize_staged_command: Callable[[Any], Any] | None = None,
    ) -> None:
        self._close_port = close_port
        self._pending_store = pending_store
        self._materialize_staged_command = materialize_staged_command

    def commit(
        self,
        request: CloseRequest,
        guard: CloseFreshnessGuard,
    ) -> CloseResult:
        try:
            guard.guard_state_change()
            disposition = self._commit_fresh(request)
        except Exception as exc:
            return CloseResult(
                committed=False,
                disposition=None,
                settled_outcome=_settled_outcome_with_materialization_failure(
                    request.settled_outcome,
                    request.selected_staged_command_ids,
                    _reason_code(exc),
                ),
                selected_staged_command_ids=request.selected_staged_command_ids,
                reason_code=_reason_code(exc),
                error=exc,
            )
        self._save_pending_clarifications(request)
        return CloseResult(
            committed=True,
            disposition=disposition,
            settled_outcome=request.settled_outcome,
            selected_staged_command_ids=request.selected_staged_command_ids,
            reason_code=getattr(disposition, "reason_code", None),
        )

    def commit_recovery(
        self,
        request: CloseRequest,
        guard: CloseFreshnessGuard,
    ) -> CloseResult:
        try:
            guard.guard_state_change()
            disposition = self._close_port.commit_recovery_reply(
                request.turn_id,
                request.segments,
                reason_code="grounded_failure_recovery",
            )
        except Exception as exc:
            return CloseResult(
                committed=False,
                disposition=None,
                settled_outcome=request.settled_outcome,
                selected_staged_command_ids=request.selected_staged_command_ids,
                reason_code=_reason_code(exc),
                error=exc,
            )
        self._save_pending_clarifications(request)
        return CloseResult(
            committed=True,
            disposition=disposition,
            settled_outcome=request.settled_outcome,
            selected_staged_command_ids=request.selected_staged_command_ids,
            reason_code=getattr(disposition, "reason_code", None),
        )

    def _commit_fresh(self, request: CloseRequest) -> Any:
        if request.segments:
            return self._close_port.commit_reply(
                request.turn_id,
                request.segments,
                reason_code="reply_ready",
                materialize_staged_command=self._materialize_staged_command,
            )
        return self._close_port.commit_no_reply(
            request.turn_id,
            reason_code="intentional_no_reply",
            materialize_staged_command=self._materialize_staged_command,
        )

    def _save_pending_clarifications(self, request: CloseRequest) -> None:
        if self._pending_store is None:
            return
        for pending in _pending_clarifications_from_outcome(request):
            self._pending_store.save(request.conversation_id, pending)


def _pending_clarifications_from_outcome(
    request: CloseRequest,
) -> tuple[PendingClarification, ...]:
    if request.source_input_window is None:
        return ()
    expires_at = request.pending_expires_at
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
    pending: list[PendingClarification] = []
    for outcome in request.settled_outcome.outcomes:
        if outcome.category not in {
            "needs_choice",
            "needs_input",
            "needs_confirmation",
        }:
            continue
        fingerprint = outcome.data.get("unresolved_action_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            continue
        pending.append(
            PendingClarification(
                unresolved_action_fingerprint=fingerprint,
                candidates=_structured_candidates(outcome.data.get("candidates", ())),
                source_input_window=request.source_input_window,
                expires_at=expires_at,
                status="open",
            )
        )
    return tuple(pending)


def _structured_candidates(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, str):
        return ()
    try:
        return tuple(item for item in value if isinstance(item, Mapping))
    except TypeError:
        return ()


def _settled_outcome_with_materialization_failure(
    settled_outcome: SettledOutcome,
    selected_staged_command_ids: tuple[str, ...],
    reason_code: str,
) -> SettledOutcome:
    failed_ids = set(selected_staged_command_ids)
    if not failed_ids:
        return settled_outcome
    outcomes: list[ActionOutcome] = []
    for outcome in settled_outcome.outcomes:
        if outcome.staged_command_id not in failed_ids:
            outcomes.append(outcome)
            continue
        data = dict(outcome.data)
        data["materialization_error"] = reason_code
        outcomes.append(
            ActionOutcome(
                category="not_possible",
                status="materialization_failed",
                data=data,
                staged_command_id=outcome.staged_command_id,
            )
        )
    return SettledOutcome(outcomes=tuple(outcomes))


def _reason_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    if error.args:
        return str(error.args[0])
    return error.__class__.__name__
