from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.social_scheduling.availability import (
    FriendAvailability,
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
    build_busy_free_windows,
)
from coke.domains.social_scheduling.models import (
    FriendLink,
    FriendLinkView,
    FriendListEntry,
    Friendship,
    FriendshipResult,
    NotificationDeliveryState,
    NotificationFact,
    NotificationRecipient,
    PublicFriendLinkView,
    ReminderProjection,
    SharedReminder,
    SharedReminderCancellationResult,
    SharedReminderCreateResult,
    SocialSchedulingError,
    UndeliveredNotificationResendTurn,
)
from coke.domains.social_scheduling.notifications import (
    NotificationFactWriter,
    canonical_hash,
)
from coke.domains.social_scheduling.repository import (
    SocialSchedulingRepository,
    unordered_pair,
)

CommitGuard = Callable[[], None] | None


class SocialSchedulingService:
    def __init__(
        self,
        repository: SocialSchedulingRepository,
        reachability: ParticipantReachabilityPort,
        reminder_availability: ReminderAvailabilityPort,
        detector: Any | None = None,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
        token_factory: Callable[[str], str] | None = None,
        display_name_resolver: Callable[[str], str] | None = None,
        public_base_url: str = "http://localhost:4040",
    ) -> None:
        self.repository = repository
        self.reachability = reachability
        self.reminder_availability = reminder_availability
        self.detector = detector
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid4().hex}")
        self._token_factory = token_factory or (
            lambda prefix: f"{prefix}_{token_urlsafe(24)}"
        )
        self.display_name_resolver = display_name_resolver or _default_display_name
        self._public_base_url = public_base_url.rstrip("/") or "http://localhost:4040"
        self._notifications = NotificationFactWriter(
            repository=repository,
            now=self._now,
            id_factory=self._new_id,
        )

    def get_or_create_friend_link(
        self,
        owner_account_id: str,
        commit_guard: CommitGuard = None,
    ) -> FriendLinkView:
        self._require_usable_channel(owner_account_id, "owner_channel_required")
        existing = self.repository.get_friend_link_by_owner(owner_account_id)
        if existing is not None:
            if existing.lifecycle == "disabled":
                return self._link_view(existing, include_public=False)
            return self._link_view(existing, include_public=True)

        token = self._new_token("friend_link")
        code = self._new_token("friend_code")
        now = self._now()
        link = FriendLink(
            id=self._new_id("friend_link"),
            owner_account_id=owner_account_id,
            token_hash=_hash_token(token),
            link_code_hash=_hash_token(code),
            lifecycle="active",
            reset_at=None,
            disabled_at=None,
            created_at=now,
            updated_at=now,
        )
        _run_commit_guard(commit_guard)
        self.repository.add_friend_link(link, token, code)
        return self._link_view(link, include_public=True)

    def reset_friend_link(
        self,
        owner_account_id: str,
        commit_guard: CommitGuard = None,
    ) -> FriendLinkView:
        self._require_usable_channel(owner_account_id, "owner_channel_required")
        existing = self.repository.get_friend_link_by_owner(owner_account_id)
        if existing is None:
            return self.get_or_create_friend_link(owner_account_id, commit_guard)
        token = self._new_token("friend_link")
        code = self._new_token("friend_code")
        updated = replace(
            existing,
            token_hash=_hash_token(token),
            link_code_hash=_hash_token(code),
            lifecycle="active",
            reset_at=self._now(),
            disabled_at=None,
            updated_at=self._now(),
        )
        _run_commit_guard(commit_guard)
        self.repository.save_friend_link(updated, token, code)
        return self._link_view(updated, include_public=True)

    def disable_friend_link(
        self,
        owner_account_id: str,
        commit_guard: CommitGuard = None,
    ) -> FriendLinkView:
        existing = self.repository.get_friend_link_by_owner(owner_account_id)
        if existing is None:
            raise SocialSchedulingError("friend_link_not_found")
        updated = replace(
            existing,
            lifecycle="disabled",
            disabled_at=self._now(),
            updated_at=self._now(),
        )
        _run_commit_guard(commit_guard)
        self.repository.save_friend_link(updated, None, None)
        return self._link_view(updated, include_public=False)

    def establish_friendship_from_token(
        self,
        joiner_account_id: str,
        public_token: str,
        *,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
        link = self.repository.get_friend_link_by_token_hash(_hash_token(public_token))
        if link is None:
            raise SocialSchedulingError("friend_link_not_found")
        return self._establish_from_link(
            joiner_account_id, link, commit_guard=commit_guard
        )

    def establish_friendship_from_code(
        self,
        joiner_account_id: str,
        link_code: str,
        *,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
        link = self.repository.get_friend_link_by_code_hash(_hash_token(link_code))
        if link is None:
            raise SocialSchedulingError("friend_link_not_found")
        return self._establish_from_link(
            joiner_account_id, link, commit_guard=commit_guard
        )

    def resolve_public_friend_link(
        self, link_code: str
    ) -> PublicFriendLinkView | None:
        link = self.repository.get_friend_link_by_code_hash(_hash_token(link_code))
        if link is None or link.lifecycle != "active":
            return None
        if not self.reachability.has_usable_channel(link.owner_account_id):
            return None
        try:
            owner_display_name = self.display_name_resolver(link.owner_account_id)
        except Exception:
            return None
        return PublicFriendLinkView(
            link_code=link_code,
            status="active",
            owner_display_name=owner_display_name,
        )

    def complete_deferred_friend_link(
        self,
        joiner_account_id: str,
        friend_link_id: str,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
        link = self.repository.get_friend_link(friend_link_id)
        if link is None:
            raise SocialSchedulingError("friend_link_not_found")
        self._require_usable_channel(joiner_account_id, "joiner_channel_required")
        return self._establish_from_link(
            joiner_account_id,
            link,
            allow_defer=False,
            commit_guard=commit_guard,
        )

    def list_friends(self, account_id: str) -> list[FriendListEntry]:
        return [
            FriendListEntry(
                account_id=friendship.other_account_id(account_id),
                friendship_id=friendship.id,
                display_name=self.display_name_resolver(
                    friendship.other_account_id(account_id)
                ),
            )
            for friendship in self.repository.list_active_friendships(account_id)
        ]

    def friend_identifiers_for_shared_reminder(
        self,
        shared_reminder_id: str,
        viewer_account_id: str,
    ) -> list[str]:
        reminder = self.repository.get_shared_reminder(shared_reminder_id)
        if (
            reminder is None
            or viewer_account_id not in reminder.participant_account_ids
        ):
            return []
        return [
            self.display_name_resolver(account_id)
            for account_id in reminder.participant_account_ids
            if account_id != viewer_account_id
        ]

    def remove_friend(
        self,
        account_id: str,
        friend_account_id: str,
        commit_guard: CommitGuard = None,
    ) -> Friendship:
        friendship = self.repository.get_active_friendship(
            account_id, friend_account_id
        )
        if friendship is None:
            raise SocialSchedulingError(
                "friendship_not_found",
                fact={"type": "not_active_friend"},
            )
        updated = replace(
            friendship,
            lifecycle="removed",
            removed_at=self._now(),
            updated_at=self._now(),
        )
        _run_commit_guard(commit_guard)
        self.repository.save_friendship(updated)
        return updated

    def create_shared_reminder(
        self,
        *,
        creator_account_id: str,
        receiver_account_ids: list[str],
        title: str | None,
        local_trigger_at: datetime | None,
        captured_timezone: str,
        duration_minutes: int,
        context: dict | None,
        commit_guard: CommitGuard = None,
    ) -> SharedReminderCreateResult:
        local_trigger_at = _as_local_wall_clock(local_trigger_at)
        missing = _first_missing_field(
            receiver_account_ids, title, local_trigger_at, context
        )
        if missing is not None:
            return SharedReminderCreateResult(
                status=f"needs_{missing}",
                shared_reminder=None,
                follow_up_facts={"missing": missing},
            )
        time_state = self._validate_shared_trigger_time(
            local_trigger_at,
            captured_timezone,
        )
        if time_state != "valid_future":
            return SharedReminderCreateResult(
                status=time_state,
                shared_reminder=None,
                follow_up_facts={
                    "time_state": time_state,
                    "local_trigger_at": local_trigger_at.isoformat(),
                    "captured_timezone": captured_timezone,
                },
            )

        unique_receivers = _dedupe_preserve_order(receiver_account_ids)
        not_friends = [
            account_id
            for account_id in unique_receivers
            if self.repository.get_active_friendship(creator_account_id, account_id)
            is None
        ]
        if not_friends:
            return SharedReminderCreateResult(
                status="needs_participants",
                shared_reminder=None,
                follow_up_facts={
                    "missing": "participants",
                    "reason": "receiver_not_active_friend",
                    "receiver_account_ids": not_friends,
                },
            )

        participants = sorted(set([creator_account_id, *unique_receivers]))
        title_hash = _hash_value(_normalize_title(title))
        participant_set_hash = _hash_value("|".join(participants))
        duplicate = self.repository.get_duplicate_active_shared_reminder(
            creator_account_id,
            participant_set_hash,
            title_hash,
            local_trigger_at,
            captured_timezone,
            duration_minutes,
        )
        if duplicate is not None:
            return SharedReminderCreateResult(
                status="duplicate",
                shared_reminder=duplicate,
                projections=self.repository.list_projections(duplicate.id),
            )

        start = local_trigger_at
        end = start + timedelta(minutes=duration_minutes)
        conflicting = [
            account_id
            for account_id in unique_receivers
            if self._busy_intervals_for(
                account_id=account_id,
                start=start,
                end=end,
                requester_timezone=captured_timezone,
            )
        ]
        unreachable = [
            account_id
            for account_id in participants
            if not self.reachability.has_usable_channel(account_id)
        ]
        available = [
            account_id
            for account_id in unique_receivers
            if account_id not in set(conflicting) and account_id not in set(unreachable)
        ]
        if conflicting or unreachable:
            return SharedReminderCreateResult(
                status="blocked",
                shared_reminder=None,
                breakdown={
                    "conflicting_participants": sorted(conflicting),
                    "unreachable_participants": sorted(unreachable),
                    "available_participants": sorted(available),
                },
            )

        with self.repository.atomic():
            _run_commit_guard(commit_guard)
            now = self._now()
            reminder = SharedReminder(
                id=self._new_id("shared_reminder"),
                creator_account_id=creator_account_id,
                participant_account_ids=tuple(participants),
                participant_set_hash=participant_set_hash,
                title=title.strip(),
                title_hash=title_hash,
                local_trigger_at=local_trigger_at,
                captured_timezone=captured_timezone,
                duration_minutes=duration_minutes,
                status="active",
                cancelled_at=None,
                created_at=now,
                updated_at=now,
            )
            self.repository.add_shared_reminder(reminder)
            projections: list[ReminderProjection] = []
            for account_id in participants:
                projection = ReminderProjection(
                    id=self._new_id("reminder_projection"),
                    shared_reminder_id=reminder.id,
                    account_id=account_id,
                    reminder_id=self._new_id("reminder"),
                    lifecycle="active",
                    completion_status="pending",
                    created_at=self._now(),
                    updated_at=self._now(),
                )
                self.repository.add_projection(projection)
                projections.append(projection)
            notification = self._create_shared_reminder_notification(
                reminder, "created", recipients=unique_receivers
            )
        return SharedReminderCreateResult(
            status="created",
            shared_reminder=reminder,
            projections=projections,
            notification_facts=[notification],
        )

    def detect_and_create_shared_reminder(
        self,
        *,
        creator_account_id: str,
        receiver_account_ids: list[str],
        raw_text: str,
        title: str | None,
        captured_timezone: str,
        duration_minutes: int | None,
        context: dict | None,
        commit_guard: CommitGuard = None,
    ) -> SharedReminderCreateResult:
        if self.detector is None:
            raise SocialSchedulingError("detector_unavailable")
        try:
            zone = ZoneInfo(captured_timezone)
            detector_now = self._now().astimezone(zone)
            fields = self.detector.extract(raw_text, captured_timezone, detector_now)
        except (RuntimeError, ZoneInfoNotFoundError) as error:
            raise SocialSchedulingError("invalid_detector_output") from error

        detected_title = getattr(fields, "content", None)
        detected_trigger_at = self._detected_local_trigger_time(
            getattr(fields, "trigger_time", None),
            captured_timezone,
        )
        detected_duration = getattr(fields, "duration_minutes", None)
        return self.create_shared_reminder(
            creator_account_id=creator_account_id,
            receiver_account_ids=receiver_account_ids,
            title=title or detected_title,
            local_trigger_at=detected_trigger_at,
            captured_timezone=captured_timezone,
            duration_minutes=duration_minutes or detected_duration or 15,
            context=context,
            commit_guard=commit_guard,
        )

    def list_shared_reminders(self, account_id: str) -> list[SharedReminder]:
        return self.repository.list_shared_reminders_for_participant(account_id)

    def view_shared_reminder(
        self, account_id: str, shared_reminder_id: str
    ) -> SharedReminder:
        reminder = self.repository.get_shared_reminder(shared_reminder_id)
        if reminder is None or account_id not in reminder.participant_account_ids:
            raise SocialSchedulingError("shared_reminder_not_found")
        return reminder

    def cancel_shared_reminder(
        self,
        account_id: str,
        shared_reminder_id: str,
        commit_guard: CommitGuard = None,
    ) -> SharedReminderCancellationResult:
        reminder = self.view_shared_reminder(account_id, shared_reminder_id)
        projections = self.repository.list_projections(shared_reminder_id)
        if reminder.status == "cancelled":
            return SharedReminderCancellationResult(
                status="already_cancelled",
                shared_reminder=reminder,
                projections=projections,
                notification_facts=[],
            )
        updated_reminder = replace(
            reminder,
            status="cancelled",
            cancelled_at=self._now(),
            updated_at=self._now(),
        )
        updated_projections: list[ReminderProjection] = []
        with self.repository.atomic():
            _run_commit_guard(commit_guard)
            self.repository.save_shared_reminder(updated_reminder)
            for projection in projections:
                updated = replace(
                    projection,
                    lifecycle="cancelled",
                    updated_at=self._now(),
                )
                self.repository.save_projection(updated)
                updated_projections.append(updated)
            notification = self._create_shared_reminder_notification(
                updated_reminder,
                "cancelled",
                actor_account_id=account_id,
                recipients=[
                    participant
                    for participant in updated_reminder.participant_account_ids
                    if participant != account_id
                ],
            )
        return SharedReminderCancellationResult(
            status="cancelled",
            shared_reminder=updated_reminder,
            projections=updated_projections,
            notification_facts=[notification],
        )

    def complete_own_projection(
        self,
        account_id: str,
        shared_reminder_id: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderProjection:
        self.view_shared_reminder(account_id, shared_reminder_id)
        projection = self.repository.get_projection(shared_reminder_id, account_id)
        if projection is None:
            raise SocialSchedulingError("shared_projection_not_found")
        updated = replace(
            projection,
            completion_status="completed",
            updated_at=self._now(),
        )
        _run_commit_guard(commit_guard)
        self.repository.save_projection(updated)
        return updated

    def query_availability(
        self,
        *,
        requester_account_id: str,
        friend_account_ids: list[str],
        local_start: datetime,
        local_end: datetime,
        requester_timezone: str,
    ) -> FriendAvailability | list[FriendAvailability]:
        local_start = _as_local_wall_clock(local_start)
        local_end = _as_local_wall_clock(local_end)
        if not friend_account_ids:
            raise SocialSchedulingError(
                "availability_requires_one_or_more_friends",
                fact={"type": "availability_requires_one_or_more_friends"},
            )
        results: list[FriendAvailability] = []
        for friend_account_id in _dedupe_preserve_order(friend_account_ids):
            if (
                self.repository.get_active_friendship(
                    requester_account_id, friend_account_id
                )
                is None
            ):
                raise SocialSchedulingError("friendship_not_found")
            intervals = self._busy_intervals_for(
                account_id=friend_account_id,
                start=local_start,
                end=local_end,
                requester_timezone=requester_timezone,
            )
            results.append(
                FriendAvailability(
                    friend_account_id=friend_account_id,
                    windows=build_busy_free_windows(local_start, local_end, intervals),
                )
            )
        if len(results) == 1:
            return results[0]
        return results

    def record_notification_delivery(
        self,
        *,
        notification_fact_id: str,
        recipient_account_id: str,
        delivery_state: NotificationDeliveryState,
        error_facts: dict,
        turn_id: str | None = None,
    ) -> NotificationRecipient:
        recipient = self._notifications.record_delivery(
            notification_fact_id=notification_fact_id,
            recipient_account_id=recipient_account_id,
            delivery_state=delivery_state,
            error_facts=error_facts,
            turn_id=turn_id,
        )
        self._maybe_create_shared_reminder_delivery_receipt(recipient)
        return recipient

    def undelivered_notification_resend_turn(
        self, recipient_account_id: str
    ) -> UndeliveredNotificationResendTurn:
        notification_fact_ids: list[str] = []
        for fact in self.repository.list_notification_facts():
            recipient = self.repository.get_notification_recipient(
                fact.id,
                recipient_account_id,
            )
            if recipient is not None and recipient.delivery_state == "undelivered":
                notification_fact_ids.append(fact.id)
        return UndeliveredNotificationResendTurn(
            recipient_account_id=recipient_account_id,
            notification_fact_ids=notification_fact_ids,
            trigger_id=f"notification_undelivered:{recipient_account_id}",
        )

    def _establish_from_link(
        self,
        joiner_account_id: str,
        link: FriendLink,
        allow_defer: bool = True,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
        if link.lifecycle != "active":
            raise SocialSchedulingError("friend_link_disabled")
        self._require_usable_channel(link.owner_account_id, "owner_channel_required")
        if joiner_account_id == link.owner_account_id:
            raise SocialSchedulingError("self_friendship_forbidden")
        if not self.reachability.has_usable_channel(joiner_account_id):
            if allow_defer:
                return FriendshipResult(
                    status="deferred_channel_required",
                    friendship=None,
                    continuation={"friend_link_id": link.id},
                )
            raise SocialSchedulingError("joiner_channel_required")
        active = self.repository.get_active_friendship(
            joiner_account_id, link.owner_account_id
        )
        if active is not None:
            return FriendshipResult(status="already_active", friendship=active)
        low, high = unordered_pair(joiner_account_id, link.owner_account_id)
        friendship = Friendship(
            id=self._new_id("friendship"),
            account_low_id=low,
            account_high_id=high,
            lifecycle="active",
            established_at=self._now(),
            removed_at=None,
            created_at=self._now(),
            updated_at=self._now(),
        )
        with self.repository.atomic():
            _run_commit_guard(commit_guard)
            self.repository.add_friendship(friendship)
            self._create_friendship_notification(
                friendship, actor_account_id=joiner_account_id
            )
        return FriendshipResult(status="created", friendship=friendship)

    def _create_friendship_notification(
        self, friendship: Friendship, actor_account_id: str
    ) -> NotificationFact:
        participants = sorted([friendship.account_low_id, friendship.account_high_id])
        actor_display_name = self.display_name_resolver(actor_account_id)
        return self._notifications.create_fact(
            notification_type="friendship_created",
            actor_account_id=actor_account_id,
            object_type="friendship",
            object_id=friendship.id,
            status="created",
            facts={
                "actor_account_id": actor_account_id,
                "actor_display_name": actor_display_name,
                "object_type": "friendship",
                "object_id": friendship.id,
                "participants": participants,
                "status": "created",
                "occurred_at": self._now().isoformat(),
                "time": None,
                "timezone": None,
                "duration_minutes": None,
            },
            recipients=participants,
            idempotency_key=f"friendship_created:{friendship.id}:created",
        )

    def _create_shared_reminder_notification(
        self,
        reminder: SharedReminder,
        status: str,
        actor_account_id: str | None = None,
        recipients: list[str] | None = None,
    ) -> NotificationFact:
        actor_id = actor_account_id or reminder.creator_account_id
        return self._notifications.create_fact(
            notification_type=f"shared_reminder_{status}",
            actor_account_id=actor_id,
            object_type="shared_reminder",
            object_id=reminder.id,
            status=status,
            facts={
                "actor_account_id": actor_id,
                "actor_display_name": self.display_name_resolver(actor_id),
                "object_type": "shared_reminder",
                "object_id": reminder.id,
                "title": reminder.title,
                "participants": list(reminder.participant_account_ids),
                "time": reminder.local_trigger_at.isoformat(),
                "timezone": reminder.captured_timezone,
                "duration_minutes": reminder.duration_minutes,
                "status": status,
            },
            recipients=(
                recipients
                if recipients is not None
                else list(reminder.participant_account_ids)
            ),
            idempotency_key=f"shared_reminder:{reminder.id}:{status}",
        )

    def _maybe_create_shared_reminder_delivery_receipt(
        self, recipient: NotificationRecipient
    ) -> None:
        if recipient.delivery_state != "delivered":
            return
        fact = self._notification_fact_by_id(recipient.notification_fact_id)
        if fact is None or fact.type != "shared_reminder_created":
            return
        creator_account_id = str(fact.facts.get("actor_account_id") or "")
        if (
            not creator_account_id
            or recipient.recipient_account_id == creator_account_id
        ):
            return
        idempotency_key = (
            f"shared_reminder:{fact.object_id}:delivery_confirmed:"
            f"{recipient.recipient_account_id}"
        )
        if any(
            existing.idempotency_key == idempotency_key
            for existing in self.repository.list_notification_facts()
        ):
            return
        self._notifications.create_fact(
            notification_type="shared_reminder_delivery_confirmed",
            actor_account_id=recipient.recipient_account_id,
            object_type=fact.object_type,
            object_id=fact.object_id,
            status="delivered",
            facts={
                "creator_account_id": creator_account_id,
                "recipient_account_id": recipient.recipient_account_id,
                "recipient_display_name": self.display_name_resolver(
                    recipient.recipient_account_id
                ),
                "object_type": fact.object_type,
                "object_id": fact.object_id,
                "title": fact.facts.get("title"),
                "time": fact.facts.get("time"),
                "timezone": fact.facts.get("timezone"),
                "duration_minutes": fact.facts.get("duration_minutes"),
                "delivery_state": "delivered",
                "status": "delivered",
            },
            recipients=[creator_account_id],
            idempotency_key=idempotency_key,
        )

    def _notification_fact_by_id(
        self, notification_fact_id: str
    ) -> NotificationFact | None:
        for fact in self.repository.list_notification_facts():
            if fact.id == notification_fact_id:
                return fact
        return None

    def _busy_intervals_for(
        self,
        *,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ):
        return [
            *self.reminder_availability.personal_busy_intervals(
                account_id, start, end, requester_timezone
            ),
            *self.repository.shared_busy_intervals(account_id, start, end),
        ]

    def _link_view(self, link: FriendLink, include_public: bool) -> FriendLinkView:
        token = self.repository.get_public_token(link.id) if include_public else None
        code = self.repository.get_link_code(link.id) if include_public else None
        return FriendLinkView(
            id=link.id,
            owner_account_id=link.owner_account_id,
            lifecycle=link.lifecycle,
            public_token=token,
            link_code=code,
            qr_payload=f"{self._public_base_url}/u/{code}" if code else None,
        )

    def _require_usable_channel(self, account_id: str, code: str) -> None:
        if not self.reachability.has_usable_channel(account_id):
            raise SocialSchedulingError(
                code, fact={"type": code, "account_id": account_id}
            )

    def _validate_shared_trigger_time(
        self,
        local_trigger_at: datetime,
        captured_timezone: str,
    ) -> str:
        try:
            zone = ZoneInfo(captured_timezone)
        except ZoneInfoNotFoundError:
            return "invalid"
        trigger_in_zone = local_trigger_at.replace(tzinfo=zone)
        now_in_zone = self._now().astimezone(zone)
        if trigger_in_zone < now_in_zone:
            return "needs_past_time_confirmation"
        return "valid_future"

    def _detected_local_trigger_time(
        self,
        trigger_time: datetime | None,
        captured_timezone: str,
    ) -> datetime | None:
        if trigger_time is None:
            return None
        try:
            zone = ZoneInfo(captured_timezone)
        except ZoneInfoNotFoundError as error:
            raise SocialSchedulingError("invalid_detector_output") from error
        if trigger_time.tzinfo is not None:
            return trigger_time.astimezone(zone).replace(tzinfo=None)
        return trigger_time

    def _new_id(self, prefix: str) -> str:
        value = self._id_factory(prefix)
        generated = getattr(self.repository, "generated_ids", None)
        if generated is not None:
            generated.append(value)
        return value

    def _new_token(self, prefix: str) -> str:
        value = self._token_factory(prefix)
        generated = getattr(self.repository, "generated_tokens", None)
        if generated is not None:
            generated.append(value)
        return value


def _hash_token(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_value(value: str) -> str:
    return canonical_hash(value)


def _as_local_wall_clock(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().split()).lower()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _run_commit_guard(commit_guard: CommitGuard) -> None:
    if commit_guard is not None:
        commit_guard()


def _default_display_name(account_id: str) -> str:
    return account_id


def _first_missing_field(
    receiver_account_ids: list[str],
    title: str | None,
    local_trigger_at: datetime | None,
    context: dict | None,
) -> str | None:
    if not receiver_account_ids:
        return "participants"
    if title is None or title.strip() == "":
        return "title"
    if local_trigger_at is None:
        return "time"
    if context is None:
        return "context"
    return None
