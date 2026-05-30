from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from hashlib import sha256
import json

from coke.domains.social_scheduling.models import (
    NotificationDeliveryState,
    NotificationFact,
    NotificationRecipient,
    SocialSchedulingError,
)
from coke.domains.social_scheduling.repository import SocialSchedulingRepository

PROSE_KEYS = {"text", "payload", "payload_text", "prose", "message"}


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def assert_structured_facts(facts: dict) -> None:
    disallowed = PROSE_KEYS & set(facts)
    if disallowed:
        raise SocialSchedulingError(
            "notification_fact_contains_prose",
            fact={
                "type": "notification_fact_contains_prose",
                "keys": sorted(disallowed),
            },
        )


class NotificationFactWriter:
    def __init__(
        self,
        repository: SocialSchedulingRepository,
        now: Callable[[], datetime],
        id_factory: Callable[[str], str],
    ) -> None:
        self.repository = repository
        self._now = now
        self._id_factory = id_factory

    def create_fact(
        self,
        *,
        notification_type: str,
        actor_account_id: str | None,
        object_type: str,
        object_id: str,
        status: str,
        facts: dict,
        recipients: Iterable[str],
        idempotency_key: str,
    ) -> NotificationFact:
        assert_structured_facts(facts)
        canonical_facts = {
            "type": notification_type,
            "actor_account_id": actor_account_id,
            "object_type": object_type,
            "object_id": object_id,
            "status": status,
            "facts": facts,
        }
        fact = NotificationFact(
            id=self._id_factory("notification_fact"),
            type=notification_type,
            actor_account_id=actor_account_id,
            object_type=object_type,
            object_id=object_id,
            status=status,
            facts=dict(facts),
            facts_hash=canonical_hash(canonical_facts),
            idempotency_key=idempotency_key,
            outbox_id=self._id_factory("outbox"),
            created_at=self._now(),
        )
        self.repository.add_notification_fact(fact)
        for account_id in sorted(set(recipients)):
            self.repository.add_notification_recipient(
                NotificationRecipient(
                    id=self._id_factory("notification_recipient"),
                    notification_fact_id=fact.id,
                    recipient_account_id=account_id,
                    delivery_state="pending",
                    error_facts={},
                    created_at=self._now(),
                    updated_at=self._now(),
                    turn_id=None,
                )
            )
        return fact

    def record_delivery(
        self,
        *,
        notification_fact_id: str,
        recipient_account_id: str,
        delivery_state: NotificationDeliveryState,
        error_facts: dict,
        turn_id: str | None = None,
    ) -> NotificationRecipient:
        _validate_error_facts(error_facts)
        recipient = self.repository.get_notification_recipient(
            notification_fact_id, recipient_account_id
        )
        if recipient is None:
            raise SocialSchedulingError(
                "notification_recipient_not_found",
                fact={
                    "type": "notification_recipient_not_found",
                    "notification_fact_id": notification_fact_id,
                    "recipient_account_id": recipient_account_id,
                },
            )
        updated = NotificationRecipient(
            id=recipient.id,
            notification_fact_id=recipient.notification_fact_id,
            recipient_account_id=recipient.recipient_account_id,
            delivery_state=delivery_state,
            error_facts=dict(error_facts),
            created_at=recipient.created_at,
            updated_at=self._now(),
            turn_id=turn_id if turn_id is not None else recipient.turn_id,
        )
        self.repository.save_notification_recipient(updated)
        return updated


def _validate_error_facts(error_facts: dict) -> None:
    lowered = json.dumps(error_facts, sort_keys=True).lower()
    forbidden_fragments = ("raw", "internal", "queue", "attempt", "error_code")
    if any(fragment in lowered for fragment in forbidden_fragments):
        raise SocialSchedulingError(
            "unsafe_notification_error_facts",
            fact={"type": "unsafe_notification_error_facts"},
        )
