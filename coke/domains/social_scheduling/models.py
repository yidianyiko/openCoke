from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

FriendLinkLifecycle = Literal["active", "disabled"]
FriendshipLifecycle = Literal["active", "removed"]
SharedReminderStatus = Literal["active", "cancelled"]
ProjectionLifecycle = Literal["active", "cancelled"]
ProjectionCompletionStatus = Literal["pending", "completed"]
NotificationDeliveryState = Literal["pending", "delivered", "undelivered", "failed"]
RecoverableSchedulingIntentStatus = Literal["open", "consumed", "expired", "superseded"]
RecoverableSchedulingIntentBlocker = Literal["unmatched_friend", "ambiguous_friend"]
SocialSchedulingOutcomeStatus = Literal[
    "created_active",
    "duplicate_active",
    "blocked_unmatched_friend",
    "blocked_ambiguous_friend",
    "blocked_receiver_conflict",
    "blocked_unreachable_participant",
    "needs_participants",
    "needs_title",
    "needs_time",
    "needs_context",
    "needs_past_time_confirmation",
    "needs_incomplete_date_clarification",
    "invalid",
    "staged_pending_close",
]
SocialSchedulingClaim = Literal[
    "active_created",
    "active_duplicate",
    "blocked_unmatched_friend",
    "blocked_ambiguous_friend",
    "blocked_receiver_conflict",
    "blocked_unreachable_participant",
    "needs_participants",
    "needs_title",
    "needs_time",
    "needs_context",
    "needs_past_time_confirmation",
    "needs_incomplete_date_clarification",
    "failed",
    "no_success_claim",
]
FriendResolutionStatus = Literal["matched", "ambiguous", "unmatched"]


class SocialSchedulingError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class FriendLink:
    id: str
    owner_account_id: str
    token_hash: str
    link_code_hash: str
    lifecycle: FriendLinkLifecycle
    reset_at: datetime | None
    disabled_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FriendLinkView:
    id: str
    owner_account_id: str
    lifecycle: FriendLinkLifecycle
    public_token: str | None
    link_code: str | None
    qr_payload: str | None


@dataclass(frozen=True, slots=True)
class PublicFriendLinkView:
    link_code: str
    status: Literal["active"]
    owner_display_name: str


@dataclass(frozen=True, slots=True)
class Friendship:
    id: str
    account_low_id: str
    account_high_id: str
    lifecycle: FriendshipLifecycle
    established_at: datetime
    removed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def other_account_id(self, account_id: str) -> str:
        if account_id == self.account_low_id:
            return self.account_high_id
        if account_id == self.account_high_id:
            return self.account_low_id
        raise SocialSchedulingError("friendship_not_found")


@dataclass(frozen=True, slots=True)
class FriendListEntry:
    account_id: str
    friendship_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class FriendResolutionResult:
    status: FriendResolutionStatus
    matched_account_id: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FriendshipResult:
    status: Literal["created", "already_active"]
    friendship: Friendship | None
    counterpart_account_id: str
    counterpart_display_name: str
    continuation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SharedReminder:
    id: str
    creator_account_id: str
    participant_account_ids: tuple[str, ...]
    participant_set_hash: str
    title: str
    title_hash: str
    local_trigger_at: datetime
    captured_timezone: str
    duration_minutes: int
    status: SharedReminderStatus
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RecoverableSchedulingIntent:
    id: str
    conversation_id: str
    creator_account_id: str
    operation: Literal["shared_reminder_create"]
    status: RecoverableSchedulingIntentStatus
    blocker: RecoverableSchedulingIntentBlocker
    title: str
    local_trigger_at: datetime
    captured_timezone: str
    duration_minutes: int | None
    unresolved_reference_text: str
    source_turn_id: str
    source_input_from_seq: int
    source_input_to_seq: int
    source_message_ids: tuple[str, ...]
    facts: dict[str, Any]
    facts_hash: str
    expires_at: datetime
    consumed_turn_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SocialSchedulingOutcome:
    outcome_id: str
    operation: str
    status: SocialSchedulingOutcomeStatus
    staged_command_id: str | None = None
    shared_reminder_id: str | None = None
    title: str | None = None
    local_trigger_at: datetime | None = None
    captured_timezone: str | None = None
    duration_minutes: int | None = None
    participant_account_ids: tuple[str, ...] = ()
    blocker: str | None = None
    facts_hash: str | None = None
    recoverable_scheduling_intent_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReminderProjection:
    id: str
    shared_reminder_id: str
    account_id: str
    reminder_id: str
    lifecycle: ProjectionLifecycle
    completion_status: ProjectionCompletionStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationFact:
    id: str
    type: str
    actor_account_id: str | None
    object_type: str
    object_id: str
    status: str
    facts: dict[str, Any]
    facts_hash: str
    idempotency_key: str
    outbox_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationRecipient:
    id: str
    notification_fact_id: str
    recipient_account_id: str
    delivery_state: NotificationDeliveryState
    error_facts: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class UndeliveredNotificationResendTurn:
    recipient_account_id: str
    notification_fact_ids: list[str]
    trigger_id: str


@dataclass(frozen=True, slots=True)
class SharedReminderCreateResult:
    status: Literal[
        "created",
        "duplicate",
        "blocked",
        "needs_participants",
        "needs_title",
        "needs_time",
        "needs_context",
        "needs_past_time_confirmation",
        "needs_incomplete_date_clarification",
        "invalid",
    ]
    shared_reminder: SharedReminder | None
    projections: list[ReminderProjection] = field(default_factory=list)
    breakdown: dict[str, list[str]] = field(default_factory=dict)
    follow_up_facts: dict[str, Any] = field(default_factory=dict)
    notification_facts: list[NotificationFact] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SharedReminderCancellationResult:
    status: Literal["cancelled", "already_cancelled"]
    shared_reminder: SharedReminder
    projections: list[ReminderProjection]
    notification_facts: list[NotificationFact] = field(default_factory=list)
