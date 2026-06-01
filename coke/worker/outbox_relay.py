from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from coke.composition import CokeRuntime, build_runtime_from_settings
from coke.config import Settings
from coke.domains.conversation_runtime.models import OutboxRecord
from coke.worker.waiting_reply import WaitingReplyDispatcher

LOGGER = logging.getLogger(__name__)


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


def run_outbox_relay_loop(
    settings: Settings | None = None,
    *,
    runtime: CokeRuntime | None = None,
    iterations: int | None = None,
    limit: int = 100,
) -> None:
    settings = settings or Settings.from_env()
    runtime = runtime or build_runtime_from_settings(settings)
    if runtime.work_stream is None or runtime.session is None:
        raise RuntimeError("runtime is missing outbox relay stream or session")
    runtime.work_stream.ensure_group()
    relay = OutboxRelay(
        repository=runtime.repositories.conversation_runtime,
        redis_stream=runtime.work_stream,
        stream_name=settings.work_stream_name,
    )
    waiting_dispatcher = WaitingReplyDispatcher(
        conversation_runtime=runtime.conversation_runtime_service,
        outbound_delivery=runtime.turn_runner.outbound_delivery,
        delay_seconds=settings.waiting_reply_after_seconds,
    )
    handled = 0
    while iterations is None or handled < iterations:
        try:
            waiting_dispatcher.dispatch_due(limit=limit)
            published = relay.publish_unprocessed(limit=limit)
            runtime.session.commit()
            handled += 1
            if not published:
                time.sleep(settings.outbox_relay_poll_interval_s)
        except Exception:
            runtime.session.rollback()
            LOGGER.exception("outbox relay iteration failed")
            time.sleep(settings.outbox_relay_poll_interval_s)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_outbox_relay_loop()


if __name__ == "__main__":
    main()
