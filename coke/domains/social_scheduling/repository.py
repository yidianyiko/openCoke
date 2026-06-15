from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import (
    db_id,
    insert_row,
    json_value,
    many,
    one_or_none,
    update_row,
    write_with_integrity,
)
from coke.domains.reminder.models import Reminder
from coke.domains.social_scheduling.availability import BusyInterval
from coke.domains.social_scheduling.models import (
    FriendLink,
    Friendship,
    NotificationFact,
    NotificationRecipient,
    ReminderProjection,
    SharedReminder,
)
from coke.infra.tracing import generate_traceparent


class SocialSchedulingRepository(Protocol):
    def atomic(self): ...

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

    def sync_projection_reminders(
        self,
        shared_reminder: SharedReminder,
        projections: list[ReminderProjection],
    ) -> None: ...

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
        self.projection_reminders_by_id: dict[str, Reminder] = {}
        self.notification_facts_by_id: dict[str, NotificationFact] = {}
        self.notification_facts_by_idempotency: dict[str, str] = {}
        self.notification_recipients_by_id: dict[str, NotificationRecipient] = {}
        self.notification_recipients_by_fact_account: dict[tuple[str, str], str] = {}
        self.generated_ids: list[str] = []
        self.generated_tokens: list[str] = []

    def atomic(self):
        return nullcontext()

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
            if (
                reminder.status == "active"
                and account_id in reminder.participant_account_ids
            ):
                reminders.append(reminder)
        return reminders

    def add_projection(self, projection: ReminderProjection) -> None:
        key = (projection.shared_reminder_id, projection.account_id)
        if projection.id in self.projections_by_id:
            raise ValueError("duplicate_projection_id")
        if key in self.projections_by_shared_and_account:
            raise ValueError("duplicate_projection_participant")
        if projection.reminder_id in self.projection_reminders_by_id:
            raise ValueError("duplicate_projection_reminder_id")
        shared = self.shared_reminders_by_id.get(projection.shared_reminder_id)
        if shared is None:
            raise ValueError("shared_reminder_not_found")
        self.projections_by_id[projection.id] = projection
        self.projections_by_shared_and_account[key] = projection.id
        self.projection_reminders_by_id[projection.reminder_id] = _projection_reminder(
            projection, shared
        )

    def save_projection(self, projection: ReminderProjection) -> None:
        if projection.id not in self.projections_by_id:
            raise ValueError("projection_not_found")
        self.projections_by_id[projection.id] = projection
        self.projections_by_shared_and_account[
            (projection.shared_reminder_id, projection.account_id)
        ] = projection.id
        if projection.lifecycle == "cancelled":
            reminder = self.projection_reminders_by_id.get(projection.reminder_id)
            if reminder is None:
                raise ValueError("projection_reminder_missing")
            self.projection_reminders_by_id[projection.reminder_id] = replace(
                reminder,
                lifecycle="deleted",
                updated_at=projection.updated_at,
            )

    def sync_projection_reminders(
        self,
        shared_reminder: SharedReminder,
        projections: list[ReminderProjection],
    ) -> None:
        for projection in projections:
            if projection.lifecycle != "active":
                continue
            if projection.reminder_id not in self.projection_reminders_by_id:
                raise ValueError("projection_reminder_missing")
            self.projection_reminders_by_id[projection.reminder_id] = (
                _projection_reminder(projection, shared_reminder)
            )

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


class PostgresSocialSchedulingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def atomic(self):
        return self.session.begin_nested()

    def add_friend_link(
        self, link: FriendLink, public_token: str, link_code: str
    ) -> None:
        def _write() -> None:
            self.session.execute(
                schema.friend_link.insert().values(**_link_values(link))
            )
            self._upsert_link_artifact(link, "friend_link_public_token", public_token)
            self._upsert_link_artifact(link, "friend_link_code", link_code)

        write_with_integrity(
            self.session,
            _write,
            {
                "pk_friend_link": "duplicate_friend_link_id",
                "uq_friend_link_token_hash": "duplicate_friend_link_token_hash",
                "uq_friend_link_code_hash": "duplicate_friend_link_code_hash",
                "uq_auth_artifact_token_hash": "duplicate_friend_link_token_hash",
            },
            default_error="duplicate_friend_link_token_hash",
        )

    def save_friend_link(
        self, link: FriendLink, public_token: str | None, link_code: str | None
    ) -> None:
        if self.get_friend_link(link.id) is None:
            raise ValueError("friend_link_not_found")

        def _write() -> None:
            self.session.execute(
                schema.friend_link.update()
                .where(schema.friend_link.c.id == link.id)
                .values(**_link_values(link))
            )
            if public_token is not None:
                self._upsert_link_artifact(
                    link, "friend_link_public_token", public_token
                )
            if link_code is not None:
                self._upsert_link_artifact(link, "friend_link_code", link_code)

        write_with_integrity(
            self.session,
            _write,
            {
                "uq_friend_link_token_hash": "duplicate_friend_link_token_hash",
                "uq_friend_link_code_hash": "duplicate_friend_link_code_hash",
                "uq_auth_artifact_token_hash": "duplicate_friend_link_token_hash",
            },
            default_error="duplicate_friend_link_token_hash",
        )

    def get_friend_link_by_owner(self, owner_account_id: str) -> FriendLink | None:
        row = one_or_none(
            self.session,
            schema.friend_link,
            schema.friend_link.c.owner_account_id == owner_account_id,
        )
        return _link(row) if row else None

    def get_friend_link(self, friend_link_id: str) -> FriendLink | None:
        row = one_or_none(
            self.session, schema.friend_link, schema.friend_link.c.id == friend_link_id
        )
        return _link(row) if row else None

    def get_public_token(self, friend_link_id: str) -> str | None:
        return self._link_artifact_token(friend_link_id, "friend_link_public_token")

    def get_link_code(self, friend_link_id: str) -> str | None:
        return self._link_artifact_token(friend_link_id, "friend_link_code")

    def get_friend_link_by_token_hash(self, token_hash: str) -> FriendLink | None:
        row = one_or_none(
            self.session,
            schema.friend_link,
            schema.friend_link.c.token_hash == token_hash,
        )
        return _link(row) if row else None

    def get_friend_link_by_code_hash(self, link_code_hash: str) -> FriendLink | None:
        row = one_or_none(
            self.session,
            schema.friend_link,
            schema.friend_link.c.link_code_hash == link_code_hash,
        )
        return _link(row) if row else None

    def add_friendship(self, friendship: Friendship) -> None:
        insert_row(
            self.session,
            schema.friendship,
            _friendship_values(friendship),
            {
                "pk_friendship": "duplicate_friendship_id",
                "uq_friendship_one_active_pair": "duplicate_active_friendship",
            },
            default_error="duplicate_active_friendship",
        )

    def save_friendship(self, friendship: Friendship) -> None:
        if (
            self.get_active_friendship(
                friendship.account_low_id, friendship.account_high_id
            )
            is None
            and one_or_none(
                self.session, schema.friendship, schema.friendship.c.id == friendship.id
            )
            is None
        ):
            raise ValueError("friendship_not_found")
        update_row(
            self.session,
            schema.friendship,
            _friendship_values(friendship),
            {"uq_friendship_one_active_pair": "duplicate_active_friendship"},
            default_error="duplicate_active_friendship",
        )

    def get_active_friendship(
        self, account_a: str, account_b: str
    ) -> Friendship | None:
        if not _is_db_uuid(account_a) or not _is_db_uuid(account_b):
            return None
        low, high = unordered_pair(account_a, account_b)
        row = one_or_none(
            self.session,
            schema.friendship,
            schema.friendship.c.account_low_id == low,
            schema.friendship.c.account_high_id == high,
            schema.friendship.c.lifecycle == "active",
        )
        return _friendship(row) if row else None

    def list_active_friendships(self, account_id: str) -> list[Friendship]:
        if not _is_db_uuid(account_id):
            return []
        return [
            _friendship(row)
            for row in many(
                self.session,
                schema.friendship,
                schema.friendship.c.lifecycle == "active",
                sa.or_(
                    schema.friendship.c.account_low_id == account_id,
                    schema.friendship.c.account_high_id == account_id,
                ),
                order_by=(schema.friendship.c.created_at, schema.friendship.c.id),
            )
        ]

    def list_active_friends(self, account_id: str) -> list[str]:
        return [
            friendship.other_account_id(account_id)
            for friendship in self.list_active_friendships(account_id)
        ]

    def add_shared_reminder(self, shared_reminder: SharedReminder) -> None:
        insert_row(
            self.session,
            schema.shared_reminder,
            _shared_values(shared_reminder),
            {
                "pk_shared_reminder": "duplicate_shared_reminder_id",
                "uq_shared_reminder_active_duplicate": "duplicate_active_shared_reminder",
            },
            default_error="duplicate_active_shared_reminder",
        )

    def save_shared_reminder(self, shared_reminder: SharedReminder) -> None:
        if self.get_shared_reminder(shared_reminder.id) is None:
            raise ValueError("shared_reminder_not_found")
        update_row(
            self.session,
            schema.shared_reminder,
            _shared_values(shared_reminder),
            {"uq_shared_reminder_active_duplicate": "duplicate_active_shared_reminder"},
            default_error="duplicate_active_shared_reminder",
        )

    def get_shared_reminder(self, shared_reminder_id: str) -> SharedReminder | None:
        if not _is_db_uuid(shared_reminder_id):
            return None
        row = one_or_none(
            self.session,
            schema.shared_reminder,
            schema.shared_reminder.c.id == shared_reminder_id,
        )
        return _shared(row, self._participant_ids(shared_reminder_id)) if row else None

    def get_duplicate_active_shared_reminder(
        self,
        creator_account_id: str,
        participant_set_hash: str,
        title_hash: str,
        local_trigger_at: datetime,
        captured_timezone: str,
        duration_minutes: int,
    ) -> SharedReminder | None:
        if not _is_db_uuid(creator_account_id):
            return None
        row = one_or_none(
            self.session,
            schema.shared_reminder,
            schema.shared_reminder.c.status == "active",
            schema.shared_reminder.c.creator_account_id == creator_account_id,
            schema.shared_reminder.c.participant_set_hash == participant_set_hash,
            schema.shared_reminder.c.title_hash == title_hash,
            schema.shared_reminder.c.local_trigger_at == local_trigger_at,
            schema.shared_reminder.c.captured_timezone == captured_timezone,
            schema.shared_reminder.c.duration_minutes == duration_minutes,
        )
        return _shared(row, self._participant_ids(row["id"])) if row else None

    def list_shared_reminders_for_participant(
        self, account_id: str
    ) -> list[SharedReminder]:
        if not _is_db_uuid(account_id):
            return []
        statement = (
            sa.select(schema.shared_reminder)
            .join(
                schema.reminder_projection,
                schema.reminder_projection.c.shared_reminder_id
                == schema.shared_reminder.c.id,
            )
            .where(schema.reminder_projection.c.account_id == account_id)
            .where(schema.shared_reminder.c.status == "active")
            .order_by(schema.shared_reminder.c.created_at, schema.shared_reminder.c.id)
        )
        return [
            _shared(dict(row), self._participant_ids(db_id(row["id"])))
            for row in self.session.execute(statement).mappings()
        ]

    def add_projection(self, projection: ReminderProjection) -> None:
        def _write() -> None:
            if (
                one_or_none(
                    self.session,
                    schema.reminder,
                    schema.reminder.c.id == projection.reminder_id,
                )
                is None
            ):
                shared = self.get_shared_reminder(projection.shared_reminder_id)
                if shared is None:
                    raise ValueError("shared_reminder_not_found")
                self.session.execute(
                    schema.reminder.insert().values(
                        **_projection_reminder_values(projection, shared)
                    )
                )
            self.session.execute(
                schema.reminder_projection.insert().values(
                    **_projection_values(projection)
                )
            )

        write_with_integrity(
            self.session,
            _write,
            {
                "pk_reminder": "duplicate_projection_reminder_id",
                "pk_reminder_projection": "duplicate_projection_id",
                "uq_reminder_projection_participant": "duplicate_projection_participant",
                "fk_reminder_projection_reminder_id_reminder": "projection_reminder_missing",
                "fk_reminder_projection_shared_reminder_id_shared_reminder": "shared_reminder_not_found",
            },
            default_error="projection_write_failed",
        )

    def save_projection(self, projection: ReminderProjection) -> None:
        if (
            one_or_none(
                self.session,
                schema.reminder_projection,
                schema.reminder_projection.c.id == projection.id,
            )
            is None
        ):
            raise ValueError("projection_not_found")

        def _write() -> None:
            self.session.execute(
                schema.reminder_projection.update()
                .where(schema.reminder_projection.c.id == projection.id)
                .values(**_projection_values(projection))
            )
            if projection.lifecycle == "cancelled":
                self.session.execute(
                    schema.reminder.update()
                    .where(schema.reminder.c.id == projection.reminder_id)
                    .values(
                        lifecycle="deleted",
                        updated_at=projection.updated_at,
                    )
                )

        write_with_integrity(
            self.session,
            _write,
            {"uq_reminder_projection_participant": "duplicate_projection_participant"},
            default_error="duplicate_projection_participant",
        )

    def sync_projection_reminders(
        self,
        shared_reminder: SharedReminder,
        projections: list[ReminderProjection],
    ) -> None:
        for projection in projections:
            if projection.lifecycle != "active":
                continue
            self.session.execute(
                schema.reminder.update()
                .where(schema.reminder.c.id == projection.reminder_id)
                .values(**_projection_reminder_values(projection, shared_reminder))
            )

    def list_projections(self, shared_reminder_id: str) -> list[ReminderProjection]:
        if not _is_db_uuid(shared_reminder_id):
            return []
        return [
            _projection(row)
            for row in many(
                self.session,
                schema.reminder_projection,
                schema.reminder_projection.c.shared_reminder_id == shared_reminder_id,
                order_by=(
                    schema.reminder_projection.c.created_at,
                    schema.reminder_projection.c.id,
                ),
            )
        ]

    def get_projection(
        self, shared_reminder_id: str, account_id: str
    ) -> ReminderProjection | None:
        if not _is_db_uuid(shared_reminder_id) or not _is_db_uuid(account_id):
            return None
        row = one_or_none(
            self.session,
            schema.reminder_projection,
            schema.reminder_projection.c.shared_reminder_id == shared_reminder_id,
            schema.reminder_projection.c.account_id == account_id,
        )
        return _projection(row) if row else None

    def shared_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
    ) -> list[BusyInterval]:
        if not _is_db_uuid(account_id):
            return []
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
        def _write() -> None:
            if (
                one_or_none(
                    self.session, schema.outbox, schema.outbox.c.id == fact.outbox_id
                )
                is None
            ):
                self.session.execute(
                    schema.outbox.insert().values(**_notification_outbox_values(fact))
                )
            self.session.execute(
                schema.notification_fact.insert().values(**_fact_values(fact))
            )

        write_with_integrity(
            self.session,
            _write,
            {
                "pk_outbox": "duplicate_notification_outbox_id",
                "uq_outbox_idempotency_key": "duplicate_notification_fact_idempotency",
                "pk_notification_fact": "duplicate_notification_fact_id",
                "uq_notification_fact_idempotency": "duplicate_notification_fact_idempotency",
                "fk_notification_fact_outbox_id_outbox": "notification_outbox_missing",
            },
            default_error="notification_fact_write_failed",
        )

    def add_notification_recipient(self, recipient: NotificationRecipient) -> None:
        insert_row(
            self.session,
            schema.notification_recipient,
            _recipient_values(recipient),
            {
                "pk_notification_recipient": "duplicate_notification_recipient_id",
                "uq_notification_recipient_fact_account": "duplicate_notification_recipient_fact_account",
            },
            default_error="duplicate_notification_recipient_fact_account",
        )

    def save_notification_recipient(self, recipient: NotificationRecipient) -> None:
        if (
            one_or_none(
                self.session,
                schema.notification_recipient,
                schema.notification_recipient.c.id == recipient.id,
            )
            is None
        ):
            raise ValueError("notification_recipient_not_found")
        update_row(
            self.session,
            schema.notification_recipient,
            _recipient_values(recipient),
            {
                "uq_notification_recipient_fact_account": "duplicate_notification_recipient_fact_account"
            },
            default_error="duplicate_notification_recipient_fact_account",
        )

    def get_notification_recipient(
        self, notification_fact_id: str, recipient_account_id: str
    ) -> NotificationRecipient | None:
        row = one_or_none(
            self.session,
            schema.notification_recipient,
            schema.notification_recipient.c.notification_fact_id
            == notification_fact_id,
            schema.notification_recipient.c.recipient_account_id
            == recipient_account_id,
        )
        return _recipient(row) if row else None

    def list_notification_facts(self) -> list[NotificationFact]:
        return [
            _fact(row)
            for row in many(
                self.session,
                schema.notification_fact,
                order_by=(
                    schema.notification_fact.c.created_at,
                    schema.notification_fact.c.id,
                ),
            )
        ]

    def list_notification_recipients(
        self, notification_fact_id: str
    ) -> list[NotificationRecipient]:
        return [
            _recipient(row)
            for row in many(
                self.session,
                schema.notification_recipient,
                schema.notification_recipient.c.notification_fact_id
                == notification_fact_id,
                order_by=(
                    schema.notification_recipient.c.created_at,
                    schema.notification_recipient.c.id,
                ),
            )
        ]

    def _participant_ids(self, shared_reminder_id: str) -> tuple[str, ...]:
        if not _is_db_uuid(shared_reminder_id):
            return ()
        rows = many(
            self.session,
            schema.reminder_projection,
            schema.reminder_projection.c.shared_reminder_id == shared_reminder_id,
            order_by=(schema.reminder_projection.c.account_id,),
        )
        return tuple(db_id(row["account_id"]) for row in rows)

    def _upsert_link_artifact(
        self, link: FriendLink, artifact_type: str, token: str
    ) -> None:
        artifact_id = uuid5(NAMESPACE_URL, f"{link.id}:{artifact_type}").hex
        values = {
            "id": artifact_id,
            "account_id": link.owner_account_id,
            "target_account_id": None,
            "type": artifact_type,
            "purpose": "friend_link",
            "delivery": "web",
            "token_hash": token,
            "browser_session": link.id,
            "continuation": {"friend_link_id": link.id},
            "expires_at": link.updated_at,
            "consumed_at": None,
            "delivery_state": link.lifecycle,
            "resend_count": 0,
            "created_at": link.created_at,
            "updated_at": link.updated_at,
        }
        existing = one_or_none(
            self.session,
            schema.auth_artifact,
            schema.auth_artifact.c.id == artifact_id,
        )
        if existing is None:
            self.session.execute(schema.auth_artifact.insert().values(**values))
        else:
            self.session.execute(
                schema.auth_artifact.update()
                .where(schema.auth_artifact.c.id == artifact_id)
                .values(**values)
            )

    def _link_artifact_token(
        self, friend_link_id: str, artifact_type: str
    ) -> str | None:
        row = one_or_none(
            self.session,
            schema.auth_artifact,
            schema.auth_artifact.c.type == artifact_type,
            schema.auth_artifact.c.browser_session == friend_link_id,
        )
        return row["token_hash"] if row else None


def _link_values(link: FriendLink) -> dict:
    return {
        "id": link.id,
        "owner_account_id": link.owner_account_id,
        "token_hash": link.token_hash,
        "link_code_hash": link.link_code_hash,
        "lifecycle": link.lifecycle,
        "reset_at": link.reset_at,
        "disabled_at": link.disabled_at,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def _link(row: Mapping) -> FriendLink:
    return FriendLink(
        db_id(row["id"]),
        db_id(row["owner_account_id"]),
        row["token_hash"],
        row["link_code_hash"],
        row["lifecycle"],
        row["reset_at"],
        row["disabled_at"],
        row["created_at"],
        row["updated_at"],
    )


def _friendship_values(friendship: Friendship) -> dict:
    return {
        "id": friendship.id,
        "account_low_id": friendship.account_low_id,
        "account_high_id": friendship.account_high_id,
        "lifecycle": friendship.lifecycle,
        "established_at": friendship.established_at,
        "removed_at": friendship.removed_at,
        "created_at": friendship.created_at,
        "updated_at": friendship.updated_at,
    }


def _friendship(row: Mapping) -> Friendship:
    return Friendship(
        db_id(row["id"]),
        db_id(row["account_low_id"]),
        db_id(row["account_high_id"]),
        row["lifecycle"],
        row["established_at"],
        row["removed_at"],
        row["created_at"],
        row["updated_at"],
    )


def _is_db_uuid(value: str | None) -> bool:
    if value is None:
        return False
    try:
        UUID(str(value))
    except ValueError:
        return False
    return True


def _shared_values(reminder: SharedReminder) -> dict:
    return {
        "id": reminder.id,
        "creator_account_id": reminder.creator_account_id,
        "participant_set_hash": reminder.participant_set_hash,
        "title": reminder.title,
        "title_hash": reminder.title_hash,
        "local_trigger_at": reminder.local_trigger_at,
        "captured_timezone": reminder.captured_timezone,
        "duration_minutes": reminder.duration_minutes,
        "status": reminder.status,
        "cancelled_at": reminder.cancelled_at,
        "created_at": reminder.created_at,
        "updated_at": reminder.updated_at,
    }


def _shared(row: Mapping, participant_ids: tuple[str, ...]) -> SharedReminder:
    return SharedReminder(
        db_id(row["id"]),
        db_id(row["creator_account_id"]),
        participant_ids,
        row["participant_set_hash"],
        row["title"],
        row["title_hash"],
        row["local_trigger_at"],
        row["captured_timezone"],
        row["duration_minutes"],
        row["status"],
        row["cancelled_at"],
        row["created_at"],
        row["updated_at"],
    )


def _projection_values(projection: ReminderProjection) -> dict:
    return {
        "id": projection.id,
        "shared_reminder_id": projection.shared_reminder_id,
        "account_id": projection.account_id,
        "reminder_id": projection.reminder_id,
        "lifecycle": projection.lifecycle,
        "completion_status": projection.completion_status,
        "created_at": projection.created_at,
        "updated_at": projection.updated_at,
    }


def _projection(row: Mapping) -> ReminderProjection:
    return ReminderProjection(
        db_id(row["id"]),
        db_id(row["shared_reminder_id"]),
        db_id(row["account_id"]),
        db_id(row["reminder_id"]),
        row["lifecycle"],
        row["completion_status"],
        row["created_at"],
        row["updated_at"],
    )


def _projection_reminder(
    projection: ReminderProjection,
    shared: SharedReminder,
) -> Reminder:
    return Reminder(**_projection_reminder_values(projection, shared))


def _projection_reminder_values(
    projection: ReminderProjection,
    shared: SharedReminder,
) -> dict:
    next_fire_at = shared.local_trigger_at.replace(
        tzinfo=ZoneInfo(shared.captured_timezone)
    ).astimezone(UTC)
    return {
        "id": projection.reminder_id,
        "owner_account_id": projection.account_id,
        "content": shared.title,
        "content_hash": shared.title_hash,
        "kind": "shared_projection",
        "next_fire_at": next_fire_at,
        "recurrence_rule": {},
        "captured_timezone": shared.captured_timezone,
        "duration_minutes": shared.duration_minutes,
        "lifecycle": "active",
        "hidden_from_calendar": False,
        "shared_reminder_id": shared.id,
        "created_at": projection.created_at,
        "updated_at": projection.updated_at,
    }


def _fact_values(fact: NotificationFact) -> dict:
    return {
        "id": fact.id,
        "type": fact.type,
        "actor_account_id": fact.actor_account_id,
        "object_type": fact.object_type,
        "object_id": fact.object_id,
        "status": fact.status,
        "facts": json_value(fact.facts),
        "facts_hash": fact.facts_hash,
        "idempotency_key": fact.idempotency_key,
        "outbox_id": fact.outbox_id,
        "created_at": fact.created_at,
    }


def _fact(row: Mapping) -> NotificationFact:
    return NotificationFact(
        db_id(row["id"]),
        row["type"],
        db_id(row["actor_account_id"]) if row["actor_account_id"] is not None else None,
        row["object_type"],
        db_id(row["object_id"]),
        row["status"],
        dict(row["facts"]),
        row["facts_hash"],
        row["idempotency_key"],
        db_id(row["outbox_id"]),
        row["created_at"],
    )


def _notification_outbox_values(fact: NotificationFact) -> dict:
    recipients = _notification_recipients_from_fact(fact)
    return {
        "id": fact.outbox_id,
        "topic": "turn.notification",
        "idempotency_key": f"notification:{fact.idempotency_key}",
        "payload": {
            "trigger_id": f"notification:{fact.id}",
            "notification_fact_id": fact.id,
            "account_id": recipients[0] if recipients else fact.actor_account_id,
            "recipient_account_ids": recipients,
            "object_type": fact.object_type,
            "object_id": fact.object_id,
            "facts_hash": fact.facts_hash,
        },
        "traceparent": generate_traceparent(),
        "status": "pending",
        "created_at": fact.created_at,
        "published_at": None,
        "processed_at": None,
        "acked_at": None,
        "retry_count": 0,
        "last_error": None,
    }


def _notification_recipients_from_fact(fact: NotificationFact) -> list[str]:
    delivery_recipients = fact.facts.get("delivery_recipients")
    if isinstance(delivery_recipients, list):
        return sorted(str(recipient) for recipient in delivery_recipients)
    participants = fact.facts.get("participants")
    if isinstance(participants, list):
        return sorted(str(participant) for participant in participants)
    if fact.actor_account_id is not None:
        return [fact.actor_account_id]
    return []


def _recipient_values(recipient: NotificationRecipient) -> dict:
    return {
        "id": recipient.id,
        "notification_fact_id": recipient.notification_fact_id,
        "recipient_account_id": recipient.recipient_account_id,
        "turn_id": recipient.turn_id,
        "delivery_state": recipient.delivery_state,
        "error_facts": json_value(recipient.error_facts),
        "created_at": recipient.created_at,
        "updated_at": recipient.updated_at,
    }


def _recipient(row: Mapping) -> NotificationRecipient:
    return NotificationRecipient(
        db_id(row["id"]),
        db_id(row["notification_fact_id"]),
        db_id(row["recipient_account_id"]),
        row["delivery_state"],
        dict(row["error_facts"]),
        row["created_at"],
        row["updated_at"],
        turn_id=db_id(row["turn_id"]) if row["turn_id"] is not None else None,
    )
