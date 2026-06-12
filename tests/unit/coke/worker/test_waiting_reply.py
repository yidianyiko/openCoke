from __future__ import annotations

import logging
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


class FailedDelivery:
    def __init__(self, error_code: str = "provider_network_error") -> None:
        self.error_code = error_code
        self.requests = []

    def deliver(self, request):
        self.requests.append(request)
        return type(
            "DeliveryOutcome",
            (),
            {"status": "failed", "error_code": self.error_code},
        )()


class SequenceDelivery:
    def __init__(self, outcomes) -> None:
        self.requests = []
        self._outcomes = list(outcomes)

    def deliver(self, request):
        self.requests.append(request)
        status, error_code = self._outcomes.pop(0)
        return type(
            "DeliveryOutcome",
            (),
            {"status": status, "error_code": error_code},
        )()


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
    assert delivery.requests[0].idempotency_key == f"{turn.id}:waiting:1"
    assert delivery.requests[0].delivery_source == "waiting_timer"
    assert delivery.requests[0].delivery_intent == f"{turn.id}:waiting:1"
    assert delivery.requests[0].retry_attempt == 1
    assert delivery.requests[0].traceparent == TRACEPARENT
    assert delivery.requests[0].context_token_source == "latest_inbound_message"
    assert delivery.requests[0].context_token_age_seconds == 21

    final = service.commit_reply(
        turn.id,
        segments=("final answer",),
    )

    assert final.disposition == "replied"
    assert service.get_disposition(turn.id).disposition == "replied"


def test_waiting_reply_failed_provider_network_error_keeps_turn_active_and_observable(
    caplog,
):
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_1",
        causal_inbound_event_id="provider:message-1",
        text="slow request",
        payload={"context_token": "ctx_1"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    ).turn
    delivery = SequenceDelivery(
        [
            ("failed", "provider_network_error"),
            ("failed", "provider_network_error"),
        ]
    )
    dispatcher = WaitingReplyDispatcher(
        conversation_runtime=service,
        outbound_delivery=delivery,
        delay_seconds=20,
        retry_jitter=lambda _attempt: 0,
        sleep=lambda _seconds: None,
        now=lambda: NOW + timedelta(seconds=21),
    )

    with caplog.at_level(logging.WARNING, logger="coke.worker.waiting_reply"):
        assert dispatcher.dispatch_due() == 0

    assert "waiting_reply_delivery_failed" in caplog.text
    assert [request.idempotency_key for request in delivery.requests] == [
        f"{turn.id}:waiting:1",
        f"{turn.id}:waiting:2",
    ]
    assert [request.retry_attempt for request in delivery.requests] == [1, 2]
    disposition = service.get_disposition(turn.id)
    assert disposition.disposition == "pending_async_reply"
    assert (
        repository.get_conversation(inbound.conversation.id).last_closed_inbound_seq
        == inbound.conversation.last_closed_inbound_seq
    )
    assert (
        service.repository.outbound_messages_for_turn(turn.id)[0].text == WAITING_TEXT
    )
    final = service.commit_reply(
        turn.id,
        segments=("final answer",),
    )

    assert final.disposition == "replied"


def test_waiting_reply_context_token_failure_does_not_retry():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_1",
        causal_inbound_event_id="provider:message-1",
        text="slow request",
        payload={"context_token": "ctx_1"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    ).turn
    delivery = FailedDelivery(error_code="context_token_required")
    dispatcher = WaitingReplyDispatcher(
        conversation_runtime=service,
        outbound_delivery=delivery,
        delay_seconds=20,
        retry_jitter=lambda _attempt: 0,
        sleep=lambda _seconds: None,
        now=lambda: NOW + timedelta(seconds=21),
    )

    assert dispatcher.dispatch_due() == 0

    assert [request.idempotency_key for request in delivery.requests] == [
        f"{turn.id}:waiting:1",
    ]


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
