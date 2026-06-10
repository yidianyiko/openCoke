from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Sequence

import pytest

from coke.turn.v2.close import CloseCoordinator
from coke.turn.v2.contracts import (
    ActionOutcome,
    CompiledAction,
    PendingClarification,
    ProposedAction,
    SettledOutcome,
    TurnPlan,
)
from coke.turn.v2.pending import InMemoryPendingClarificationStore
from coke.turn.v2.pipeline import (
    SegmentDeliveryPort,
    TurnPipeline,
    TurnPipelineRequest,
    _plan_request,
)
from coke.turn.v2.plan import PlanRequest, SiliconFlowPlanner


@dataclass(frozen=True, slots=True)
class FakeDisposition:
    disposition: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class FakeStagedCommand:
    id: str


class StaticPlanner:
    def __init__(self, plan: TurnPlan, events: list[str]) -> None:
        self.plan_to_return = plan
        self.events = events
        self.requests: list[PlanRequest] = []

    def plan(self, request: PlanRequest) -> TurnPlan:
        self.events.append("plan")
        self.requests.append(request)
        return self.plan_to_return


class RecordingJSONClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema_name": schema_name,
            }
        )
        return {"actions": [], "reply_necessity": "reply_needed"}


class StaticHandler:
    def __init__(self, outcome: ActionOutcome, events: list[str]) -> None:
        self.outcome = outcome
        self.events = events
        self.calls: list[CompiledAction] = []

    def resolve_and_stage(
        self,
        compiled_action: CompiledAction,
        guard: Any,
    ) -> ActionOutcome:
        self.events.append(f"execute:{compiled_action.action.operation}")  # type: ignore[union-attr]
        self.calls.append(compiled_action)
        return self.outcome


class RecordingExpress:
    def __init__(self, segments: tuple[str, ...], events: list[str]) -> None:
        self.segments = segments
        self.events = events
        self.render_calls: list[Any] = []
        self.stream_calls: list[Any] = []

    def render(self, request: Any) -> tuple[str, ...]:
        self.events.append("express_render")
        self.render_calls.append(request)
        return self.segments

    async def render_streaming(self, request: Any):
        self.events.append("express_stream")
        self.stream_calls.append(request)
        for segment in self.segments:
            self.events.append(f"stream_segment:{segment}")
            yield segment


class RecordingDelivery(SegmentDeliveryPort):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.segments: list[str] = []

    def deliver(self, turn_id: str, segment: str) -> None:
        self.events.append(f"deliver:{segment}")
        self.segments.append(segment)


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
        self.events.append("commit_reply")
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
        self.events.append("commit_no_reply")
        self.calls.append(("no_reply", turn_id, (), reason_code))
        for command in self.staged_commands:
            if materialize_staged_command is not None:
                materialize_staged_command(command)
        return FakeDisposition(disposition="no_reply", reason_code=reason_code)


def test_plan_request_and_planner_payload_preserve_conversation_history() -> None:
    history = (
        {
            "role": "user",
            "content": "和朋友约明晚八点吃饭",
            "seq": 1,
        },
        {"role": "assistant", "content": "她那边有冲突，要不换个时间？"},
    )
    request = _pipeline_request(conversation_history=history)

    plan_request = _plan_request(request, None)

    assert plan_request.conversation_history == history

    client = RecordingJSONClient()
    SiliconFlowPlanner(client).plan(plan_request)

    assert client.calls[0]["schema_name"] == "turn_plan"
    assert client.calls[0]["user"]["conversation_history"] == [
        {
            "role": "user",
            "content": "和朋友约明晚八点吃饭",
            "seq": 1,
        },
        {"role": "assistant", "content": "她那边有冲突，要不换个时间？"},
    ]


@pytest.mark.asyncio
async def test_read_only_turn_streams_segments_and_then_closes() -> None:
    events: list[str] = []
    planner = StaticPlanner(
        TurnPlan(
            actions=(ProposedAction(domain="reminder", operation="list"),),
        ),
        events,
    )
    close_port = RecordingClosePort(events)
    delivery = RecordingDelivery(events)
    pipeline = TurnPipeline(
        planner=planner,
        handlers={
            "reminder": StaticHandler(
                ActionOutcome(category="done", status="listed", data={"count": 1}),
                events,
            )
        },
        express=RecordingExpress(("Here is your reminder.",), events),
        close_coordinator=CloseCoordinator(close_port),
        pending_store=InMemoryPendingClarificationStore(),
        delivery=delivery,
    )

    result = await pipeline.run(_pipeline_request(), RecordingGuard(events))

    assert result.streamed is True
    assert result.segments == ("Here is your reminder.",)
    assert delivery.segments == ["Here is your reminder."]
    assert close_port.calls == [
        ("reply", "turn-1", ("Here is your reminder.",), "reply_ready")
    ]
    assert events == [
        "plan",
        "execute:list",
        "express_stream",
        "stream_segment:Here is your reminder.",
        "deliver:Here is your reminder.",
        "guard:turn-1",
        "commit_reply",
    ]


@pytest.mark.asyncio
async def test_mutating_turn_buffers_until_after_close_commit() -> None:
    events: list[str] = []
    materialized: list[str] = []
    close_port = RecordingClosePort(
        events,
        staged_commands=(FakeStagedCommand(id="stage-1"),),
    )
    delivery = RecordingDelivery(events)
    pipeline = TurnPipeline(
        planner=StaticPlanner(
            TurnPlan(
                actions=(
                    ProposedAction(
                        domain="reminder",
                        operation="create",
                        params={
                            "content": "drink water",
                            "time_phrase": "tomorrow morning",
                        },
                    ),
                ),
            ),
            events,
        ),
        handlers={
            "reminder": StaticHandler(
                ActionOutcome(
                    category="done",
                    status="created",
                    staged_command_id="stage-1",
                ),
                events,
            )
        },
        express=RecordingExpress(("Created it.",), events),
        close_coordinator=CloseCoordinator(
            close_port,
            materialize_staged_command=lambda command: materialized.append(command.id),
        ),
        pending_store=InMemoryPendingClarificationStore(),
        delivery=delivery,
    )

    result = await pipeline.run(_pipeline_request(), RecordingGuard(events))

    assert result.streamed is False
    assert result.segments == ("Created it.",)
    assert materialized == ["stage-1"]
    assert delivery.segments == ["Created it."]
    assert events.index("deliver:Created it.") > events.index("commit_reply")
    assert "express_stream" not in events


@pytest.mark.asyncio
async def test_supersede_before_mutating_commit_delivers_and_materializes_nothing() -> (
    None
):
    events: list[str] = []
    materialized: list[str] = []
    close_port = RecordingClosePort(
        events,
        staged_commands=(FakeStagedCommand(id="stage-1"),),
    )
    delivery = RecordingDelivery(events)
    pipeline = TurnPipeline(
        planner=StaticPlanner(
            TurnPlan(
                actions=(
                    ProposedAction(
                        domain="reminder",
                        operation="create",
                        params={
                            "content": "drink water",
                            "time_phrase": "tomorrow morning",
                        },
                    ),
                ),
            ),
            events,
        ),
        handlers={
            "reminder": StaticHandler(
                ActionOutcome(
                    category="done",
                    status="created",
                    staged_command_id="stage-1",
                ),
                events,
            )
        },
        express=RecordingExpress(("Created it.",), events),
        close_coordinator=CloseCoordinator(
            close_port,
            materialize_staged_command=lambda command: materialized.append(command.id),
        ),
        pending_store=InMemoryPendingClarificationStore(),
        delivery=delivery,
    )

    result = await pipeline.run(
        _pipeline_request(),
        RecordingGuard(events, fail=RuntimeError("turn_superseded")),
    )

    assert result.close_result.committed is False
    assert result.close_result.reason_code == "turn_superseded"
    assert delivery.segments == []
    assert materialized == []
    assert close_port.calls == []


@pytest.mark.asyncio
async def test_unresolved_action_writes_pending_clarification_with_candidates() -> None:
    events: list[str] = []
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    pending_store = InMemoryPendingClarificationStore()
    pipeline = TurnPipeline(
        planner=StaticPlanner(
            TurnPlan(
                actions=(
                    ProposedAction(
                        domain="reminder",
                        operation="delete",
                        params={"match": "gym"},
                    ),
                ),
            ),
            events,
        ),
        handlers={
            "reminder": StaticHandler(
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
                events,
            )
        },
        express=RecordingExpress(("Which gym reminder?",), events),
        close_coordinator=CloseCoordinator(
            RecordingClosePort(events),
            pending_store=pending_store,
        ),
        pending_store=pending_store,
        delivery=RecordingDelivery(events),
    )

    await pipeline.run(
        _pipeline_request(
            source_input_window=(7, 7),
            pending_expires_at=now + timedelta(minutes=10),
        ),
        RecordingGuard(events),
    )

    pending = pending_store.open_for_conversation("conversation-1", now=now)
    assert pending is not None
    assert pending.unresolved_action_fingerprint == "delete:gym"
    assert [candidate["title"] for candidate in pending.candidates] == [
        "morning gym",
        "evening gym",
    ]
    assert pending.source_input_window == (7, 7)


@pytest.mark.asyncio
async def test_next_turn_resolution_consumes_pending_by_fingerprint() -> None:
    events: list[str] = []
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    pending_store = InMemoryPendingClarificationStore()
    pending_store.save(
        "conversation-1",
        PendingClarification(
            unresolved_action_fingerprint="delete:gym",
            candidates=({"id": "r2", "title": "evening gym"},),
            source_input_window=(7, 7),
            expires_at=now + timedelta(minutes=10),
            status="open",
        ),
    )
    planner = StaticPlanner(
        TurnPlan(
            actions=(
                ProposedAction(
                    domain="reminder",
                    operation="delete",
                    params={
                        "match": "evening gym",
                        "resolves_pending_fingerprint": "delete:gym",
                    },
                ),
            ),
        ),
        events,
    )
    close_port = RecordingClosePort(
        events,
        staged_commands=(FakeStagedCommand(id="stage-1"),),
    )
    pipeline = TurnPipeline(
        planner=planner,
        handlers={
            "reminder": StaticHandler(
                ActionOutcome(
                    category="done",
                    status="cancelled",
                    staged_command_id="stage-1",
                ),
                events,
            )
        },
        express=RecordingExpress(("Cancelled the evening gym reminder.",), events),
        close_coordinator=CloseCoordinator(close_port),
        pending_store=pending_store,
        delivery=RecordingDelivery(events),
    )

    result = await pipeline.run(_pipeline_request(now=now), RecordingGuard(events))

    assert result.close_result.committed is True
    assert planner.requests[0].trusted_facts["pending_clarification"] == {
        "unresolved_action_fingerprint": "delete:gym",
        "candidates": [{"id": "r2", "title": "evening gym"}],
        "source_input_window": [7, 7],
        "expires_at": "2026-06-10T12:10:00+00:00",
        "status": "open",
    }
    assert pending_store.open_for_conversation("conversation-1", now=now) is None
    assert pending_store.consumed[0][1].unresolved_action_fingerprint == "delete:gym"


@pytest.mark.asyncio
async def test_intentional_no_reply_uses_close_without_streaming_or_segments() -> None:
    events: list[str] = []
    close_port = RecordingClosePort(events, existing_disposition="pending_async_reply")
    express = RecordingExpress(("should not render",), events)
    delivery = RecordingDelivery(events)
    pipeline = TurnPipeline(
        planner=StaticPlanner(
            TurnPlan(actions=(), reply_necessity="intentional_no_reply"),
            events,
        ),
        handlers={},
        express=express,
        close_coordinator=CloseCoordinator(close_port),
        pending_store=InMemoryPendingClarificationStore(),
        delivery=delivery,
    )

    result = await pipeline.run(_pipeline_request(), RecordingGuard(events))

    assert close_port.existing_disposition == "pending_async_reply"
    assert result.close_result.committed is True
    assert result.segments == ()
    assert delivery.segments == []
    assert express.render_calls == []
    assert express.stream_calls == []
    assert close_port.calls == [("no_reply", "turn-1", (), "intentional_no_reply")]


def _pipeline_request(
    *,
    now: datetime | None = None,
    source_input_window: tuple[int, int] = (1, 1),
    pending_expires_at: datetime | None = None,
    conversation_history: Sequence[Mapping[str, Any]] = (
        {"role": "user", "content": "hello"},
    ),
) -> TurnPipelineRequest:
    if now is None:
        now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    if pending_expires_at is None:
        pending_expires_at = now + timedelta(minutes=10)
    return TurnPipelineRequest(
        turn_id="turn-1",
        account_id="account-1",
        conversation_id="conversation-1",
        payload={"text": "hello"},
        trusted_facts={"timezone": "Asia/Tokyo"},
        conversation_history=conversation_history,
        persona="concise",
        source_input_window=source_input_window,
        pending_expires_at=pending_expires_at,
        now=now,
    )
