from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from coke.domains.social_scheduling.models import (
    NotificationFact,
    NotificationRecipient,
)
from coke.domains.social_scheduling.repository import InMemorySocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.worker.__main__ import _handle_event, _turn_trigger_from_event
from coke.worker.stream_consumer import StreamEvent

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


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


class FakeConversationRuntimeRepository:
    def __init__(self, missing_accounts: set[str] | None = None) -> None:
        self._missing_accounts = missing_accounts or set()

    def get_conversation_by_account(self, account_id: str):
        if account_id in self._missing_accounts:
            return None
        return type("Conversation", (), {"id": f"conversation:{account_id}"})()


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class RecordingTurnRunner:
    def __init__(self) -> None:
        self.triggers = []

    def run_render_turn(self, trigger):
        self.triggers.append(trigger)
        return type(
            "TurnResult",
            (),
            {
                "turn_id": f"turn:{trigger.account_id}",
                "disposition": "replied",
                "reason_code": "reply_ready",
                "visible_text": "rendered",
            },
        )()


class WorkerRuntime:
    def __init__(
        self,
        social_scheduling,
        *,
        conversation_runtime=None,
        social_scheduling_service=None,
    ) -> None:
        self.repositories = type(
            "Repositories",
            (),
            {
                "social_scheduling": social_scheduling,
                "conversation_runtime": (
                    conversation_runtime or FakeConversationRuntimeRepository()
                ),
            },
        )()
        self.social_scheduling_service = social_scheduling_service
        self.turn_runner = RecordingTurnRunner()
        self.session = FakeSession()
        self.reply_pubsub = None


class RecordingSupervisor:
    def __init__(self) -> None:
        self.submitted = []

    async def submit(self, trigger):
        self.submitted.append(trigger)

    async def drain_completed(self):
        return []


class FakeReachability:
    def has_usable_channel(self, account_id: str) -> bool:
        return True


class FakeReminderAvailability:
    def personal_busy_intervals(self, account_id, start, end, requester_timezone):
        return []


def id_factory(prefix: str) -> str:
    id_factory.count += 1
    return f"{prefix}_{id_factory.count}"


id_factory.count = 0


def make_social_service_for_notification(recipients: list[str]):
    id_factory.count = 0
    repo = InMemorySocialSchedulingRepository()
    service = SocialSchedulingService(
        repository=repo,
        reachability=FakeReachability(),
        reminder_availability=FakeReminderAvailability(),
        now=lambda: NOW,
        id_factory=id_factory,
        token_factory=lambda prefix: f"{prefix}_token",
    )
    repo.add_notification_fact(
        NotificationFact(
            id="notification_fact_1",
            type="shared_reminder_created",
            actor_account_id="creator_1",
            object_type="shared_reminder",
            object_id="shared_1",
            status="created",
            facts={"title": "Lunch", "delivery_recipients": list(recipients)},
            facts_hash="hash_1",
            idempotency_key="shared_1:created",
            outbox_id="outbox_1",
            created_at=NOW,
        )
    )
    for recipient in recipients:
        repo.add_notification_recipient(
            NotificationRecipient(
                id=f"notification_recipient:{recipient}",
                notification_fact_id="notification_fact_1",
                recipient_account_id=recipient,
                delivery_state="pending",
                error_facts={},
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return service, repo


def notification_event(account_id: str) -> StreamEvent:
    return StreamEvent(
        event_id="event_1",
        topic="turn.notification",
        idempotency_key="notification:1",
        traceparent="traceparent",
        payload={
            "trigger_id": "notification:notification_fact_1",
            "notification_fact_id": "notification_fact_1",
            "account_id": account_id,
            "recipient_account_ids": [account_id],
            "object_type": "shared_reminder",
            "object_id": "shared_1",
            "facts_hash": "hash_1",
        },
        stream_message_id="1-0",
    )


def test_notification_without_recipient_conversation_settles_failed_and_drains():
    service, repo = make_social_service_for_notification(["receiver_1"])
    runtime = WorkerRuntime(
        repo,
        conversation_runtime=FakeConversationRuntimeRepository(
            missing_accounts={"receiver_1"}
        ),
        social_scheduling_service=service,
    )

    _handle_event(
        runtime, notification_event("receiver_1"), supervisor=RecordingSupervisor()
    )

    recipient = repo.get_notification_recipient("notification_fact_1", "receiver_1")
    assert runtime.turn_runner.triggers == []
    assert runtime.session.commits == 1
    assert recipient.delivery_state == "failed"
    assert recipient.turn_id is None
    assert recipient.error_facts == {
        "type": "channel_optional_join_no_conversation",
        "reason_code": "conversation_not_found",
    }


def test_notification_with_recipient_conversation_still_produces_render_trigger():
    service, repo = make_social_service_for_notification(["receiver_1"])
    runtime = WorkerRuntime(repo, social_scheduling_service=service)

    trigger = _turn_trigger_from_event(runtime, notification_event("receiver_1"))

    recipient = repo.get_notification_recipient("notification_fact_1", "receiver_1")
    assert trigger.trigger_type == "NotificationTurn"
    assert trigger.account_id == "receiver_1"
    assert trigger.conversation_id == "conversation:receiver_1"
    assert trigger.payload["recipient_account_ids"] == ["receiver_1"]
    assert recipient.delivery_state == "pending"
    assert recipient.error_facts == {}


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


def test_notification_event_fans_out_to_recipient_scoped_render_turns():
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
    runtime = WorkerRuntime(FakeSocialSchedulingRepository([fact]))
    supervisor = RecordingSupervisor()

    _handle_event(
        runtime,
        StreamEvent(
            event_id="event_1",
            topic="turn.notification",
            idempotency_key="notification:1",
            traceparent="traceparent",
            payload={
                "trigger_id": "notification:notification_fact_1",
                "notification_fact_id": "notification_fact_1",
                "account_id": "creator_1",
                "recipient_account_ids": ["creator_1", "receiver_1"],
                "object_type": "shared_reminder",
                "object_id": "shared_1",
                "facts_hash": "hash_1",
            },
            stream_message_id="1-0",
        ),
        supervisor=supervisor,
    )

    triggers = runtime.turn_runner.triggers
    assert supervisor.submitted == []
    assert [trigger.account_id for trigger in triggers] == [
        "creator_1",
        "receiver_1",
    ]
    assert [trigger.conversation_id for trigger in triggers] == [
        "conversation:creator_1",
        "conversation:receiver_1",
    ]
    assert [trigger.trigger_id for trigger in triggers] == [
        "notification:notification_fact_1:creator_1",
        "notification:notification_fact_1:receiver_1",
    ]
    assert [trigger.payload["recipient_account_ids"] for trigger in triggers] == [
        ["creator_1"],
        ["receiver_1"],
    ]
    assert all(
        trigger.payload["notification_fact"]["facts"]["title"] == "Lunch"
        for trigger in triggers
    )


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
