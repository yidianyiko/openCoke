from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from coke.domains.social_scheduling.availability import BusyInterval
from coke.domains.social_scheduling.models import (
    FriendLink,
    Friendship,
    NotificationFact,
    NotificationRecipient,
    ReminderProjection,
    SharedReminder,
)


class SocialSchedulingRepository(Protocol):
    def add_friend_link(
        self, link: FriendLink, public_token: str, link_code: str
    ) -> None: ...

    def save_friend_link(
        self, link: FriendLink, public_token: str | None, link_code: str | None
    ) -> None: ...

    def get_friend_link_by_owner(self, owner_account_id: str) -> FriendLink | None: ...

    def get_friend_link(self, friend_link_id: str) -> FriendLink | None: ...

    def get_public_token(self, friend_link_id: str) -> str | None: ...

    def get_link_code(self, friend_link_id: str) -> str | None: ...

    def get_friend_link_by_token_hash(self, token_hash: str) -> FriendLink | None: ...

    def get_friend_link_by_code_hash(
        self, link_code_hash: str
    ) -> FriendLink | None: ...

    def add_friendship(self, friendship: Friendship) -> None: ...

    def save_friendship(self, friendship: Friendship) -> None: ...

    def get_active_friendship(
        self, account_a: str, account_b: str
    ) -> Friendship | None: ...

    def list_active_friendships(self, account_id: str) -> list[Friendship]: ...

    def add_shared_reminder(self, shared_reminder: SharedReminder) -> None: ...

    def save_shared_reminder(self, shared_reminder: SharedReminder) -> None: ...

    def get_shared_reminder(self, shared_reminder_id: str) -> SharedReminder | None: ...

    def get_duplicate_active_shared_reminder(
        self,
        creator_account_id: str,
        participant_set_hash: str,
        title_hash: str,
        local_trigger_at: datetime,
        captured_timezone: str,
        duration_minutes: int,
    ) -> SharedReminder | None: ...

    def list_shared_reminders_for_participant(
        self, account_id: str
    ) -> list[SharedReminder]: ...

    def add_projection(self, projection: ReminderProjection) -> None: ...

    def save_projection(self, projection: ReminderProjection) -> None: ...

    def list_projections(self, shared_reminder_id: str) -> list[ReminderProjection]: ...

    def get_projection(
        self, shared_reminder_id: str, account_id: str
    ) -> ReminderProjection | None: ...

    def shared_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
    ) -> list[BusyInterval]: ...

    def add_notification_fact(self, fact: NotificationFact) -> None: ...

    def add_notification_recipient(self, recipient: NotificationRecipient) -> None: ...

    def save_notification_recipient(self, recipient: NotificationRecipient) -> None: ...

    def get_notification_recipient(
        self, notification_fact_id: str, recipient_account_id: str
    ) -> NotificationRecipient | None: ...

    def list_notification_facts(self) -> list[NotificationFact]: ...

    def list_notification_recipients(
        self, notification_fact_id: str
    ) -> list[NotificationRecipient]: ...


def unordered_pair(account_a: str, account_b: str) -> tuple[str, str]:
    if account_a <= account_b:
        return account_a, account_b
    return account_b, account_a


class InMemorySocialSchedulingRepository:
    def __init__(self) -> None:
        self.friend_links_by_id: dict[str, FriendLink] = {}
        self.friend_link_by_owner: dict[str, str] = {}
        self.friend_link_by_token_hash: dict[str, str] = {}
        self.friend_link_by_code_hash: dict[str, str] = {}
        self.public_tokens_by_link_id: dict[str, str] = {}
        self.link_codes_by_link_id: dict[str, str] = {}
        self.friendships_by_id: dict[str, Friendship] = {}
        self.shared_reminders_by_id: dict[str, SharedReminder] = {}
        self.projections_by_id: dict[str, ReminderProjection] = {}
        self.projections_by_shared_and_account: dict[tuple[str, str], str] = {}
        self.notification_facts_by_id: dict[str, NotificationFact] = {}
        self.notification_facts_by_idempotency: dict[str, str] = {}
        self.notification_recipients_by_id: dict[str, NotificationRecipient] = {}
        self.notification_recipients_by_fact_account: dict[tuple[str, str], str] = {}
        self.generated_ids: list[str] = []
        self.generated_tokens: list[str] = []

    def add_friend_link(
        self, link: FriendLink, public_token: str, link_code: str
    ) -> None:
        if link.id in self.friend_links_by_id:
            raise ValueError("duplicate_friend_link_id")
        if link.owner_account_id in self.friend_link_by_owner:
            raise ValueError("duplicate_friend_link_owner")
        if link.token_hash in self.friend_link_by_token_hash:
            raise ValueError("duplicate_friend_link_token_hash")
        if link.link_code_hash in self.friend_link_by_code_hash:
            raise ValueError("duplicate_friend_link_code_hash")
        self.friend_links_by_id[link.id] = link
        self.friend_link_by_owner[link.owner_account_id] = link.id
        self.friend_link_by_token_hash[link.token_hash] = link.id
        self.friend_link_by_code_hash[link.link_code_hash] = link.id
        self.public_tokens_by_link_id[link.id] = public_token
        self.link_codes_by_link_id[link.id] = link_code

    def save_friend_link(
        self, link: FriendLink, public_token: str | None, link_code: str | None
    ) -> None:
        existing = self.friend_links_by_id.get(link.id)
        if existing is None:
            raise ValueError("friend_link_not_found")
        self.friend_link_by_token_hash.pop(existing.token_hash, None)
        self.friend_link_by_code_hash.pop(existing.link_code_hash, None)
        if link.token_hash in self.friend_link_by_token_hash:
            raise ValueError("duplicate_friend_link_token_hash")
        if link.link_code_hash in self.friend_link_by_code_hash:
            raise ValueError("duplicate_friend_link_code_hash")
        self.friend_links_by_id[link.id] = link
        self.friend_link_by_owner[link.owner_account_id] = link.id
        self.friend_link_by_token_hash[link.token_hash] = link.id
        self.friend_link_by_code_hash[link.link_code_hash] = link.id
        if public_token is not None:
            self.public_tokens_by_link_id[link.id] = public_token
        if link_code is not None:
            self.link_codes_by_link_id[link.id] = link_code

    def get_friend_link_by_owner(self, owner_account_id: str) -> FriendLink | None:
        link_id = self.friend_link_by_owner.get(owner_account_id)
        return self.friend_links_by_id.get(link_id) if link_id is not None else None

    def get_friend_link(self, friend_link_id: str) -> FriendLink | None:
        return self.friend_links_by_id.get(friend_link_id)

    def get_public_token(self, friend_link_id: str) -> str | None:
        return self.public_tokens_by_link_id.get(friend_link_id)

    def get_link_code(self, friend_link_id: str) -> str | None:
        return self.link_codes_by_link_id.get(friend_link_id)

    def get_friend_link_by_token_hash(self, token_hash: str) -> FriendLink | None:
        link_id = self.friend_link_by_token_hash.get(token_hash)
        return self.friend_links_by_id.get(link_id) if link_id is not None else None

    def get_friend_link_by_code_hash(self, link_code_hash: str) -> FriendLink | None:
        link_id = self.friend_link_by_code_hash.get(link_code_hash)
        return self.friend_links_by_id.get(link_id) if link_id is not None else None

    def add_friendship(self, friendship: Friendship) -> None:
        if friendship.id in self.friendships_by_id:
            raise ValueError("duplicate_friendship_id")
        if friendship.lifecycle == "active":
            active = self.get_active_friendship(
                friendship.account_low_id, friendship.account_high_id
            )
            if active is not None:
                raise ValueError("duplicate_active_friendship")
        self.friendships_by_id[friendship.id] = friendship

    def save_friendship(self, friendship: Friendship) -> None:
        if friendship.id not in self.friendships_by_id:
            raise ValueError("friendship_not_found")
        if friendship.lifecycle == "active":
            active = self.get_active_friendship(
                friendship.account_low_id, friendship.account_high_id
            )
            if active is not None and active.id != friendship.id:
                raise ValueError("duplicate_active_friendship")
        self.friendships_by_id[friendship.id] = friendship

    def get_active_friendship(
        self, account_a: str, account_b: str
    ) -> Friendship | None:
        low, high = unordered_pair(account_a, account_b)
        for friendship in self.friendships_by_id.values():
            if (
                friendship.account_low_id == low
                and friendship.account_high_id == high
                and friendship.lifecycle == "active"
            ):
                return friendship
        return None

    def list_active_friendships(self, account_id: str) -> list[Friendship]:
        return [
            friendship
            for friendship in self.friendships_by_id.values()
            if friendship.lifecycle == "active"
            and account_id in {friendship.account_low_id, friendship.account_high_id}
        ]

    def list_active_friends(self, account_id: str) -> list[str]:
        return [
            friendship.other_account_id(account_id)
            for friendship in self.list_active_friendships(account_id)
        ]

    def add_shared_reminder(self, shared_reminder: SharedReminder) -> None:
        if shared_reminder.id in self.shared_reminders_by_id:
            raise ValueError("duplicate_shared_reminder_id")
        if shared_reminder.status == "active":
            duplicate = self.get_duplicate_active_shared_reminder(
                shared_reminder.creator_account_id,
                shared_reminder.participant_set_hash,
                shared_reminder.title_hash,
                shared_reminder.local_trigger_at,
                shared_reminder.captured_timezone,
                shared_reminder.duration_minutes,
            )
            if duplicate is not None:
                raise ValueError("duplicate_active_shared_reminder")
        self.shared_reminders_by_id[shared_reminder.id] = shared_reminder

    def save_shared_reminder(self, shared_reminder: SharedReminder) -> None:
        if shared_reminder.id not in self.shared_reminders_by_id:
            raise ValueError("shared_reminder_not_found")
        self.shared_reminders_by_id[shared_reminder.id] = shared_reminder

    def get_shared_reminder(self, shared_reminder_id: str) -> SharedReminder | None:
        return self.shared_reminders_by_id.get(shared_reminder_id)

    def get_duplicate_active_shared_reminder(
        self,
        creator_account_id: str,
        participant_set_hash: str,
        title_hash: str,
        local_trigger_at: datetime,
        captured_timezone: str,
        duration_minutes: int,
    ) -> SharedReminder | None:
        for reminder in self.shared_reminders_by_id.values():
            if (
                reminder.status == "active"
                and reminder.creator_account_id == creator_account_id
                and reminder.participant_set_hash == participant_set_hash
                and reminder.title_hash == title_hash
                and reminder.local_trigger_at == local_trigger_at
                and reminder.captured_timezone == captured_timezone
                and reminder.duration_minutes == duration_minutes
            ):
                return reminder
        return None

    def list_shared_reminders_for_participant(
        self, account_id: str
    ) -> list[SharedReminder]:
        reminders: list[SharedReminder] = []
        for reminder in self.shared_reminders_by_id.values():
            if account_id in reminder.participant_account_ids:
                reminders.append(reminder)
        return reminders

    def add_projection(self, projection: ReminderProjection) -> None:
        key = (projection.shared_reminder_id, projection.account_id)
        if projection.id in self.projections_by_id:
            raise ValueError("duplicate_projection_id")
        if key in self.projections_by_shared_and_account:
            raise ValueError("duplicate_projection_participant")
        self.projections_by_id[projection.id] = projection
        self.projections_by_shared_and_account[key] = projection.id

    def save_projection(self, projection: ReminderProjection) -> None:
        if projection.id not in self.projections_by_id:
            raise ValueError("projection_not_found")
        self.projections_by_id[projection.id] = projection
        self.projections_by_shared_and_account[
            (projection.shared_reminder_id, projection.account_id)
        ] = projection.id

    def list_projections(self, shared_reminder_id: str) -> list[ReminderProjection]:
        return [
            projection
            for projection in self.projections_by_id.values()
            if projection.shared_reminder_id == shared_reminder_id
        ]

    def get_projection(
        self, shared_reminder_id: str, account_id: str
    ) -> ReminderProjection | None:
        projection_id = self.projections_by_shared_and_account.get(
            (shared_reminder_id, account_id)
        )
        return self.projections_by_id.get(projection_id) if projection_id else None

    def shared_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
    ) -> list[BusyInterval]:
        intervals: list[BusyInterval] = []
        for reminder in self.list_shared_reminders_for_participant(account_id):
            if reminder.status != "active":
                continue
            projection = self.get_projection(reminder.id, account_id)
            if projection is None or projection.lifecycle != "active":
                continue
            interval_start = reminder.local_trigger_at
            interval_end = interval_start + timedelta(minutes=reminder.duration_minutes)
            if interval_start < end and interval_end > start:
                intervals.append(
                    BusyInterval(
                        account_id=account_id,
                        start=interval_start,
                        end=interval_end,
                        source="shared",
                        detail_id=reminder.id,
                    )
                )
        return intervals

    def add_notification_fact(self, fact: NotificationFact) -> None:
        if fact.id in self.notification_facts_by_id:
            raise ValueError("duplicate_notification_fact_id")
        if fact.idempotency_key in self.notification_facts_by_idempotency:
            raise ValueError("duplicate_notification_fact_idempotency")
        self.notification_facts_by_id[fact.id] = fact
        self.notification_facts_by_idempotency[fact.idempotency_key] = fact.id

    def add_notification_recipient(self, recipient: NotificationRecipient) -> None:
        key = (recipient.notification_fact_id, recipient.recipient_account_id)
        if recipient.id in self.notification_recipients_by_id:
            raise ValueError("duplicate_notification_recipient_id")
        if key in self.notification_recipients_by_fact_account:
            raise ValueError("duplicate_notification_recipient_fact_account")
        self.notification_recipients_by_id[recipient.id] = recipient
        self.notification_recipients_by_fact_account[key] = recipient.id

    def save_notification_recipient(self, recipient: NotificationRecipient) -> None:
        if recipient.id not in self.notification_recipients_by_id:
            raise ValueError("notification_recipient_not_found")
        self.notification_recipients_by_id[recipient.id] = recipient

    def get_notification_recipient(
        self, notification_fact_id: str, recipient_account_id: str
    ) -> NotificationRecipient | None:
        recipient_id = self.notification_recipients_by_fact_account.get(
            (notification_fact_id, recipient_account_id)
        )
        return (
            self.notification_recipients_by_id.get(recipient_id)
            if recipient_id is not None
            else None
        )

    def list_notification_facts(self) -> list[NotificationFact]:
        return list(self.notification_facts_by_id.values())

    def list_notification_recipients(
        self, notification_fact_id: str
    ) -> list[NotificationRecipient]:
        return [
            recipient
            for recipient in self.notification_recipients_by_id.values()
            if recipient.notification_fact_id == notification_fact_id
        ]
