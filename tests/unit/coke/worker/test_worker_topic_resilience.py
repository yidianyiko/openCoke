from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest

import coke.worker.__main__ as worker_main
from coke.infra.redis import RedisWorkStream
from coke.turn.context import TurnMode, TurnTrigger
from coke.worker.__main__ import (
    _drain_supervisor_completions,
    _handle_event,
    _require_interactive_runtime_factory,
    _recover_open_inbound_windows,
)
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
        self.interaction_agent = SimpleNamespace()
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
        self.fail_next = False

    def publish_reply(self, causal_id: str, payload: dict[str, Any]) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("redis_publish_failed")
        self.published.append((causal_id, payload))


class FakeRuntime:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.turn_runner = FakeTurnRunner()
        self.reply_pubsub = FakeReplyPubSub()
        self.work_stream = None
        self.repositories = SimpleNamespace(conversation_runtime=SimpleNamespace())
        self.interactive_runtime_factory = None


class FakeSupervisor:
    def __init__(self) -> None:
        self.submitted = []
        self.idle_submitted = []
        self.idle_accept = True
        self.completed = []
        self.failures = []

    async def submit(self, trigger):
        self.submitted.append(trigger)

    async def submit_if_idle(self, trigger):
        if not self.idle_accept:
            return False
        self.idle_submitted.append(trigger)
        return True

    async def drain_completed(self):
        completed = list(self.completed)
        self.completed.clear()
        return completed

    async def restore_completed(self, completed):
        self.completed = list(completed) + self.completed

    async def drain_failures(self):
        failures = list(self.failures)
        self.failures.clear()
        return failures


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


def test_inbound_event_submits_to_supervisor_and_acks_without_running_turn():
    redis = fakeredis.FakeRedis(decode_responses=True)
    stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
    stream.ensure_group()
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
    supervisor = FakeSupervisor()
    acked: list[str] = []
    consumer = _consumer(stream, acked)

    count = consumer.poll_once(
        lambda event: _handle_event(runtime, event, supervisor=supervisor)
    )

    assert count == 1
    assert acked == ["outbox_inbound_1"]
    assert runtime.session.commits == 1
    assert runtime.turn_runner.inbound_triggers == []
    assert [trigger.trigger_id for trigger in supervisor.submitted] == [
        "inbound:provider_message_1"
    ]
    assert redis.xpending("coke.work", "workers")["pending"] == 0


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


def test_recover_open_inbound_windows_submits_synthetic_inbound_turns():
    runtime = FakeRuntime()
    runtime.repositories = SimpleNamespace(
        conversation_runtime=SimpleNamespace(
            list_open_inbound_conversations=lambda: [
                SimpleNamespace(
                    id="conversation_1",
                    account_id="account_1",
                    latest_inbound_seq=3,
                )
            ]
        )
    )
    supervisor = FakeSupervisor()

    _recover_open_inbound_windows(runtime, supervisor)

    assert supervisor.submitted == [
        TurnTrigger(
            trigger_id="recover:conversation_1:3",
            trigger_type="InboundTurn",
            mode=TurnMode.INTERACTIVE,
            conversation_id="conversation_1",
            account_id="account_1",
            payload={"recovered_open_window": True},
        )
    ]


def test_drain_supervisor_completions_logs_task_failures(caplog):
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    supervisor.failures = [
        (
            TurnTrigger(
                trigger_id="inbound:provider_message_1",
                trigger_type="InboundTurn",
                mode=TurnMode.INTERACTIVE,
                conversation_id="conversation_1",
                account_id="account_1",
                payload={"causal_inbound_event_id": "provider_message_1"},
            ),
            RuntimeError("cleanup_failed"),
        )
    ]

    with caplog.at_level(logging.ERROR):
        _drain_supervisor_completions(runtime, supervisor)

    assert "interactive_turn_task_failed" in caplog.text
    assert "inbound:provider_message_1" in caplog.text
    assert runtime.reply_pubsub.published == []


def test_worker_requires_interactive_runtime_factory_for_supervised_turns():
    with pytest.raises(RuntimeError, match="interactive runtime factory"):
        _require_interactive_runtime_factory(
            SimpleNamespace(interactive_runtime_factory=None)
        )


def test_worker_validates_runtime_factory_before_starting_supervisor_loop(monkeypatch):
    class FakeWorkStream:
        def ensure_group(self) -> None:
            pass

    class RecordingSupervisorLoop:
        started = False
        stopped = False

        def start(self) -> None:
            RecordingSupervisorLoop.started = True

        def stop(self) -> None:
            RecordingSupervisorLoop.stopped = True

    runtime = FakeRuntime()
    runtime.work_stream = FakeWorkStream()
    settings = SimpleNamespace(
        work_stream_name="coke.work",
        work_group_name="workers",
        work_consumer_name="worker-1",
        worker_block_ms=1,
        worker_reclaim_idle_ms=1,
    )
    monkeypatch.setattr(worker_main, "_SupervisorLoop", RecordingSupervisorLoop)

    with pytest.raises(RuntimeError, match="interactive runtime factory"):
        worker_main.run_worker_loop(settings=settings, runtime=runtime, iterations=0)

    assert RecordingSupervisorLoop.started is False
    assert RecordingSupervisorLoop.stopped is False


def test_drain_supervisor_failures_resubmits_failed_turn_once(caplog):
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    trigger = TurnTrigger(
        trigger_id="inbound:provider_message_1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={
            "_worker_event_id": "outbox_inbound_1",
            "causal_inbound_event_id": "provider_message_1",
        },
    )
    supervisor.failures = [
        SimpleNamespace(
            trigger=trigger,
            error=RuntimeError("agent_failed"),
            source="turn_task",
        )
    ]

    with caplog.at_level(logging.ERROR):
        _drain_supervisor_completions(runtime, supervisor)

    assert supervisor.submitted == []
    assert [submitted.trigger_id for submitted in supervisor.idle_submitted] == [
        "inbound:provider_message_1"
    ]
    assert supervisor.idle_submitted[0].payload["_worker_retry_count"] == 1
    assert "interactive_turn_task_failed" in caplog.text


def test_drain_supervisor_failures_does_not_retry_over_active_turn():
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    supervisor.idle_accept = False
    trigger = TurnTrigger(
        trigger_id="inbound:provider_message_1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={
            "_worker_event_id": "outbox_inbound_1",
            "causal_inbound_event_id": "provider_message_1",
        },
    )
    supervisor.failures = [
        SimpleNamespace(
            trigger=trigger,
            error=RuntimeError("agent_failed"),
            source="turn_task",
        )
    ]

    _drain_supervisor_completions(runtime, supervisor)

    assert supervisor.submitted == []
    assert supervisor.idle_submitted == []


def test_drain_supervisor_failures_does_not_resubmit_provider_cancel_failure():
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    trigger = TurnTrigger(
        trigger_id="inbound:provider_message_1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={"causal_inbound_event_id": "provider_message_1"},
    )
    supervisor.failures = [
        SimpleNamespace(
            trigger=trigger,
            error=RuntimeError("cancel_failed"),
            source="provider_cancel",
        )
    ]

    _drain_supervisor_completions(runtime, supervisor)

    assert supervisor.submitted == []
    assert supervisor.idle_submitted == []


def test_worker_stops_supervisor_loop_when_recovery_fails(monkeypatch):
    class FakeWorkStream:
        def ensure_group(self) -> None:
            pass

    class RecordingSupervisorLoop:
        started = False
        stopped = False

        def start(self) -> None:
            RecordingSupervisorLoop.started = True

        def stop(self) -> None:
            RecordingSupervisorLoop.stopped = True

    runtime = FakeRuntime()
    runtime.work_stream = FakeWorkStream()
    runtime.interactive_runtime_factory = lambda: runtime
    settings = SimpleNamespace(
        work_stream_name="coke.work",
        work_group_name="workers",
        work_consumer_name="worker-1",
        worker_block_ms=1,
        worker_reclaim_idle_ms=1,
    )

    def fail_recovery(*_args, **_kwargs):
        raise RuntimeError("recovery_failed")

    monkeypatch.setattr(worker_main, "_SupervisorLoop", RecordingSupervisorLoop)
    monkeypatch.setattr(worker_main, "_recover_open_inbound_windows", fail_recovery)

    with pytest.raises(RuntimeError, match="recovery_failed"):
        worker_main.run_worker_loop(settings=settings, runtime=runtime, iterations=0)

    assert RecordingSupervisorLoop.started is True
    assert RecordingSupervisorLoop.stopped is True


def test_drain_supervisor_completions_requeues_when_reply_publish_fails():
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    trigger = TurnTrigger(
        trigger_id="inbound:provider_message_1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={
            "_worker_event_id": "outbox_inbound_1",
            "causal_inbound_event_id": "provider_message_1",
        },
    )
    result = SimpleNamespace(
        turn_id="turn_1",
        disposition="replied",
        reason_code="reply_ready",
        visible_text="ok",
    )
    supervisor.completed = [(trigger, result)]
    runtime.reply_pubsub.fail_next = True

    with pytest.raises(RuntimeError, match="redis_publish_failed"):
        _drain_supervisor_completions(runtime, supervisor)

    assert supervisor.completed == [(trigger, result)]
    assert runtime.reply_pubsub.published == []

    _drain_supervisor_completions(runtime, supervisor)

    assert supervisor.completed == []
    assert runtime.reply_pubsub.published == [
        (
            "provider_message_1",
            {
                "event_id": "outbox_inbound_1",
                "turn_id": "turn_1",
                "disposition": "replied",
                "reason_code": "reply_ready",
                "visible_text": "ok",
            },
        )
    ]


def test_drain_supervisor_completions_publishes_coalesced_reply_to_latest_waiter():
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    trigger = TurnTrigger(
        trigger_id="inbound:provider_message_1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={
            "_worker_event_id": "outbox_inbound_1",
            "causal_inbound_event_id": "provider_message_1",
        },
    )
    result = SimpleNamespace(
        turn_id="turn_1",
        disposition="replied",
        reason_code="reply_ready",
        visible_text="ok",
        latest_causal_inbound_event_id="provider_message_2",
        coalesced_causal_inbound_event_ids=("provider_message_1",),
    )
    supervisor.completed = [(trigger, result)]

    _drain_supervisor_completions(runtime, supervisor)

    assert runtime.reply_pubsub.published == [
        (
            "provider_message_1",
            {
                "event_id": "outbox_inbound_1",
                "turn_id": "turn_1",
                "disposition": "superseded",
                "reason_code": "coalesced_into_newer_inbound",
                "visible_text": None,
            },
        ),
        (
            "provider_message_2",
            {
                "event_id": "outbox_inbound_1",
                "turn_id": "turn_1",
                "disposition": "replied",
                "reason_code": "reply_ready",
                "visible_text": "ok",
            },
        ),
    ]


def test_drain_supervisor_completions_requeues_before_visible_when_coalesced_publish_fails():
    runtime = FakeRuntime()
    supervisor = FakeSupervisor()
    trigger = TurnTrigger(
        trigger_id="inbound:provider_message_1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={
            "_worker_event_id": "outbox_inbound_1",
            "causal_inbound_event_id": "provider_message_1",
        },
    )
    result = SimpleNamespace(
        turn_id="turn_1",
        disposition="replied",
        reason_code="reply_ready",
        visible_text="ok",
        latest_causal_inbound_event_id="provider_message_2",
        coalesced_causal_inbound_event_ids=("provider_message_1",),
    )
    supervisor.completed = [(trigger, result)]
    runtime.reply_pubsub.fail_next = True

    with pytest.raises(RuntimeError, match="redis_publish_failed"):
        _drain_supervisor_completions(runtime, supervisor)

    assert supervisor.completed == [(trigger, result)]
    assert runtime.reply_pubsub.published == []


def _consumer(stream: RedisWorkStream, acked: list[str]) -> StreamConsumer:
    return StreamConsumer(
        redis_stream=stream,
        stream_name="coke.work",
        group_name="workers",
        consumer_name="worker-1",
        ack_callback=lambda event_id: acked.append(event_id),
        block_ms=1,
    )
