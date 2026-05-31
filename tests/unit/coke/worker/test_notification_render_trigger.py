from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coke.worker.__main__ import _turn_trigger_from_event
from coke.worker.stream_consumer import StreamEvent


@dataclass(frozen=True, slots=True)
class FakeNotificationFact:
    id: str
    type: str
    actor_account_id: str
    object_type: str
    object_id: str
    status: str
    facts: dict[str, Any]
    facts_hash: str


class FakeSocialSchedulingRepository:
    def __init__(self, facts: list[FakeNotificationFact]) -> None:
        self._facts = facts

    def list_notification_facts(self):
        return list(self._facts)


class FakeRepositories:
    def __init__(self, social_scheduling) -> None:
        self.social_scheduling = social_scheduling


class FakeRuntime:
    def __init__(self, social_scheduling) -> None:
        self.repositories = FakeRepositories(social_scheduling)


def test_notification_render_trigger_hydrates_structured_facts_from_repository():
    fact = FakeNotificationFact(
        id="notification_fact_1",
        type="shared_reminder_created",
        actor_account_id="creator_1",
        object_type="shared_reminder",
        object_id="shared_1",
        status="created",
        facts={
            "actor_display_name": "Alice",
            "title": "Lunch",
            "time": "2026-06-01T12:00:00",
            "timezone": "Asia/Tokyo",
            "duration_minutes": 45,
            "status": "created",
        },
        facts_hash="hash_1",
    )
    runtime = FakeRuntime(FakeSocialSchedulingRepository([fact]))

    trigger = _turn_trigger_from_event(
        runtime,
        StreamEvent(
            event_id="event_1",
            topic="turn.notification",
            idempotency_key="notification:1",
            traceparent="traceparent",
            payload={
                "trigger_id": "notification:notification_fact_1",
                "notification_fact_id": "notification_fact_1",
                "account_id": "receiver_1",
                "conversation_id": "conversation_1",
                "recipient_account_ids": ["receiver_1"],
                "object_type": "shared_reminder",
                "object_id": "shared_1",
                "facts_hash": "hash_1",
            },
            stream_message_id="1-0",
        ),
    )

    hydrated = trigger.payload["notification_fact"]
    assert hydrated["id"] == "notification_fact_1"
    assert hydrated["type"] == "shared_reminder_created"
    assert hydrated["facts"]["actor_display_name"] == "Alice"
    assert hydrated["facts"]["title"] == "Lunch"
    assert hydrated["facts"]["time"] == "2026-06-01T12:00:00"
    assert hydrated["facts"]["timezone"] == "Asia/Tokyo"
    assert hydrated["facts"]["duration_minutes"] == 45
    assert "text" not in hydrated["facts"]
    assert "payload" not in hydrated["facts"]
    assert "prose" not in hydrated["facts"]


def test_undelivered_resend_event_maps_to_render_turn():
    runtime = FakeRuntime(FakeSocialSchedulingRepository([]))

    trigger = _turn_trigger_from_event(
        runtime,
        StreamEvent(
            event_id="event_2",
            topic="turn.undelivered_resend",
            idempotency_key="undelivered_resend:acct_1:wa_msg_1",
            traceparent="traceparent",
            payload={
                "trigger_id": "undelivered_resend:acct_1:wa_msg_1",
                "account_id": "acct_1",
                "conversation_id": "conversation_1",
                "fire_ids": ["fire_1", "fire_2"],
                "framing": "previously_undelivered",
            },
            stream_message_id="1-1",
        ),
    )

    assert trigger.trigger_type == "UndeliveredResendTurn"
    assert trigger.payload["fire_ids"] == ["fire_1", "fire_2"]


def test_undelivered_resend_event_hydrates_notification_facts():
    fact = FakeNotificationFact(
        id="notification_fact_1",
        type="shared_reminder_cancelled",
        actor_account_id="creator_1",
        object_type="shared_reminder",
        object_id="shared_1",
        status="cancelled",
        facts={
            "actor_display_name": "Alice",
            "title": "Lunch",
            "time": "2026-06-01T12:00:00",
            "timezone": "Asia/Tokyo",
            "duration_minutes": 45,
            "status": "cancelled",
        },
        facts_hash="hash_1",
    )
    runtime = FakeRuntime(FakeSocialSchedulingRepository([fact]))

    trigger = _turn_trigger_from_event(
        runtime,
        StreamEvent(
            event_id="event_3",
            topic="turn.undelivered_resend",
            idempotency_key="undelivered_resend:acct_1:wa_msg_2",
            traceparent="traceparent",
            payload={
                "trigger_id": "undelivered_resend:acct_1:wa_msg_2",
                "account_id": "acct_1",
                "conversation_id": "conversation_1",
                "notification_fact_ids": ["notification_fact_1"],
                "framing": "previously_undelivered",
            },
            stream_message_id="1-2",
        ),
    )

    assert trigger.trigger_type == "UndeliveredResendTurn"
    assert trigger.payload["notification_facts"][0]["id"] == "notification_fact_1"
    assert trigger.payload["notification_facts"][0]["facts"]["title"] == "Lunch"
