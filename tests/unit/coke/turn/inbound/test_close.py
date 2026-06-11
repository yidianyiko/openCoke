from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Sequence

from coke.turn.inbound.close import CloseCoordinator, CloseRequest
from coke.turn.inbound.contracts import ActionOutcome, SettledOutcome, TurnPlan
from coke.turn.inbound.pending import InMemoryPendingClarificationStore


@dataclass(frozen=True, slots=True)
class FakeDisposition:
    disposition: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class FakeStagedCommand:
    id: str


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
        staged_commands: Sequence[FakeStagedCommand] = (),
        existing_disposition: str | None = None,
    ) -> None:
        self.events = events
        self.staged_commands = tuple(staged_commands)
        self.existing_disposition = existing_disposition
        self.calls: list[tuple[str, str, tuple[str, ...], str]] = []

    def commit_reply(
        self,
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "reply_ready",
        materialize_staged_command: Callable[[Any], Any] | None = None,
    ) -> FakeDisposition:
        self.events.append(f"commit_reply:{turn_id}")
        self.calls.append(("reply", turn_id, tuple(segments), reason_code))
        for command in self.staged_commands:
            if materialize_staged_command is not None:
                materialize_staged_command(command)
        return FakeDisposition(disposition="replied", reason_code=reason_code)

    def commit_no_reply(
        self,
        turn_id: str,
        reason_code: str = "intentional_no_reply",
        materialize_staged_command: Callable[[Any], Any] | None = None,
    ) -> FakeDisposition:
        self.events.append(f"commit_no_reply:{turn_id}")
        self.calls.append(("no_reply", turn_id, (), reason_code))
        for command in self.staged_commands:
            if materialize_staged_command is not None:
                materialize_staged_command(command)
        return FakeDisposition(disposition="no_reply", reason_code=reason_code)


def test_close_coordinator_rechecks_freshness_then_delegates_to_close_port() -> None:
    events: list[str] = []
    materialized: list[str] = []
    port = RecordingClosePort(
        events,
        staged_commands=(FakeStagedCommand(id="stage-1"),),
    )
    coordinator = CloseCoordinator(
        port,
        materialize_staged_command=lambda command: materialized.append(command.id),
    )

    result = coordinator.commit(
        _close_request(
            segments=("Created it.",),
            selected_staged_command_ids=("stage-1",),
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="created",
                        staged_command_id="stage-1",
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
    assert materialized == ["stage-1"]
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


def test_supersede_before_commit_does_not_commit_or_materialize() -> None:
    events: list[str] = []
    materialized: list[str] = []
    port = RecordingClosePort(
        events,
        staged_commands=(FakeStagedCommand(id="stage-1"),),
    )
    coordinator = CloseCoordinator(
        port,
        materialize_staged_command=lambda command: materialized.append(command.id),
    )

    result = coordinator.commit(
        _close_request(
            segments=("Created it.",),
            selected_staged_command_ids=("stage-1",),
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="created",
                        staged_command_id="stage-1",
                    ),
                )
            ),
        ),
        RecordingGuard(events, fail=RuntimeError("turn_superseded")),
    )

    assert result.committed is False
    assert result.reason_code == "turn_superseded"
    assert port.calls == []
    assert materialized == []


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


def test_materialization_failure_is_not_reported_as_success() -> None:
    events: list[str] = []
    port = RecordingClosePort(
        events,
        staged_commands=(FakeStagedCommand(id="stage-1"),),
    )

    def fail_materialization(command: FakeStagedCommand) -> None:
        raise RuntimeError(f"materialize_failed:{command.id}")

    coordinator = CloseCoordinator(
        port,
        materialize_staged_command=fail_materialization,
    )

    result = coordinator.commit(
        _close_request(
            segments=("Created it.",),
            selected_staged_command_ids=("stage-1",),
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="created",
                        data={"content": "water"},
                        staged_command_id="stage-1",
                    ),
                )
            ),
        ),
        RecordingGuard(events),
    )

    assert result.committed is False
    assert result.reason_code == "materialize_failed:stage-1"
    assert result.settled_outcome.outcomes == (
        ActionOutcome(
            category="not_possible",
            status="materialization_failed",
            data={
                "content": "water",
                "materialization_error": "materialize_failed:stage-1",
            },
            staged_command_id="stage-1",
        ),
    )


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
    selected_staged_command_ids: tuple[str, ...] = (),
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
        selected_staged_command_ids=selected_staged_command_ids,
        source_input_window=source_input_window,
        pending_expires_at=pending_expires_at,
    )
