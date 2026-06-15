from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coke.composition import ReminderLifecycleFocusRepository
from coke.domains.conversation_runtime.models import Conversation, Turn
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.reminder.models import Reminder, ReminderOutboxEvent
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.social_scheduling.availability import (
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService

NOW = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)


class AlwaysReachable(ParticipantReachabilityPort):
    def has_usable_channel(self, account_id: str) -> bool:
        return True


class EmptyReminderAvailability(ReminderAvailabilityPort):
    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list:
        return []


def test_last_rendered_subject_prefers_newer_shared_reminder_with_friend_detail():
    clock = {"now": NOW}
    conversation_runtime = InMemoryConversationRuntimeRepository(
        now=lambda: clock["now"]
    )
    reminder_repository = InMemoryReminderRepository()
    social_repository = InMemorySocialSchedulingRepository()
    social_service = SocialSchedulingService(
        repository=social_repository,
        reachability=AlwaysReachable(),
        reminder_availability=EmptyReminderAvailability(),
        now=lambda: clock["now"],
        id_factory=lambda prefix: f"{prefix}_{len(social_repository.generated_ids) + 1}",
        token_factory=lambda prefix: (
            f"{prefix}_token_{len(social_repository.generated_tokens) + 1}"
        ),
        display_name_resolver=lambda account_id: {
            "owner": "Owner",
            "friend_b": "eva",
        }[account_id],
    )
    conversation_runtime.add_conversation(
        Conversation(
            id="conversation_1",
            account_id="owner",
            latest_inbound_seq=1,
            last_closed_inbound_seq=1,
            created_at=NOW - timedelta(hours=1),
            updated_at=NOW - timedelta(hours=1),
        )
    )
    conversation_runtime.add_turn(
        Turn(
            id="turn_personal",
            conversation_id="conversation_1",
            trigger_id="trigger_personal",
            trigger_type="InboundTurn",
            mode="interactive",
            input_from_seq=1,
            input_to_seq=1,
            superseded_by_inbound_seq=None,
            started_at=NOW - timedelta(minutes=30),
            completed_at=NOW - timedelta(minutes=29),
            created_at=NOW - timedelta(minutes=30),
            updated_at=NOW - timedelta(minutes=29),
        )
    )
    personal_reminder = _reminder("reminder_personal", "call 李梓豪")
    reminder_repository.add_reminder_with_outbox(
        personal_reminder,
        _lifecycle_event(
            event_id="outbox_personal",
            turn_id="turn_personal",
            reminder_id=personal_reminder.id,
            created_at=NOW - timedelta(minutes=20),
        ),
    )
    link = social_service.get_or_create_friend_link("owner")
    social_service.establish_friendship_from_token("friend_b", link.public_token)

    clock["now"] = NOW - timedelta(minutes=5)
    created = social_service.create_shared_reminder(
        creator_account_id="owner",
        receiver_account_ids=["friend_b"],
        title="开会",
        local_trigger_at=datetime(2026, 6, 16, 20, 0),
        captured_timezone="Asia/Shanghai",
        duration_minutes=30,
    )

    repository = ReminderLifecycleFocusRepository(
        conversation_runtime,
        reminder_repository,
        social_repository,
        display_name_resolver=social_service.display_name_resolver,
    )

    subject = repository.last_rendered_subject("conversation_1")

    assert subject is not None
    assert subject.subject_type == "shared_reminder"
    assert subject.object_ids == (created.shared_reminder.id,)
    assert subject.ordered is True
    assert subject.friend_name == "eva"
    assert subject.title == "开会"


def _reminder(reminder_id: str, content: str) -> Reminder:
    return Reminder(
        id=reminder_id,
        owner_account_id="owner",
        content=content,
        content_hash=f"hash-{reminder_id}",
        kind="timed",
        next_fire_at=NOW + timedelta(days=1),
        recurrence_rule={},
        captured_timezone="Asia/Shanghai",
        duration_minutes=15,
        lifecycle="active",
        hidden_from_calendar=False,
        shared_reminder_id=None,
        created_at=NOW - timedelta(minutes=20),
        updated_at=NOW - timedelta(minutes=20),
    )


def _lifecycle_event(
    *,
    event_id: str,
    turn_id: str,
    reminder_id: str,
    created_at: datetime,
) -> ReminderOutboxEvent:
    return ReminderOutboxEvent(
        id=event_id,
        topic="reminder.lifecycle",
        idempotency_key=f"reminder:create:{turn_id}",
        payload={
            "type": "reminder_lifecycle",
            "operation": "create",
            "reminder_id": reminder_id,
            "owner_account_id": "owner",
            "turn_id": turn_id,
            "kind": "timed",
            "lifecycle": "active",
            "next_fire_at": (NOW + timedelta(days=1)).isoformat(),
            "duration_minutes": 15,
            "shared_reminder_id": None,
        },
        traceparent="00-00000000000000000000000000000000-0000000000000000-01",
        status="pending",
        created_at=created_at,
        published_at=None,
        processed_at=None,
        acked_at=None,
        retry_count=0,
        last_error=None,
    )


def test_last_rendered_subject_prefers_newer_personal_reminder_over_older_shared():
    """Reverse direction (scenario C): a personal reminder created AFTER a shared
    reminder must win the recency anchor, carrying its content as title."""
    clock = {"now": NOW}
    conversation_runtime = InMemoryConversationRuntimeRepository(
        now=lambda: clock["now"]
    )
    reminder_repository = InMemoryReminderRepository()
    social_repository = InMemorySocialSchedulingRepository()
    social_service = SocialSchedulingService(
        repository=social_repository,
        reachability=AlwaysReachable(),
        reminder_availability=EmptyReminderAvailability(),
        now=lambda: clock["now"],
        id_factory=lambda prefix: f"{prefix}_{len(social_repository.generated_ids) + 1}",
        token_factory=lambda prefix: (
            f"{prefix}_token_{len(social_repository.generated_tokens) + 1}"
        ),
        display_name_resolver=lambda account_id: {
            "owner": "Owner",
            "friend_b": "eva",
        }[account_id],
    )
    conversation_runtime.add_conversation(
        Conversation(
            id="conversation_1",
            account_id="owner",
            latest_inbound_seq=1,
            last_closed_inbound_seq=1,
            created_at=NOW - timedelta(hours=1),
            updated_at=NOW - timedelta(hours=1),
        )
    )
    conversation_runtime.add_turn(
        Turn(
            id="turn_personal",
            conversation_id="conversation_1",
            trigger_id="trigger_personal",
            trigger_type="InboundTurn",
            mode="interactive",
            input_from_seq=1,
            input_to_seq=1,
            superseded_by_inbound_seq=None,
            started_at=NOW - timedelta(minutes=30),
            completed_at=NOW - timedelta(minutes=29),
            created_at=NOW - timedelta(minutes=30),
            updated_at=NOW - timedelta(minutes=29),
        )
    )
    link = social_service.get_or_create_friend_link("owner")
    social_service.establish_friendship_from_token("friend_b", link.public_token)

    # SHARED created EARLIER
    clock["now"] = NOW - timedelta(minutes=10)
    social_service.create_shared_reminder(
        creator_account_id="owner",
        receiver_account_ids=["friend_b"],
        title="开会",
        local_trigger_at=datetime(2026, 6, 16, 20, 0),
        captured_timezone="Asia/Shanghai",
        duration_minutes=30,
    )
    # PERSONAL created LATER -> must win
    personal_reminder = _reminder("reminder_water", "喝水")
    reminder_repository.add_reminder_with_outbox(
        personal_reminder,
        _lifecycle_event(
            event_id="outbox_water",
            turn_id="turn_personal",
            reminder_id=personal_reminder.id,
            created_at=NOW - timedelta(minutes=2),
        ),
    )

    repository = ReminderLifecycleFocusRepository(
        conversation_runtime,
        reminder_repository,
        social_repository,
        display_name_resolver=social_service.display_name_resolver,
    )

    subject = repository.last_rendered_subject("conversation_1")

    assert subject is not None
    assert subject.subject_type == "reminder"
    assert subject.object_ids == (personal_reminder.id,)
    assert subject.title == "喝水"
