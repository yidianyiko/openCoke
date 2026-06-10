from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import db_id, json_value, many, one_or_none

from coke.turn.v2.contracts import PendingClarification


class PendingClarificationPort(Protocol):
    def open_for_conversation(
        self,
        conversation_id: str,
        *,
        now: datetime | None = None,
    ) -> PendingClarification | None: ...

    def save(
        self,
        conversation_id: str,
        pending: PendingClarification,
    ) -> PendingClarification: ...

    def consume(
        self,
        conversation_id: str,
        unresolved_action_fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> PendingClarification | None: ...

    def expire(self, now: datetime) -> tuple[PendingClarification, ...]: ...


class InMemoryPendingClarificationStore:
    def __init__(self) -> None:
        self._open: dict[str, PendingClarification] = {}
        self.consumed: list[tuple[str, PendingClarification]] = []
        self.expired: list[tuple[str, PendingClarification]] = []

    def open_for_conversation(
        self,
        conversation_id: str,
        *,
        now: datetime | None = None,
    ) -> PendingClarification | None:
        pending = self._open.get(conversation_id)
        if pending is None or pending.status != "open":
            return None
        if _is_expired(pending, now):
            return None
        return pending

    def save(
        self,
        conversation_id: str,
        pending: PendingClarification,
    ) -> PendingClarification:
        self._open[conversation_id] = pending
        return pending

    def consume(
        self,
        conversation_id: str,
        unresolved_action_fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> PendingClarification | None:
        pending = self.open_for_conversation(conversation_id, now=now)
        if pending is None:
            return None
        if pending.unresolved_action_fingerprint != unresolved_action_fingerprint:
            return None
        consumed = replace(pending, status="consumed")
        self._open.pop(conversation_id, None)
        self.consumed.append((conversation_id, consumed))
        return consumed

    def expire(self, now: datetime) -> tuple[PendingClarification, ...]:
        expired: list[PendingClarification] = []
        for conversation_id, pending in tuple(self._open.items()):
            if _is_expired(pending, now):
                expired.append(self._expire_conversation(conversation_id, pending))
        return tuple(expired)

    def _expire_conversation(
        self,
        conversation_id: str,
        pending: PendingClarification,
    ) -> PendingClarification:
        expired = replace(pending, status="expired")
        self._open.pop(conversation_id, None)
        self.expired.append((conversation_id, expired))
        return expired


class PostgresPendingClarificationRepository:
    def __init__(
        self,
        session: Session,
        *,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.session = session
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda _prefix: uuid4().hex)

    def open_for_conversation(
        self,
        conversation_id: str,
        *,
        now: datetime | None = None,
    ) -> PendingClarification | None:
        if not _is_db_uuid(conversation_id):
            return None
        row = one_or_none(
            self.session,
            schema.pending_clarification,
            schema.pending_clarification.c.conversation_id == db_id(conversation_id),
            schema.pending_clarification.c.status == "open",
        )
        if row is None:
            return None
        pending = _pending_clarification(row)
        if _is_expired(pending, now):
            return None
        return pending

    def save(
        self,
        conversation_id: str,
        pending: PendingClarification,
    ) -> PendingClarification:
        written_at = _aware_utc(self._now())
        if pending.status == "open":
            self.session.execute(
                schema.pending_clarification.update()
                .where(
                    schema.pending_clarification.c.conversation_id
                    == db_id(conversation_id),
                    schema.pending_clarification.c.status == "open",
                )
                .values(status="superseded", updated_at=written_at)
            )
        self.session.execute(
            schema.pending_clarification.insert().values(
                **_pending_clarification_values(
                    self._id_factory("pending_clarification"),
                    conversation_id,
                    pending,
                    written_at,
                )
            )
        )
        return pending

    def consume(
        self,
        conversation_id: str,
        unresolved_action_fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> PendingClarification | None:
        checked_at = _aware_utc(now or self._now())
        pending = self.open_for_conversation(conversation_id, now=checked_at)
        if pending is None:
            return None
        if pending.unresolved_action_fingerprint != unresolved_action_fingerprint:
            return None
        result = self.session.execute(
            schema.pending_clarification.update()
            .where(
                schema.pending_clarification.c.conversation_id == db_id(conversation_id),
                schema.pending_clarification.c.unresolved_action_fingerprint
                == unresolved_action_fingerprint,
                schema.pending_clarification.c.status == "open",
            )
            .values(
                status="consumed",
                consumed_at=checked_at,
                updated_at=checked_at,
            )
        )
        if not result.rowcount:
            return None
        return replace(pending, status="consumed")

    def expire(self, now: datetime) -> tuple[PendingClarification, ...]:
        checked_at = _aware_utc(now)
        rows = many(
            self.session,
            schema.pending_clarification,
            schema.pending_clarification.c.status == "open",
            schema.pending_clarification.c.expires_at <= checked_at,
            order_by=(
                schema.pending_clarification.c.created_at,
                schema.pending_clarification.c.id,
            ),
        )
        if not rows:
            return ()
        ids = [db_id(row["id"]) for row in rows]
        self.session.execute(
            schema.pending_clarification.update()
            .where(schema.pending_clarification.c.id.in_(ids))
            .values(status="expired", updated_at=checked_at)
        )
        return tuple(
            replace(_pending_clarification(row), status="expired") for row in rows
        )


def _is_expired(
    pending: PendingClarification,
    now: datetime | None,
) -> bool:
    if now is None:
        now = datetime.now(UTC)
    checked_at = _aware_utc(now)
    expires_at = _aware_utc(pending.expires_at)
    return expires_at <= checked_at


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _pending_clarification_values(
    pending_id: str,
    conversation_id: str,
    pending: PendingClarification,
    written_at: datetime,
) -> dict:
    return {
        "id": db_id(pending_id),
        "conversation_id": db_id(conversation_id),
        "unresolved_action_fingerprint": pending.unresolved_action_fingerprint,
        "candidates": json_value(pending.candidates),
        "source_input_from_seq": pending.source_input_window[0],
        "source_input_to_seq": pending.source_input_window[1],
        "expires_at": _aware_utc(pending.expires_at),
        "status": pending.status,
        "consumed_at": written_at if pending.status == "consumed" else None,
        "created_at": written_at,
        "updated_at": written_at,
    }


def _pending_clarification(row: Mapping) -> PendingClarification:
    return PendingClarification(
        unresolved_action_fingerprint=row["unresolved_action_fingerprint"],
        candidates=tuple(dict(candidate) for candidate in row["candidates"]),
        source_input_window=(
            int(row["source_input_from_seq"]),
            int(row["source_input_to_seq"]),
        ),
        expires_at=row["expires_at"],
        status=row["status"],
    )


def _is_db_uuid(value: str | None) -> bool:
    if value is None:
        return False
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
