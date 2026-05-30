from __future__ import annotations

from datetime import UTC, datetime

from coke.domains.conversation_runtime.models import OutboxRecord
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.worker.outbox_relay import OutboxRelay
from coke.worker.stream_consumer import StreamConsumer


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class RecordingStream:
    def __init__(self) -> None:
        self.messages_by_event_id: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []

    def xadd(self, stream_name: str, fields: dict):
        self.calls.append((stream_name, fields))
        self.messages_by_event_id.setdefault(fields["event_id"], fields)
        return f"{len(self.calls)}-0"

    def xreadgroup(self, groupname, consumername, streams, count=1, block=1000):
        return [
            (
                "coke.work",
                [
                    (
                        f"{index}-0",
                        fields,
                    )
                    for index, fields in enumerate(
                        self.messages_by_event_id.values(), start=1
                    )
                ],
            )
        ]

    def xack(self, stream_name, group_name, message_id):
        return 1


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
    stream = RecordingStream()
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
    assert stream.calls == [
        (
            "coke.work",
            {
                "event_id": "outbox_1",
                "topic": "turn.inbound",
                "idempotency_key": "inbound:outbox_1",
                "traceparent": TRACEPARENT,
                "payload": {"trigger_id": "inbound:outbox_1"},
            },
        )
    ]
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
    stream = RecordingStream()
    relay = OutboxRelay(
        repository=repository,
        redis_stream=stream,
        stream_name="coke.work",
        now=lambda: NOW,
    )

    relay.publish_unprocessed()
    relay.publish_unprocessed()

    assert len(stream.calls) == 2
    assert [fields["event_id"] for _stream, fields in stream.calls] == [
        "outbox_1",
        "outbox_1",
    ]
    assert list(stream.messages_by_event_id) == ["outbox_1"]
    assert repository.outbox_by_id["outbox_1"].processed_at is None


def test_stream_consumer_handles_each_event_id_once_and_acks_durable_row():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    repository.add_outbox(outbox_record())
    stream = RecordingStream()
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
    consumer.poll_once(lambda event: handled.append(event.event_id))

    assert handled == ["outbox_1"]
    assert repository.outbox_by_id["outbox_1"].status == "processed"
