from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from coke.composition import OutputLifecycleDeliveryCallbacks
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.social_scheduling.availability import (
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.models import (
    NotificationFact,
    NotificationRecipient,
)
from coke.domains.social_scheduling.repository import InMemorySocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


class FakeReachability(ParticipantReachabilityPort):
    def has_usable_channel(self, account_id: str) -> bool:
        return True


class FakeReminderAvailability(ReminderAvailabilityPort):
    def personal_busy_intervals(self, account_id, start, end, requester_timezone):
        return []


def id_factory(prefix: str) -> str:
    id_factory.count += 1
    return f"{prefix}_{id_factory.count}"


id_factory.count = 0


def make_reminder_service() -> ReminderService:
    id_factory.count = 0
    return ReminderService(
        repository=InMemoryReminderRepository(),
        now=lambda: NOW,
        id_factory=id_factory,
    )


def make_social_service():
    repo = InMemorySocialSchedulingRepository()
    service = SocialSchedulingService(
        repository=repo,
        reachability=FakeReachability(),
        reminder_availability=FakeReminderAvailability(),
        now=lambda: NOW,
        id_factory=id_factory,
        token_factory=lambda prefix: f"{prefix}_token",
    )
    fact = NotificationFact(
        id="notification_fact_1",
        type="friendship_created",
        actor_account_id="acct_2",
        object_type="friendship",
        object_id="friendship_1",
        status="created",
        facts={"type": "friendship_created"},
        facts_hash="facts_hash_1",
        idempotency_key="friendship_1",
        outbox_id="outbox_1",
        created_at=NOW,
    )
    repo.add_notification_fact(fact)
    repo.add_notification_recipient(
        NotificationRecipient(
            id="notification_recipient_1",
            notification_fact_id=fact.id,
            recipient_account_id="acct_1",
            delivery_state="pending",
            error_facts={},
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return service, repo


def test_context_token_window_failure_marks_reminder_fire_undelivered():
    reminder_service = make_reminder_service()
    social_service, _repo = make_social_service()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
    )
    created = reminder_service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="take medicine",
                trigger_time=NOW,
                captured_timezone="UTC",
            )
        ],
    )
    fire = reminder_service.claim_due_fire(created.items[0].reminder_id, NOW)

    callbacks.record_delivery(
        trigger=SimpleNamespace(
            trigger_type="ReminderFireTurn",
            payload={"fire_ids": [fire.id]},
        ),
        request=SimpleNamespace(account_id="acct_1", turn_id="turn_1"),
        outcome=SimpleNamespace(status="failed", error_code="ilink_send_failed_ret_-2"),
    )

    assert (
        reminder_service.repository.get_fire(fire.id).delivery_result == "undelivered"
    )


def test_context_token_window_failure_marks_notification_recipient_undelivered():
    reminder_service = make_reminder_service()
    social_service, repo = make_social_service()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
    )

    callbacks.record_delivery(
        trigger=SimpleNamespace(
            trigger_type="NotificationTurn",
            payload={"notification_fact_id": "notification_fact_1"},
        ),
        request=SimpleNamespace(account_id="acct_1", turn_id="turn_1"),
        outcome=SimpleNamespace(status="failed", error_code="ilink_send_failed_ret_-2"),
    )

    recipient = repo.get_notification_recipient("notification_fact_1", "acct_1")
    assert recipient.delivery_state == "undelivered"
    assert recipient.turn_id == "turn_1"
    assert recipient.error_facts == {"type": "recipient_channel_unavailable"}


def test_undelivered_resend_delivery_updates_notification_recipient():
    reminder_service = make_reminder_service()
    social_service, repo = make_social_service()
    social_service.record_notification_delivery(
        notification_fact_id="notification_fact_1",
        recipient_account_id="acct_1",
        delivery_state="undelivered",
        error_facts={"type": "recipient_channel_unavailable"},
        turn_id="turn_previous",
    )
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
    )

    callbacks.record_delivery(
        trigger=SimpleNamespace(
            trigger_type="UndeliveredResendTurn",
            payload={"notification_fact_ids": ["notification_fact_1"]},
        ),
        request=SimpleNamespace(account_id="acct_1", turn_id="turn_resend"),
        outcome=SimpleNamespace(status="sent", error_code=None),
    )

    recipient = repo.get_notification_recipient("notification_fact_1", "acct_1")
    assert recipient.delivery_state == "delivered"
    assert recipient.turn_id == "turn_resend"
    assert recipient.error_facts == {}


def test_context_token_window_failure_discards_proactive_fire():
    reminder_service = make_reminder_service()
    social_service, _repo = make_social_service()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
    )
    created = reminder_service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="gentle follow-up",
                trigger_time=NOW,
                captured_timezone="UTC",
                kind="proactive",
            )
        ],
    )
    fire = reminder_service.claim_due_fire(created.items[0].reminder_id, NOW)

    callbacks.record_delivery(
        trigger=SimpleNamespace(
            trigger_type="ProactiveFireTurn",
            payload={"fire_id": fire.id},
        ),
        request=SimpleNamespace(account_id="acct_1", turn_id="turn_1"),
        outcome=SimpleNamespace(status="failed", error_code="ilink_send_failed_ret_-2"),
    )

    assert reminder_service.repository.get_fire(fire.id).fire_state == "discarded"
    assert reminder_service.repository.get_fire(fire.id).delivery_result is None
