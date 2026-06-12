from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
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


class FakeConversationRuntimeService:
    def __init__(self) -> None:
        self.enqueued = []

    def enqueue_render_turn(
        self,
        *,
        topic,
        idempotency_key,
        payload,
        traceparent,
    ):
        self.enqueued.append(
            {
                "topic": topic,
                "idempotency_key": idempotency_key,
                "payload": payload,
                "traceparent": traceparent,
            }
        )


class FakeIdentityAccessService:
    def __init__(self) -> None:
        self.guidance_marks: list[str] = []

    def mark_first_guidance_sent(self, account_id: str) -> None:
        self.guidance_marks.append(account_id)


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
                duration_minutes=15,
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


def test_notification_delivery_success_settles_pending_recipient_delivered():
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
        outcome=SimpleNamespace(status="sent", error_code=None),
    )

    recipient = repo.get_notification_recipient("notification_fact_1", "acct_1")
    assert recipient.delivery_state == "delivered"
    assert recipient.turn_id == "turn_1"
    assert recipient.error_facts == {}


def test_notification_render_failure_marks_recipient_failed():
    reminder_service = make_reminder_service()
    social_service, repo = make_social_service()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
    )

    callbacks.record_render_failure(
        trigger=SimpleNamespace(
            trigger_type="NotificationTurn",
            account_id="acct_1",
            payload={
                "notification_fact_id": "notification_fact_1",
                "recipient_account_ids": ["acct_1"],
            },
        ),
        turn_id="turn_1",
        reason_code="notification_requires_visible_reply",
    )

    recipient = repo.get_notification_recipient("notification_fact_1", "acct_1")
    assert recipient.delivery_state == "failed"
    assert recipient.turn_id == "turn_1"
    assert recipient.error_facts == {
        "type": "notification_render_failed",
        "reason_code": "notification_requires_visible_reply",
    }


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


def test_inbound_reply_completion_enqueues_undelivered_reminder_resend():
    reminder_service = make_reminder_service()
    social_service, _repo = make_social_service()
    conversation_runtime = FakeConversationRuntimeService()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
        conversation_runtime_service=conversation_runtime,
    )
    created = reminder_service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="take medicine",
                trigger_time=NOW,
                captured_timezone="UTC",
                duration_minutes=15,
            )
        ],
    )
    fire = reminder_service.claim_due_fire(created.items[0].reminder_id, NOW)
    reminder_service.record_fire_delivery([fire.id], delivered=False)

    callbacks.record_inbound_reply_completed(
        trigger=SimpleNamespace(
            trigger_type="InboundTurn",
            account_id="acct_1",
            conversation_id="conversation_1",
            payload={
                "causal_inbound_event_id": "wa_msg_1",
                "_traceparent": (
                    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
                ),
            },
        ),
        delivered=True,
    )

    assert conversation_runtime.enqueued == [
        {
            "topic": "turn.undelivered_resend",
            "idempotency_key": "undelivered_resend:acct_1:wa_msg_1",
            "payload": {
                "trigger_id": "undelivered_resend:acct_1:wa_msg_1",
                "trigger_type": "UndeliveredResendTurn",
                "account_id": "acct_1",
                "conversation_id": "conversation_1",
                "causal_inbound_event_id": "wa_msg_1",
                "framing": "previously_undelivered",
                "fire_ids": [fire.id],
            },
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
        }
    ]


def test_inbound_reply_completion_enqueues_undelivered_notification_resend():
    reminder_service = make_reminder_service()
    social_service, repo = make_social_service()
    conversation_runtime = FakeConversationRuntimeService()
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
        conversation_runtime_service=conversation_runtime,
    )

    callbacks.record_inbound_reply_completed(
        trigger=SimpleNamespace(
            trigger_type="InboundTurn",
            account_id="acct_1",
            conversation_id="conversation_1",
            payload={
                "causal_inbound_event_id": "wa_msg_2",
                "_traceparent": (
                    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
                ),
            },
        ),
        delivered=True,
    )

    assert (
        repo.get_notification_recipient("notification_fact_1", "acct_1").delivery_state
        == "undelivered"
    )
    assert conversation_runtime.enqueued == [
        {
            "topic": "turn.undelivered_resend",
            "idempotency_key": "undelivered_resend:acct_1:wa_msg_2",
            "payload": {
                "trigger_id": "undelivered_resend:acct_1:wa_msg_2",
                "trigger_type": "UndeliveredResendTurn",
                "account_id": "acct_1",
                "conversation_id": "conversation_1",
                "causal_inbound_event_id": "wa_msg_2",
                "framing": "previously_undelivered",
                "notification_fact_ids": ["notification_fact_1"],
            },
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
        }
    ]


def test_inbound_reply_completion_does_not_resend_when_reply_delivery_failed():
    reminder_service = make_reminder_service()
    social_service, _repo = make_social_service()
    conversation_runtime = FakeConversationRuntimeService()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
        conversation_runtime_service=conversation_runtime,
    )
    created = reminder_service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="take medicine",
                trigger_time=NOW,
                captured_timezone="UTC",
                duration_minutes=15,
            )
        ],
    )
    fire = reminder_service.claim_due_fire(created.items[0].reminder_id, NOW)
    reminder_service.record_fire_delivery([fire.id], delivered=False)

    callbacks.record_inbound_reply_completed(
        trigger=SimpleNamespace(
            trigger_type="InboundTurn",
            account_id="acct_1",
            conversation_id="conversation_1",
            payload={"causal_inbound_event_id": "wa_msg_3"},
        ),
        delivered=False,
    )

    assert conversation_runtime.enqueued == []


def test_inbound_reply_completion_marks_first_guidance_only_for_visible_onboarding():
    reminder_service = make_reminder_service()
    social_service, _repo = make_social_service()
    identity_access = FakeIdentityAccessService()
    callbacks = OutputLifecycleDeliveryCallbacks(
        reminder_service=reminder_service,
        social_scheduling_service=social_service,
        identity_access_service=identity_access,
    )
    trigger = SimpleNamespace(
        trigger_type="InboundTurn",
        account_id="acct_1",
        conversation_id="conversation_1",
        payload={"causal_inbound_event_id": "wa_msg_guidance"},
    )

    callbacks.record_inbound_reply_completed(
        trigger=trigger,
        delivered=True,
        onboarding_guidance_delivered=False,
    )
    callbacks.record_inbound_reply_completed(
        trigger=trigger,
        delivered=False,
        onboarding_guidance_delivered=True,
    )
    callbacks.record_inbound_reply_completed(
        trigger=trigger,
        delivered=True,
        onboarding_guidance_delivered=True,
    )

    assert identity_access.guidance_marks == ["acct_1"]


def test_reconciler_settles_stale_pending_notification_after_terminal_turn():
    _reminder_service = make_reminder_service()
    social_service, repo = make_social_service()
    recipient = repo.get_notification_recipient("notification_fact_1", "acct_1")
    repo.save_notification_recipient(
        replace(
            recipient,
            turn_id="turn_terminal",
            updated_at=NOW - timedelta(hours=1),
        )
    )

    class TerminalRuntime:
        def get_disposition(self, turn_id):
            assert turn_id == "turn_terminal"
            return SimpleNamespace(
                disposition="failed",
                reason_code="invalid_output_protocol",
            )

    settled = social_service.reconcile_terminal_notification_recipients(
        conversation_runtime=TerminalRuntime(),
        pending_older_than=timedelta(minutes=5),
    )

    assert settled == 1
    repaired = repo.get_notification_recipient("notification_fact_1", "acct_1")
    assert repaired.delivery_state == "failed"
    assert repaired.turn_id == "turn_terminal"
    assert repaired.error_facts == {
        "type": "notification_turn_terminal_without_recipient_settlement",
        "turn_disposition": "failed",
        "reason_code": "invalid_output_protocol",
    }


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
