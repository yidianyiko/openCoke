from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from coke.domains.conversation_runtime.models import OutboxRecord


class RedisStreamPort(Protocol):
    def publish_event(
        self,
        *,
        event_id: str,
        topic: str,
        idempotency_key: str,
        traceparent: str,
        payload: dict[str, Any],
    ) -> str: ...


class OutboxRepository(Protocol):
    def list_unprocessed_outbox(self, limit: int = 100) -> list[OutboxRecord]: ...

    def mark_outbox_published(
        self, event_id: str, published_at: datetime
    ) -> OutboxRecord: ...

    def mark_outbox_processed(
        self, event_id: str, processed_at: datetime
    ) -> OutboxRecord: ...


class OutboxRelay:
    def __init__(
        self,
        repository: OutboxRepository,
        redis_stream: RedisStreamPort,
        stream_name: str = "coke.work",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.redis_stream = redis_stream
        self.stream_name = stream_name
        self._now = now or (lambda: datetime.now(UTC))

    def publish_unprocessed(self, limit: int = 100) -> list[OutboxRecord]:
        published = []
        for record in self.repository.list_unprocessed_outbox(limit=limit):
            self.redis_stream.publish_event(
                event_id=record.id,
                topic=record.topic,
                idempotency_key=record.idempotency_key,
                traceparent=record.traceparent,
                payload=dict(record.payload),
            )
            published.append(
                self.repository.mark_outbox_published(record.id, self._now())
            )
        return published

    def ack_processed(self, event_id: str) -> OutboxRecord:
        return self.repository.mark_outbox_processed(event_id, self._now())
