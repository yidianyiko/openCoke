from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains._pg import db_id
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
    FriendResolutionResult,
    Friendship,
    FriendshipResult,
    NotificationDeliveryState,
    NotificationFact,
    NotificationRecipient,
    PublicFriendLinkView,
    RecoverableSchedulingIntent,
    ReminderProjection,
    SharedReminder,
    SharedReminderCancellationResult,
    SharedReminderCreateResult,
    SharedReminderUpdateResult,
    SocialSchedulingOutcome,
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
        owner_account_id = _canon(owner_account_id)
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
        owner_account_id = _canon(owner_account_id)
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
        owner_account_id = _canon(owner_account_id)
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
        joiner_account_id = _canon(joiner_account_id)
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
        joiner_account_id = _canon(joiner_account_id)
        link = self.repository.get_friend_link_by_code_hash(_hash_token(link_code))
        if link is None:
            raise SocialSchedulingError("friend_link_not_found")
        return self._establish_from_link(
            joiner_account_id, link, commit_guard=commit_guard
        )

    def resolve_public_friend_link(self, link_code: str) -> PublicFriendLinkView | None:
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
        joiner_account_id = _canon(joiner_account_id)
        link = self.repository.get_friend_link(friend_link_id)
        if link is None:
            raise SocialSchedulingError("friend_link_not_found")
        self._require_usable_channel(joiner_account_id, "joiner_channel_required")
        return self._establish_from_link(
            joiner_account_id,
            link,
            commit_guard=commit_guard,
        )

    def list_friends(self, account_id: str) -> list[FriendListEntry]:
        account_id = _canon(account_id)
        friends: list[FriendListEntry] = []
        for friendship in self.repository.list_active_friendships(account_id):
            friend_account_id = friendship.other_account_id(account_id)
            friends.append(
                FriendListEntry(
                    account_id=friend_account_id,
                    friendship_id=friendship.id,
                    display_name=self.display_name_resolver(friend_account_id),
                )
            )
        return friends

    def resolve_active_friend_reference(
        self,
        account_id: str,
        text: str,
    ) -> FriendResolutionResult:
        account_id = _canon(account_id)
        normalized_text = _normalize_friend_reference(text)
        if not normalized_text:
            return FriendResolutionResult(status="unmatched")
        exact_candidates: list[str] = []
        partial_candidates: list[str] = []
        for friend in self.list_friends(account_id):
            if normalized_text in {
                _normalize_friend_reference(friend.account_id),
                _normalize_friend_reference(friend.display_name),
            }:
                exact_candidates.append(friend.account_id)
                continue
            if _partial_friend_display_name_match(normalized_text, friend.display_name):
                partial_candidates.append(friend.account_id)
        candidates = exact_candidates or partial_candidates
        unique_candidates = tuple(dict.fromkeys(candidates))
        if len(unique_candidates) == 1:
            return FriendResolutionResult(
                status="matched",
                matched_account_id=unique_candidates[0],
                candidates=unique_candidates,
            )
        if unique_candidates:
            return FriendResolutionResult(
                status="ambiguous",
                candidates=unique_candidates,
            )
        return FriendResolutionResult(status="unmatched")

    def create_recoverable_intent_from_outcome(
        self,
        *,
        conversation_id: str,
        creator_account_id: str,
        outcome: SocialSchedulingOutcome,
        unresolved_reference_text: str,
        source_turn_id: str,
        source_input_from_seq: int,
        source_input_to_seq: int,
        source_message_ids: tuple[str, ...],
    ) -> RecoverableSchedulingIntent | None:
        creator_account_id = _canon(creator_account_id)
        blocker_by_status = {
            "blocked_unmatched_friend": "unmatched_friend",
            "blocked_ambiguous_friend": "ambiguous_friend",
        }
        blocker = blocker_by_status.get(outcome.status)
        if blocker is None:
            return None
        if outcome.operation not in {
            "create_shared_reminder",
            "detect_and_create_shared_reminder",
        }:
            return None
        if outcome.title is None or outcome.local_trigger_at is None:
            return None
        if not outcome.captured_timezone:
            return None
        unresolved = unresolved_reference_text.strip()
        if not unresolved:
            return None
        now = self._now()
        facts = {
            "operation": "shared_reminder_create",
            "blocker": blocker,
            "title": outcome.title,
            "local_trigger_at": outcome.local_trigger_at.isoformat(),
            "captured_timezone": outcome.captured_timezone,
            "duration_minutes": outcome.duration_minutes,
            "unresolved_reference_text": unresolved,
            "source_turn_id": source_turn_id,
            "source_input_from_seq": source_input_from_seq,
            "source_input_to_seq": source_input_to_seq,
            "source_message_ids": list(source_message_ids),
        }
        intent = RecoverableSchedulingIntent(
            id=self._new_id("recoverable_intent"),
            conversation_id=conversation_id,
            creator_account_id=creator_account_id,
            operation="shared_reminder_create",
            status="open",
            blocker=blocker,  # type: ignore[arg-type]
            title=outcome.title,
            local_trigger_at=outcome.local_trigger_at,
            captured_timezone=outcome.captured_timezone,
            duration_minutes=outcome.duration_minutes,
            unresolved_reference_text=unresolved,
            source_turn_id=source_turn_id,
            source_input_from_seq=source_input_from_seq,
            source_input_to_seq=source_input_to_seq,
            source_message_ids=tuple(source_message_ids),
            facts=facts,
            facts_hash=canonical_hash(facts),
            expires_at=now + timedelta(minutes=15),
            consumed_turn_id=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_recoverable_intent(intent)
        return intent

    def recoverable_intent_for_correction(
        self,
        *,
        conversation_id: str,
        prior_reference_text: str,
    ) -> RecoverableSchedulingIntent | None:
        intent = self.repository.open_recoverable_intent_for_conversation(
            conversation_id,
            now=self._now(),
        )
        if intent is None:
            return None
        if _normalize_friend_reference(prior_reference_text) != (
            _normalize_friend_reference(intent.unresolved_reference_text)
        ):
            return None
        return intent

    def consume_recoverable_intent(
        self,
        intent_id: str,
        *,
        facts_hash: str,
        consumed_turn_id: str,
    ) -> RecoverableSchedulingIntent:
        return self.repository.consume_recoverable_intent(
            intent_id,
            facts_hash=facts_hash,
            consumed_turn_id=consumed_turn_id,
            now=self._now(),
        )

    def friend_identifiers_for_shared_reminder(
        self,
        shared_reminder_id: str,
        viewer_account_id: str,
    ) -> list[str]:
        viewer_account_id = _canon(viewer_account_id)
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
        account_id = _canon(account_id)
        friend_account_id = _canon(friend_account_id)
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
        commit_guard: CommitGuard = None,
    ) -> SharedReminderCreateResult:
        creator_account_id = _canon(creator_account_id)
        receiver_account_ids = [
            _canon(account_id) for account_id in receiver_account_ids
        ]
        local_trigger_at = _as_local_wall_clock(local_trigger_at)
        missing = _first_missing_field(receiver_account_ids, title, local_trigger_at)
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
        commit_guard: CommitGuard = None,
    ) -> SharedReminderCreateResult:
        creator_account_id = _canon(creator_account_id)
        receiver_account_ids = [
            _canon(account_id) for account_id in receiver_account_ids
        ]
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
            commit_guard=commit_guard,
        )

    def list_shared_reminders(self, account_id: str) -> list[SharedReminder]:
        account_id = _canon(account_id)
        return self.repository.list_shared_reminders_for_participant(account_id)

    def view_shared_reminder(
        self, account_id: str, shared_reminder_id: str
    ) -> SharedReminder:
        account_id = _canon(account_id)
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
        account_id = _canon(account_id)
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

    def update_shared_reminder(
        self,
        *,
        account_id: str,
        shared_reminder_id: str,
        local_trigger_at: datetime | None,
        captured_timezone: str | None = None,
        duration_minutes: int | None = None,
        commit_guard: CommitGuard = None,
    ) -> SharedReminderUpdateResult:
        account_id = _canon(account_id)
        reminder = self.view_shared_reminder(account_id, shared_reminder_id)
        projections = self.repository.list_projections(shared_reminder_id)
        if reminder.status == "cancelled":
            return SharedReminderUpdateResult(
                status="already_cancelled",
                shared_reminder=reminder,
                projections=projections,
            )
        if local_trigger_at is None and duration_minutes is None:
            return SharedReminderUpdateResult(
                status="needs_update_fields",
                shared_reminder=reminder,
                projections=projections,
                follow_up_facts={"missing": "time_or_duration"},
            )

        proposed_time = (
            _as_local_wall_clock(local_trigger_at)
            if local_trigger_at is not None
            else reminder.local_trigger_at
        )
        if proposed_time is None:
            return SharedReminderUpdateResult(
                status="needs_time",
                shared_reminder=reminder,
                projections=projections,
                follow_up_facts={"missing": "time"},
            )
        proposed_timezone = captured_timezone or reminder.captured_timezone
        proposed_duration = (
            _positive_duration_minutes(duration_minutes)
            if duration_minutes is not None
            else reminder.duration_minutes
        )
        if (
            proposed_time == reminder.local_trigger_at
            and proposed_timezone == reminder.captured_timezone
            and proposed_duration == reminder.duration_minutes
        ):
            return SharedReminderUpdateResult(
                status="needs_update_fields",
                shared_reminder=reminder,
                projections=projections,
                follow_up_facts={
                    "missing": "time_or_duration",
                    "reason": "no_change",
                },
            )
        time_state = self._validate_shared_trigger_time(
            proposed_time,
            proposed_timezone,
        )
        if time_state != "valid_future":
            return SharedReminderUpdateResult(
                status=time_state,
                shared_reminder=reminder,
                projections=projections,
                follow_up_facts={
                    "time_state": time_state,
                    "local_trigger_at": proposed_time.isoformat(),
                    "captured_timezone": proposed_timezone,
                },
            )

        duplicate = self.repository.get_duplicate_active_shared_reminder(
            reminder.creator_account_id,
            reminder.participant_set_hash,
            reminder.title_hash,
            proposed_time,
            proposed_timezone,
            proposed_duration,
        )
        if duplicate is not None and duplicate.id != reminder.id:
            return SharedReminderUpdateResult(
                status="duplicate",
                shared_reminder=duplicate,
                projections=self.repository.list_projections(duplicate.id),
            )

        start = proposed_time
        end = start + timedelta(minutes=proposed_duration)
        exclude_detail_ids = {
            reminder.id,
            *[projection.reminder_id for projection in projections],
        }
        participants = list(reminder.participant_account_ids)
        conflicting = [
            participant
            for participant in participants
            if self._busy_intervals_for(
                account_id=participant,
                start=start,
                end=end,
                requester_timezone=proposed_timezone,
                exclude_detail_ids=exclude_detail_ids,
            )
        ]
        unreachable = [
            participant
            for participant in participants
            if not self.reachability.has_usable_channel(participant)
        ]
        available = [
            participant
            for participant in participants
            if participant not in set(conflicting)
            and participant not in set(unreachable)
        ]
        if conflicting or unreachable:
            return SharedReminderUpdateResult(
                status="blocked",
                shared_reminder=None,
                projections=[],
                breakdown={
                    "conflicting_participants": sorted(conflicting),
                    "unreachable_participants": sorted(unreachable),
                    "available_participants": sorted(available),
                },
            )

        now = self._now()
        updated_reminder = replace(
            reminder,
            local_trigger_at=proposed_time,
            captured_timezone=proposed_timezone,
            duration_minutes=proposed_duration,
            updated_at=now,
        )
        updated_projections = [
            (
                replace(projection, updated_at=now)
                if projection.lifecycle == "active"
                else projection
            )
            for projection in projections
        ]
        with self.repository.atomic():
            _run_commit_guard(commit_guard)
            self.repository.save_shared_reminder(updated_reminder)
            for projection in updated_projections:
                self.repository.save_projection(projection)
            self.repository.sync_projection_reminders(
                updated_reminder,
                updated_projections,
            )
            notification = self._create_shared_reminder_notification(
                updated_reminder,
                "rescheduled",
                actor_account_id=account_id,
                recipients=[
                    participant
                    for participant in updated_reminder.participant_account_ids
                    if participant != account_id
                ],
            )
        return SharedReminderUpdateResult(
            status="rescheduled",
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
        account_id = _canon(account_id)
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
        requester_account_id = _canon(requester_account_id)
        friend_account_ids = [_canon(account_id) for account_id in friend_account_ids]
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
                    friend_display_name=self.display_name_resolver(friend_account_id),
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
        recipient_account_id = _canon(recipient_account_id)
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
        recipient_account_id = _canon(recipient_account_id)
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

    def reconcile_terminal_notification_recipients(
        self,
        *,
        conversation_runtime,
        pending_older_than: timedelta,
    ) -> int:
        cutoff = self._now() - pending_older_than
        settled = 0
        terminal_dispositions = {
            "replied",
            "no_reply",
            "failed",
            "recovered",
            "superseded",
        }
        for fact in self.repository.list_notification_facts():
            for recipient in self.repository.list_notification_recipients(fact.id):
                if recipient.delivery_state != "pending":
                    continue
                if recipient.turn_id is None:
                    continue
                if recipient.updated_at > cutoff:
                    continue
                try:
                    disposition = conversation_runtime.get_disposition(
                        recipient.turn_id
                    )
                except Exception:
                    continue
                turn_disposition = str(getattr(disposition, "disposition", ""))
                if turn_disposition not in terminal_dispositions:
                    continue
                reason_code = getattr(disposition, "reason_code", None)
                self.record_notification_delivery(
                    notification_fact_id=recipient.notification_fact_id,
                    recipient_account_id=recipient.recipient_account_id,
                    delivery_state="failed",
                    error_facts={
                        "type": (
                            "notification_turn_terminal_without_recipient_settlement"
                        ),
                        "turn_disposition": turn_disposition,
                        **(
                            {"reason_code": reason_code}
                            if isinstance(reason_code, str) and reason_code
                            else {}
                        ),
                    },
                    turn_id=recipient.turn_id,
                )
                settled += 1
        return settled

    def _establish_from_link(
        self,
        joiner_account_id: str,
        link: FriendLink,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
        if link.lifecycle != "active":
            raise SocialSchedulingError("friend_link_disabled")
        self._require_usable_channel(link.owner_account_id, "owner_channel_required")
        if joiner_account_id == link.owner_account_id:
            raise SocialSchedulingError("self_friendship_forbidden")
        active = self.repository.get_active_friendship(
            joiner_account_id, link.owner_account_id
        )
        if active is not None:
            return self._friendship_result(
                "already_active", active, link.owner_account_id
            )
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
        return self._friendship_result("created", friendship, link.owner_account_id)

    def _friendship_result(
        self,
        status: Literal["created", "already_active"],
        friendship: Friendship,
        counterpart_account_id: str,
    ) -> FriendshipResult:
        return FriendshipResult(
            status=status,
            friendship=friendship,
            counterpart_account_id=counterpart_account_id,
            counterpart_display_name=self.display_name_resolver(counterpart_account_id),
        )

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
            idempotency_key=_shared_notification_idempotency_key(reminder, status),
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
        exclude_detail_ids: set[str] | None = None,
    ):
        intervals = [
            *self.reminder_availability.personal_busy_intervals(
                account_id, start, end, requester_timezone
            ),
            *self.repository.shared_busy_intervals(account_id, start, end),
        ]
        if not exclude_detail_ids:
            return intervals
        return [
            interval
            for interval in intervals
            if interval.detail_id not in exclude_detail_ids
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


def _canon(account_id: str) -> str:
    return db_id(account_id)


def _as_local_wall_clock(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def _positive_duration_minutes(value: int) -> int:
    if isinstance(value, bool) or int(value) <= 0:
        raise SocialSchedulingError("invalid_duration_minutes")
    return int(value)


def _shared_notification_idempotency_key(
    reminder: SharedReminder,
    status: str,
) -> str:
    if status == "rescheduled":
        return (
            f"shared_reminder:{reminder.id}:{status}:{reminder.updated_at.isoformat()}"
        )
    return f"shared_reminder:{reminder.id}:{status}"


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().split()).lower()


def _normalize_friend_reference(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _friend_reference_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    current: list[str] = []
    for character in value.casefold():
        if character.isalnum():
            current.append(character)
            continue
        if current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def _partial_friend_display_name_match(
    normalized_reference: str,
    display_name: str,
) -> bool:
    normalized_display_name = _normalize_friend_reference(display_name)
    if not normalized_reference or not normalized_display_name:
        return False
    tokens = _friend_reference_tokens(display_name)
    if normalized_reference in tokens:
        return True
    if len(normalized_reference) < 3:
        return False
    if normalized_display_name.startswith(normalized_reference):
        return True
    return any(token.startswith(normalized_reference) for token in tokens)


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
) -> str | None:
    if not receiver_account_ids:
        return "participants"
    if title is None or title.strip() == "":
        return "title"
    if local_trigger_at is None:
        return "time"
    return None
