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
    def deliver(self, request):
        return type(
            "DeliveryOutcome",
            (),
            {"status": "failed", "error_code": "provider_network_error"},
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
    assert delivery.requests[0].idempotency_key == f"{turn.id}:waiting"

    staged = service.stage_command(
        turn_id=turn.id,
        domain="social_scheduling",
        operation="create_shared_reminder",
        command_payload={
            "title": "music lesson",
            "local_trigger_at": "2026-06-01T22:30:00+08:00",
        },
        preview_facts={"status": "staged"},
        item_index=0,
    )
    materialized = []
    final = service.commit_reply(
        turn.id,
        segments=("final answer",),
        materialize_staged_command=materialized.append,
    )

    assert final.disposition == "replied"
    assert service.get_disposition(turn.id).disposition == "replied"
    assert materialized == [staged]


def test_waiting_reply_logs_failed_delivery_without_retrying_blindly(caplog):
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
    dispatcher = WaitingReplyDispatcher(
        conversation_runtime=service,
        outbound_delivery=FailedDelivery(),
        delay_seconds=20,
        now=lambda: NOW + timedelta(seconds=21),
    )

    with caplog.at_level(logging.WARNING, logger="coke.worker.waiting_reply"):
        assert dispatcher.dispatch_due() == 1

    assert "waiting_reply_delivery_failed" in caplog.text
    assert (
        service.repository.outbound_messages_for_turn(turn.id)[0].text == WAITING_TEXT
    )


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
