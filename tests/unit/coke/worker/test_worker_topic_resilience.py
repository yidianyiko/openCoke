from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import fakeredis

from coke.infra.redis import RedisWorkStream
from coke.worker.__main__ import _handle_event
from coke.worker.stream_consumer import StreamConsumer

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def execute(self, statement):
        sql = str(statement)
        if "FROM conversation" in sql:
            return FakeResult({"id": "conversation_1", "account_id": "account_1"})
        if "FROM message" in sql:
            return FakeResult(
                {
                    "id": "message_1",
                    "channel_identity_id": "channel_identity_1",
                    "text": "hello",
                    "payload": {"provider": "wechat_personal"},
                    "causal_inbound_event_id": "provider_message_1",
                }
            )
        return FakeResult(None)

    def commit(self) -> None:
        self.commits += 1


class FakeTurnRunner:
    def __init__(self) -> None:
        self.inbound_triggers = []
        self.render_triggers = []
        self.next_inbound_result = SimpleNamespace(
            turn_id="turn_inbound_1",
            disposition="replied",
            reason_code=None,
            visible_text="ok",
        )

    def run_inbound_turn(self, trigger):
        self.inbound_triggers.append(trigger)
        return self.next_inbound_result

    def run_render_turn(self, trigger):
        self.render_triggers.append(trigger)
        return SimpleNamespace(
            turn_id="turn_render_1",
            disposition="replied",
            reason_code=None,
            visible_text="rendered",
        )


class FakeReplyPubSub:
    def __init__(self) -> None:
        self.published = []

    def publish_reply(self, causal_id: str, payload: dict[str, Any]) -> None:
        self.published.append((causal_id, payload))


class FakeRuntime:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.turn_runner = FakeTurnRunner()
        self.reply_pubsub = FakeReplyPubSub()


def test_reminder_lifecycle_event_is_acked_as_evidence_without_turn_or_reply(caplog):
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    stream.publish_event(
        event_id="outbox_lifecycle_1",
        topic="reminder.lifecycle",
        idempotency_key="reminder:update:turn_1:1",
        traceparent=TRACEPARENT,
        payload={
            "type": "reminder_lifecycle",
            "operation": "update",
            "reminder_id": "reminder_1",
            "owner_account_id": "account_1",
        },
    )
    runtime = FakeRuntime()
    acked: list[str] = []
    consumer = _consumer(stream, acked)

    with caplog.at_level(logging.INFO):
        count = consumer.poll_once(lambda event: _handle_event(runtime, event))

    assert count == 1
    assert acked == ["outbox_lifecycle_1"]
    assert redis.xpending("coke.work", "workers")["pending"] == 0
    assert runtime.turn_runner.inbound_triggers == []
    assert runtime.turn_runner.render_triggers == []
    assert runtime.reply_pubsub.published == []
    assert "reminder_lifecycle_event_acked_as_evidence" in caplog.text


def test_unknown_topic_is_warned_acked_and_following_inbound_still_processes(caplog):
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    stream.publish_event(
        event_id="outbox_unknown_1",
        topic="unexpected.topic",
        idempotency_key="unknown:1",
        traceparent=TRACEPARENT,
        payload={"type": "future_topic"},
    )
    stream.publish_event(
        event_id="outbox_inbound_1",
        topic="turn.inbound",
        idempotency_key="inbound:1",
        traceparent=TRACEPARENT,
        payload={
            "trigger_id": "inbound:provider_message_1",
            "conversation_id": "conversation_1",
            "message_id": "message_1",
        },
    )
    runtime = FakeRuntime()
    acked: list[str] = []
    consumer = _consumer(stream, acked)

    with caplog.at_level(logging.WARNING):
        first_count = consumer.poll_once(lambda event: _handle_event(runtime, event))
        second_count = consumer.poll_once(lambda event: _handle_event(runtime, event))

    assert first_count == 1
    assert second_count == 1
    assert acked == ["outbox_unknown_1", "outbox_inbound_1"]
    assert redis.xpending("coke.work", "workers")["pending"] == 0
    assert len(runtime.turn_runner.inbound_triggers) == 1
    assert runtime.turn_runner.inbound_triggers[0].trigger_type == "InboundTurn"
    assert "unknown_worker_topic_skipped" in caplog.text


def test_covered_inbound_event_publishes_terminal_no_visible_result_and_acks():
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
    stream.publish_event(
        event_id="outbox_inbound_covered",
        topic="turn.inbound",
        idempotency_key="inbound:covered",
        traceparent=TRACEPARENT,
        payload={
            "trigger_id": "inbound:provider_message_1:covered",
            "conversation_id": "conversation_1",
            "message_id": "message_1",
        },
    )
    runtime = FakeRuntime()
    runtime.turn_runner.next_inbound_result = SimpleNamespace(
        turn_id="inbound:provider_message_1:covered",
        disposition="superseded",
        reason_code="input_window_already_closed",
        visible_text=None,
    )
    acked: list[str] = []
    consumer = _consumer(stream, acked)

    count = consumer.poll_once(lambda event: _handle_event(runtime, event))

    assert count == 1
    assert acked == ["outbox_inbound_covered"]
    assert runtime.session.commits == 1
    assert runtime.reply_pubsub.published == [
        (
            "provider_message_1",
            {
                "event_id": "outbox_inbound_covered",
                "turn_id": "inbound:provider_message_1:covered",
                "disposition": "superseded",
                "reason_code": "input_window_already_closed",
                "visible_text": None,
            },
        )
    ]


def _consumer(stream: RedisWorkStream, acked: list[str]) -> StreamConsumer:
    return StreamConsumer(
        redis_stream=stream,
        stream_name="coke.work",
        group_name="workers",
        consumer_name="worker-1",
        ack_callback=lambda event_id: acked.append(event_id),
        block_ms=1,
    )
