from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.turn.runner import WAITING_TEXT
from coke.worker.waiting_reply import WaitingReplyDispatcher

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def id_factory():
    counter = count(1)
    return lambda prefix: f"{prefix}_{next(counter)}"


class RecordingDelivery:
    def __init__(self) -> None:
        self.requests = []

    def deliver(self, request):
        self.requests.append(request)
        return type("DeliveryOutcome", (), {"status": "sent", "error_code": None})()


def test_waiting_reply_dispatches_after_budget_and_final_reply_can_still_close():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    delivery = RecordingDelivery()
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_1",
        causal_inbound_event_id="provider:message-1",
        text="how many reminders?",
        payload={"context_token": "ctx_1"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    ).turn
    dispatcher = WaitingReplyDispatcher(
        conversation_runtime=service,
        outbound_delivery=delivery,
        delay_seconds=20,
        now=lambda: NOW + timedelta(seconds=21),
    )

    assert dispatcher.dispatch_due() == 1

    disposition = service.get_disposition(turn.id)
    assert disposition.disposition == "pending_async_reply"
    assert disposition.reason_code == "waiting_timer_elapsed"
    assert delivery.requests[0].visible_text == WAITING_TEXT
    assert delivery.requests[0].context_token == "ctx_1"
    assert delivery.requests[0].idempotency_key == f"{turn.id}:waiting"

    final = service.commit_reply(
        turn.id,
        segments=("final answer",),
    )

    assert final.disposition == "replied"
    assert service.get_disposition(turn.id).disposition == "replied"


def test_waiting_reply_does_not_dispatch_before_budget():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    delivery = RecordingDelivery()
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_1",
        causal_inbound_event_id="provider:message-1",
        text="how many reminders?",
        payload={},
        traceparent=TRACEPARENT,
    )
    service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )
    dispatcher = WaitingReplyDispatcher(
        conversation_runtime=service,
        outbound_delivery=delivery,
        delay_seconds=20,
        now=lambda: NOW + timedelta(seconds=19),
    )

    assert dispatcher.dispatch_due() == 0
    assert delivery.requests == []
