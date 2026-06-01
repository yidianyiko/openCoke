from __future__ import annotations

import fakeredis

from coke.infra.redis import RedisReplyPubSub, RedisWorkStream
from coke.worker.stream_consumer import StreamConsumer

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def publish_inbound(stream: RedisWorkStream, event_id: str = "outbox_1") -> str:
    return stream.publish_event(
        event_id=event_id,
        topic="turn.inbound",
        idempotency_key=f"inbound:{event_id}",
        traceparent=TRACEPARENT,
        payload={"trigger_id": f"inbound:{event_id}"},
    )


def test_stream_produce_consume_and_ack_after_durable_success():
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    publish_inbound(stream)
    acked: list[str] = []
    handled: list[str] = []
    consumer = StreamConsumer(
        redis_stream=stream,
        stream_name="coke.work",
        group_name="workers",
        consumer_name="worker-1",
        ack_callback=lambda event_id: acked.append(event_id),
        block_ms=1,
    )

    count = consumer.poll_once(lambda event: handled.append(event.event_id))

    assert count == 1
    assert handled == ["outbox_1"]
    assert acked == ["outbox_1"]
    assert redis.xpending("coke.work", "workers")["pending"] == 0


def test_stream_pending_message_can_be_reclaimed_after_crashed_consumer():
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    publish_inbound(stream)
    crashed_read = redis.xreadgroup(
        "workers",
        "worker-1",
        {"coke.work": ">"},
        count=1,
        block=1,
    )
    acked: list[str] = []
    handled: list[str] = []
    consumer = StreamConsumer(
        redis_stream=stream,
        stream_name="coke.work",
        group_name="workers",
        consumer_name="worker-2",
        ack_callback=lambda event_id: acked.append(event_id),
        block_ms=1,
    )

    count = consumer.reclaim_pending_once(
        lambda event: handled.append(event.event_id),
        min_idle_ms=0,
    )

    assert crashed_read
    assert count == 1
    assert handled == ["outbox_1"]
    assert acked == ["outbox_1"]
    assert redis.xpending("coke.work", "workers")["pending"] == 0


def test_reply_pubsub_round_trips_by_causal_inbound_event_id():
    redis = fakeredis.FakeRedis(decode_responses=True)
    bus = RedisReplyPubSub(redis, channel_prefix="coke:reply")
    subscription = bus.subscribe("inbound-event-1")

    try:
        bus.publish_reply(
            "inbound-event-1",
            {
                "event_id": "outbox_1",
                "status": "completed",
                "segments": ["hello"],
            },
        )

        assert bus.get_reply(subscription, timeout_s=1.0) == {
            "event_id": "outbox_1",
            "status": "completed",
            "segments": ["hello"],
        }
    finally:
        subscription.close()
