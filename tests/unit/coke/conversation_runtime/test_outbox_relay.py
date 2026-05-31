from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import fakeredis

from coke.config import Settings
from coke.domains.conversation_runtime.models import OutboxRecord
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.infra.redis import RedisWorkStream
from coke.worker.outbox_relay import OutboxRelay, run_outbox_relay_loop
from coke.worker.stream_consumer import StreamConsumer

NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
PAST = datetime(2026, 5, 29, 11, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def outbox_record(event_id: str = "outbox_1") -> OutboxRecord:
    return OutboxRecord(
        id=event_id,
        topic="turn.inbound",
        idempotency_key=f"inbound:{event_id}",
        payload={"trigger_id": f"inbound:{event_id}"},
        traceparent=TRACEPARENT,
        status="pending",
        created_at=NOW,
        published_at=None,
        processed_at=None,
        acked_at=None,
        retry_count=0,
        last_error=None,
    )


def test_outbox_relay_publishes_unprocessed_rows_without_processing_until_ack():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    repository.add_outbox(outbox_record())
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    relay = OutboxRelay(
        repository=repository,
        redis_stream=stream,
        stream_name="coke.work",
        now=lambda: NOW,
    )

    published = relay.publish_unprocessed()
    after_publish = repository.outbox_by_id["outbox_1"]
    acked = relay.ack_processed("outbox_1")

    assert [event.id for event in published] == ["outbox_1"]
    assert redis.xlen("coke.work") == 1
    assert after_publish.status == "published"
    assert after_publish.published_at == NOW
    assert after_publish.processed_at is None
    assert after_publish.acked_at is None
    assert acked.status == "processed"
    assert acked.processed_at == NOW
    assert acked.acked_at == NOW


def test_outbox_relay_replays_unacked_rows_with_same_event_id_for_idempotent_dedup():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    repository.add_outbox(outbox_record())
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    relay = OutboxRelay(
        repository=repository,
        redis_stream=stream,
        stream_name="coke.work",
        now=lambda: NOW,
    )

    relay.publish_unprocessed()
    relay.publish_unprocessed()

    assert redis.xlen("coke.work") == 1
    assert repository.outbox_by_id["outbox_1"].processed_at is None


def test_stream_consumer_handles_event_and_acks_durable_outbox_row():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    repository.add_outbox(outbox_record())
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    relay = OutboxRelay(
        repository=repository,
        redis_stream=stream,
        stream_name="coke.work",
        now=lambda: NOW,
    )
    relay.publish_unprocessed()
    handled: list[str] = []
    consumer = StreamConsumer(
        redis_stream=stream,
        stream_name="coke.work",
        group_name="workers",
        consumer_name="worker-1",
        ack_callback=relay.ack_processed,
    )

    consumer.poll_once(lambda event: handled.append(event.event_id))

    assert handled == ["outbox_1"]
    assert repository.outbox_by_id["outbox_1"].status == "processed"
    assert redis.xpending("coke.work", "workers")["pending"] == 0


def test_outbox_relay_loop_dispatches_due_waiting_reply_before_sleep():
    repository = InMemoryConversationRuntimeRepository(now=lambda: PAST)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: PAST,
        id_factory=_id_factory(),
    )
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_1",
        causal_inbound_event_id="provider:message-1",
        text="how many reminders?",
        payload={"context_token": "ctx_1"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    ).turn
    delivery = _RecordingDelivery()
    runtime = SimpleNamespace(
        repositories=SimpleNamespace(conversation_runtime=repository),
        conversation_runtime_service=service,
        turn_runner=SimpleNamespace(outbound_delivery=delivery),
        work_stream=RedisWorkStream(
            fakeredis.FakeRedis(decode_responses=True),
            stream_name="coke.work",
            group_name="workers",
        ),
        session=_RecordingSession(),
    )

    run_outbox_relay_loop(
        Settings(
            database_url="postgresql://unused",
            redis_url="redis://unused",
            app_env="test",
            outbox_relay_poll_interval_s=0,
            waiting_reply_after_seconds=20,
        ),
        runtime=runtime,
        iterations=1,
    )

    assert service.get_disposition(turn.id).disposition == "pending_async_reply"
    assert delivery.requests[0].message_type == "waiting"
    assert runtime.session.commits == 1


def _id_factory():
    counter = 0

    def next_id(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}_{counter}"

    return next_id


class _RecordingDelivery:
    def __init__(self) -> None:
        self.requests = []

    def deliver(self, request):
        self.requests.append(request)


class _RecordingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1
