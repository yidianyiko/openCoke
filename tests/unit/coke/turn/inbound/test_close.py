from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Sequence

from coke.turn.inbound.close import CloseCoordinator, CloseRequest
from coke.turn.inbound.contracts import ActionOutcome, SettledOutcome, TurnPlan
from coke.turn.inbound.pending import InMemoryPendingClarificationStore


@dataclass(frozen=True, slots=True)
class FakeDisposition:
    disposition: str
    reason_code: str


class RecordingGuard:
    def __init__(self, events: list[str], *, fail: Exception | None = None) -> None:
        self.events = events
        self.fail = fail

    def guard_state_change(self) -> None:
        self.events.append("guard:turn-1")
        if self.fail is not None:
            raise self.fail


class RecordingClosePort:
    def __init__(
        self,
        events: list[str],
        *,
        existing_disposition: str | None = None,
    ) -> None:
        self.events = events
        self.existing_disposition = existing_disposition
        self.calls: list[tuple[str, str, tuple[str, ...], str]] = []

    def commit_reply(
        self,
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "reply_ready",
    ) -> FakeDisposition:
        self.events.append(f"commit_reply:{turn_id}")
        self.calls.append(("reply", turn_id, tuple(segments), reason_code))
        return FakeDisposition(disposition="replied", reason_code=reason_code)

    def commit_no_reply(
        self,
        turn_id: str,
        reason_code: str = "intentional_no_reply",
    ) -> FakeDisposition:
        self.events.append(f"commit_no_reply:{turn_id}")
        self.calls.append(("no_reply", turn_id, (), reason_code))
        return FakeDisposition(disposition="no_reply", reason_code=reason_code)

    def commit_recovery_reply(
        self,
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "grounded_failure_recovery",
    ) -> FakeDisposition:
        self.events.append(f"commit_recovery_reply:{turn_id}")
        self.calls.append(("recovery", turn_id, tuple(segments), reason_code))
        return FakeDisposition(disposition="recovered", reason_code=reason_code)


def test_close_coordinator_rechecks_freshness_then_delegates_to_close_port() -> None:
    events: list[str] = []
    port = RecordingClosePort(events)
    coordinator = CloseCoordinator(port)

    result = coordinator.commit(
        _close_request(
            segments=("Created it.",),
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="created",
                    ),
                )
            ),
        ),
        RecordingGuard(events),
    )

    assert result.committed is True
    assert result.disposition == FakeDisposition(
        disposition="replied",
        reason_code="reply_ready",
    )
    assert events == ["guard:turn-1", "commit_reply:turn-1"]
    assert not hasattr(result, "selected_staged_command_ids")
    assert port.calls == [("reply", "turn-1", ("Created it.",), "reply_ready")]


def test_close_coordinator_uses_no_reply_close_for_empty_segments() -> None:
    events: list[str] = []
    port = RecordingClosePort(events)
    coordinator = CloseCoordinator(port)

    result = coordinator.commit(
        _close_request(segments=(), reply_necessity="intentional_no_reply"),
        RecordingGuard(events),
    )

    assert result.committed is True
    assert result.disposition == FakeDisposition(
        disposition="no_reply",
        reason_code="intentional_no_reply",
    )
    assert port.calls == [("no_reply", "turn-1", (), "intentional_no_reply")]


def test_supersede_before_commit_does_not_commit() -> None:
    events: list[str] = []
    port = RecordingClosePort(events)
    coordinator = CloseCoordinator(port)

    result = coordinator.commit(
        _close_request(
            segments=("Created it.",),
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="created",
                    ),
                )
            ),
        ),
        RecordingGuard(events, fail=RuntimeError("turn_superseded")),
    )

    assert result.committed is False
    assert result.reason_code == "turn_superseded"
    assert port.calls == []


def test_unresolved_outcome_saves_pending_after_successful_close() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    pending_store = InMemoryPendingClarificationStore()
    events: list[str] = []
    coordinator = CloseCoordinator(
        RecordingClosePort(events),
        pending_store=pending_store,
    )

    result = coordinator.commit(
        _close_request(
            segments=("Which gym reminder?",),
            source_input_window=(4, 4),
            pending_expires_at=now + timedelta(minutes=10),
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="needs_choice",
                        status="ambiguous",
                        data={
                            "unresolved_action_fingerprint": "delete:gym",
                            "candidates": (
                                {"id": "r1", "title": "morning gym"},
                                {"id": "r2", "title": "evening gym"},
                            ),
                        },
                    ),
                )
            ),
        ),
        RecordingGuard(events),
    )

    assert result.committed is True
    pending = pending_store.open_for_conversation("conversation-1", now=now)
    assert pending is not None
    assert pending.unresolved_action_fingerprint == "delete:gym"
    assert pending.candidates[0]["title"] == "morning gym"
    assert pending.source_input_window == (4, 4)


def test_close_failure_preserves_real_settled_outcome() -> None:
    events: list[str] = []
    port = RecordingClosePort(events)

    def fail_commit(
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "reply_ready",
    ) -> FakeDisposition:
        raise RuntimeError("close_failed")

    port.commit_reply = fail_commit  # type: ignore[method-assign]
    coordinator = CloseCoordinator(port)
    settled_outcome = SettledOutcome(
        outcomes=(
            ActionOutcome(
                category="done",
                status="created",
                data={"content": "water"},
            ),
        )
    )

    result = coordinator.commit(
        _close_request(
            segments=("Created it.",),
            settled_outcome=settled_outcome,
        ),
        RecordingGuard(events),
    )

    assert result.committed is False
    assert result.reason_code == "close_failed"
    assert result.settled_outcome == settled_outcome


def test_pending_async_disposition_is_only_closed_by_final_commit() -> None:
    events: list[str] = []
    port = RecordingClosePort(events, existing_disposition="pending_async_reply")
    coordinator = CloseCoordinator(port)

    result = coordinator.commit(
        _close_request(segments=("Final answer.",)),
        RecordingGuard(events),
    )

    assert port.existing_disposition == "pending_async_reply"
    assert result.committed is True
    assert result.disposition == FakeDisposition(
        disposition="replied",
        reason_code="reply_ready",
    )
    assert port.calls == [("reply", "turn-1", ("Final answer.",), "reply_ready")]


def _close_request(
    *,
    segments: tuple[str, ...],
    settled_outcome: SettledOutcome = SettledOutcome(outcomes=()),
    reply_necessity: str = "reply_needed",
    source_input_window: tuple[int, int] = (1, 1),
    pending_expires_at: datetime | None = None,
) -> CloseRequest:
    if pending_expires_at is None:
        pending_expires_at = datetime(2026, 6, 10, 12, 10, tzinfo=UTC)
    return CloseRequest(
        turn_id="turn-1",
        conversation_id="conversation-1",
        plan=TurnPlan(actions=(), reply_necessity=reply_necessity),  # type: ignore[arg-type]
        settled_outcome=settled_outcome,
        segments=segments,
        source_input_window=source_input_window,
        pending_expires_at=pending_expires_at,
    )
