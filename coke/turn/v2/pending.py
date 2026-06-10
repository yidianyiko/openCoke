from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

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
