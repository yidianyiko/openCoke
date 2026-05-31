from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import replace
from threading import Thread
from typing import Any

import sqlalchemy as sa

from coke import schema
from coke.composition import CokeRuntime, build_runtime_from_settings
from coke.config import Settings
from coke.domains._pg import db_id
from coke.turn.context import TurnMode, TurnTrigger
from coke.worker.interactive_supervisor import InteractiveTurnSupervisor
from coke.worker.outbox_relay import OutboxRelay
from coke.worker.stream_consumer import StreamConsumer, StreamEvent

LOGGER = logging.getLogger(__name__)

REMINDER_LIFECYCLE_TOPICS = frozenset({"reminder.lifecycle"})
RENDER_TURN_TOPICS = frozenset(
    {
        "turn.reminder_fire",
        "turn.nightly_summary",
        "turn.proactive_fire",
        "turn.notification",
        "turn.undelivered_resend",
    }
)
TURN_TOPICS = frozenset({"turn.inbound", *RENDER_TURN_TOPICS})
SUPERVISED_TURN_FAILURE_RETRY_LIMIT = 1


def run_worker_loop(
    settings: Settings | None = None,
    *,
    runtime: CokeRuntime | None = None,
    iterations: int | None = None,
) -> None:
    settings = settings or Settings.from_env()
    runtime = runtime or build_runtime_from_settings(settings)
    if runtime.work_stream is None or runtime.session is None:
        raise RuntimeError("runtime is missing worker stream or session")
    interactive_runtime_factory = _require_interactive_runtime_factory(runtime)
    relay = OutboxRelay(
        repository=runtime.repositories.conversation_runtime,
        redis_stream=runtime.work_stream,
        stream_name=settings.work_stream_name,
    )

    def _ack_processed(event_id: str):
        record = relay.ack_processed(event_id)
        runtime.session.commit()
        return record

    consumer = StreamConsumer(
        redis_stream=runtime.work_stream,
        stream_name=settings.work_stream_name,
        group_name=settings.work_group_name,
        consumer_name=settings.work_consumer_name,
        ack_callback=_ack_processed,
        block_ms=settings.worker_block_ms,
    )
    consumer.ensure_group()
    supervisor_loop = _SupervisorLoop()
    supervisor_loop.start()
    try:
        supervisor = InteractiveTurnSupervisor(
            turn_runner=runtime.turn_runner,
            interaction_agent=runtime.turn_runner.interaction_agent,
            runtime_factory=interactive_runtime_factory,
        )
        _recover_open_inbound_windows(
            runtime, supervisor, supervisor_loop=supervisor_loop
        )
        attempts = 0
        while iterations is None or attempts < iterations:
            try:
                count = consumer.reclaim_pending_once(
                    lambda event: _handle_event(
                        runtime,
                        event,
                        supervisor=supervisor,
                        supervisor_loop=supervisor_loop,
                    ),
                    min_idle_ms=settings.worker_reclaim_idle_ms,
                )
                if count == 0:
                    count = consumer.poll_once(
                        lambda event: _handle_event(
                            runtime,
                            event,
                            supervisor=supervisor,
                            supervisor_loop=supervisor_loop,
                        )
                    )
                _drain_supervisor_completions(
                    runtime, supervisor, supervisor_loop=supervisor_loop
                )
                attempts += 1
            except Exception:
                runtime.session.rollback()
                LOGGER.exception("worker loop iteration failed")
                time.sleep(1.0)
                attempts += 1
    finally:
        supervisor_loop.stop()


def _handle_event(
    runtime: CokeRuntime,
    event: StreamEvent,
    *,
    supervisor: Any | None = None,
    supervisor_loop: Any | None = None,
) -> None:
    if _handle_non_turn_event(event):
        return
    results: list[tuple[TurnTrigger, Any]] = []
    for trigger in _turn_triggers_from_event(runtime, event):
        if trigger.mode == TurnMode.INTERACTIVE and supervisor is not None:
            _submit_interactive_trigger(
                supervisor,
                _with_worker_event_id(trigger, event.event_id),
                supervisor_loop=supervisor_loop,
            )
            continue
        if trigger.mode == TurnMode.RENDER:
            result = runtime.turn_runner.run_render_turn(trigger)
        else:
            result = runtime.turn_runner.run_inbound_turn(trigger)
        results.append((trigger, result))
    runtime.session.commit()
    for trigger, result in results:
        _publish_reply(runtime, event_id=event.event_id, trigger=trigger, result=result)


def _recover_open_inbound_windows(
    runtime: CokeRuntime,
    supervisor: Any,
    *,
    supervisor_loop: Any | None = None,
) -> None:
    repository = runtime.repositories.conversation_runtime
    list_open = getattr(repository, "list_open_inbound_conversations", None)
    if not callable(list_open):
        return
    for conversation in list_open():
        trigger = TurnTrigger(
            trigger_id=(f"recover:{conversation.id}:{conversation.latest_inbound_seq}"),
            trigger_type="InboundTurn",
            mode=TurnMode.INTERACTIVE,
            conversation_id=conversation.id,
            account_id=conversation.account_id,
            payload={"recovered_open_window": True},
        )
        _submit_interactive_trigger(
            supervisor,
            trigger,
            supervisor_loop=supervisor_loop,
        )


def _drain_supervisor_completions(
    runtime: CokeRuntime,
    supervisor: Any,
    *,
    supervisor_loop: Any | None = None,
) -> None:
    completed = _run_supervisor_coroutine(
        supervisor.drain_completed(),
        supervisor_loop=supervisor_loop,
    )
    _drain_supervisor_failures(supervisor, supervisor_loop=supervisor_loop)
    if not completed:
        return
    remaining = list(completed)
    try:
        if runtime.session is not None:
            runtime.session.commit()
        for trigger, result in completed:
            _publish_reply(
                runtime,
                event_id=str(
                    trigger.payload.get("_worker_event_id") or trigger.trigger_id
                ),
                trigger=trigger,
                result=result,
            )
            remaining.pop(0)
    except Exception:
        _restore_supervisor_completions(
            supervisor,
            remaining,
            supervisor_loop=supervisor_loop,
        )
        raise


def _restore_supervisor_completions(
    supervisor: Any,
    completed: list[tuple[TurnTrigger, Any]],
    *,
    supervisor_loop: Any | None = None,
) -> None:
    restore_completed = getattr(supervisor, "restore_completed", None)
    if not completed or not callable(restore_completed):
        return
    _run_supervisor_coroutine(
        restore_completed(completed),
        supervisor_loop=supervisor_loop,
    )


def _drain_supervisor_failures(
    supervisor: Any,
    *,
    supervisor_loop: Any | None = None,
) -> None:
    drain_failures = getattr(supervisor, "drain_failures", None)
    if not callable(drain_failures):
        return
    failures = _run_supervisor_coroutine(
        drain_failures(),
        supervisor_loop=supervisor_loop,
    )
    for failure in failures:
        trigger, error, source = _supervisor_failure_parts(failure)
        trigger_id = getattr(trigger, "trigger_id", None)
        conversation_id = getattr(trigger, "conversation_id", None)
        LOGGER.error(
            "interactive_turn_task_failed trigger_id=%s conversation_id=%s",
            trigger_id,
            conversation_id,
            extra={
                "trigger_id": trigger_id,
                "conversation_id": conversation_id,
            },
            exc_info=(type(error), error, error.__traceback__),
        )
        retry_trigger = _retry_trigger_for_supervisor_failure(trigger, source)
        if retry_trigger is not None:
            _submit_interactive_trigger_if_idle(
                supervisor,
                retry_trigger,
                supervisor_loop=supervisor_loop,
            )


def _supervisor_failure_parts(failure: Any) -> tuple[Any | None, Exception, str]:
    trigger = getattr(failure, "trigger", None)
    error = getattr(failure, "error", None)
    source = str(getattr(failure, "source", "unknown"))
    if isinstance(error, Exception):
        return trigger, error, source
    if isinstance(failure, tuple) and len(failure) >= 2:
        trigger = failure[0]
        error = failure[1]
        source = str(failure[2]) if len(failure) >= 3 else "unknown"
        if isinstance(error, Exception):
            return trigger, error, source
    raise TypeError("invalid supervisor failure")


def _retry_trigger_for_supervisor_failure(
    trigger: TurnTrigger | None,
    source: str,
) -> TurnTrigger | None:
    if source != "turn_task" or trigger is None or trigger.mode != TurnMode.INTERACTIVE:
        return None
    retry_count = _worker_retry_count(trigger.payload)
    if retry_count >= SUPERVISED_TURN_FAILURE_RETRY_LIMIT:
        return None
    payload = dict(trigger.payload)
    payload["_worker_retry_count"] = retry_count + 1
    return replace(trigger, payload=payload)


def _submit_interactive_trigger_if_idle(
    supervisor: Any,
    trigger: TurnTrigger,
    *,
    supervisor_loop: Any | None = None,
) -> bool:
    submit_if_idle = getattr(supervisor, "submit_if_idle", None)
    if not callable(submit_if_idle):
        return False
    return bool(
        _run_supervisor_coroutine(
            submit_if_idle(trigger), supervisor_loop=supervisor_loop
        )
    )


def _worker_retry_count(payload: Mapping[str, Any]) -> int:
    raw = payload.get("_worker_retry_count", 0)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _publish_reply(
    runtime: CokeRuntime,
    *,
    event_id: str,
    trigger: TurnTrigger,
    result: Any,
) -> None:
    if runtime.reply_pubsub is None:
        return
    causal_id = trigger.payload.get("causal_inbound_event_id")
    if not isinstance(causal_id, str) or not causal_id:
        return
    runtime.reply_pubsub.publish_reply(
        causal_id,
        {
            "event_id": event_id,
            "turn_id": result.turn_id,
            "disposition": result.disposition,
            "reason_code": result.reason_code,
            "visible_text": result.visible_text,
        },
    )


def _submit_interactive_trigger(
    supervisor: Any,
    trigger: TurnTrigger,
    *,
    supervisor_loop: Any | None = None,
) -> None:
    _run_supervisor_coroutine(
        supervisor.submit(trigger),
        supervisor_loop=supervisor_loop,
    )


def _run_supervisor_coroutine(coro: Any, *, supervisor_loop: Any | None = None) -> Any:
    if supervisor_loop is not None:
        return supervisor_loop.run(coro)
    return asyncio.run(coro)


def _with_worker_event_id(trigger: TurnTrigger, event_id: str) -> TurnTrigger:
    payload = dict(trigger.payload)
    payload["_worker_event_id"] = event_id
    return replace(trigger, payload=payload)


def _require_interactive_runtime_factory(runtime: CokeRuntime) -> Any:
    factory = runtime.interactive_runtime_factory
    if factory is None:
        raise RuntimeError("runtime is missing interactive runtime factory")
    return factory


class _SupervisorLoop:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self._run, name="coke-interactive-turns")

    def start(self) -> None:
        self.thread.start()

    def run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(
            self._cancel_pending_tasks(), self.loop
        ).result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5.0)
        self.loop.close()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _cancel_pending_tasks(self) -> None:
        current = asyncio.current_task()
        tasks = [
            task
            for task in asyncio.all_tasks(self.loop)
            if task is not current and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _handle_non_turn_event(event: StreamEvent) -> bool:
    payload = dict(event.payload)
    if event.topic in REMINDER_LIFECYCLE_TOPICS:
        LOGGER.info(
            "reminder_lifecycle_event_acked_as_evidence",
            extra={
                "event_id": event.event_id,
                "topic": event.topic,
                "operation": payload.get("operation"),
                "reminder_id": payload.get("reminder_id"),
            },
        )
        return True
    if event.topic not in TURN_TOPICS:
        LOGGER.warning(
            "unknown_worker_topic_skipped",
            extra={"event_id": event.event_id, "topic": event.topic},
        )
        return True
    return False


def _turn_trigger_from_event(runtime: CokeRuntime, event: StreamEvent) -> TurnTrigger:
    return _turn_triggers_from_event(runtime, event)[0]


def _turn_triggers_from_event(
    runtime: CokeRuntime, event: StreamEvent
) -> list[TurnTrigger]:
    topic = event.topic
    payload = dict(event.payload)
    if topic == "turn.inbound":
        return [_inbound_trigger(runtime, payload)]
    if topic in RENDER_TURN_TOPICS:
        return [
            _render_trigger(runtime, topic, render_payload)
            for render_payload in _render_payloads(runtime, topic, payload)
        ]
    raise RuntimeError(f"unsupported_worker_topic:{topic}")


def _inbound_trigger(runtime: CokeRuntime, payload: Mapping[str, Any]) -> TurnTrigger:
    conversation_id = _required_str(payload, "conversation_id")
    message_id = _required_str(payload, "message_id")
    message = _message_row(runtime, message_id)
    conversation = _conversation_row(runtime, conversation_id)
    return TurnTrigger(
        trigger_id=_required_str(payload, "trigger_id"),
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=conversation_id,
        account_id=db_id(conversation["account_id"]),
        channel_identity_id=(
            db_id(message["channel_identity_id"])
            if message.get("channel_identity_id") is not None
            else None
        ),
        payload={
            "message_id": message_id,
            "text": message.get("text"),
            "payload": dict(message.get("payload") or {}),
            "causal_inbound_event_id": message.get("causal_inbound_event_id"),
        },
    )


def _render_trigger(
    runtime: CokeRuntime,
    topic: str,
    payload: Mapping[str, Any],
) -> TurnTrigger:
    trigger_payload = dict(payload)
    if topic == "turn.notification":
        trigger_payload = _hydrate_notification_payload(runtime, trigger_payload)
    if topic == "turn.undelivered_resend":
        trigger_payload = _hydrate_undelivered_resend_payload(runtime, trigger_payload)
    account_id = _required_str(payload, "account_id")
    conversation_id = str(trigger_payload.get("conversation_id") or "")
    if not conversation_id:
        conversation = (
            runtime.repositories.conversation_runtime.get_conversation_by_account(
                account_id
            )
        )
        if conversation is None:
            raise RuntimeError(f"conversation_not_found_for_account:{account_id}")
        conversation_id = conversation.id
    trigger_type = {
        "turn.reminder_fire": "ReminderFireTurn",
        "turn.nightly_summary": "NightlySummaryTurn",
        "turn.proactive_fire": "ProactiveFireTurn",
        "turn.notification": "NotificationTurn",
        "turn.undelivered_resend": "UndeliveredResendTurn",
    }[topic]
    return TurnTrigger(
        trigger_id=_required_str(payload, "trigger_id"),
        trigger_type=trigger_type,
        mode=TurnMode.RENDER,
        conversation_id=conversation_id,
        account_id=account_id,
        payload=trigger_payload,
    )


def _render_payloads(
    runtime: CokeRuntime,
    topic: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    trigger_payload = dict(payload)
    if topic != "turn.notification":
        return [trigger_payload]

    trigger_payload = _hydrate_notification_payload(runtime, trigger_payload)
    recipient_ids = _unique_strings(trigger_payload.get("recipient_account_ids"))
    if len(recipient_ids) <= 1:
        return [trigger_payload]

    base_trigger_id = _required_str(trigger_payload, "trigger_id")
    payloads: list[dict[str, Any]] = []
    for recipient_id in recipient_ids:
        recipient_payload = dict(trigger_payload)
        recipient_payload["account_id"] = recipient_id
        recipient_payload["recipient_account_ids"] = [recipient_id]
        recipient_payload["trigger_id"] = f"{base_trigger_id}:{recipient_id}"
        recipient_payload.pop("conversation_id", None)
        payloads.append(recipient_payload)
    return payloads


def _hydrate_notification_payload(
    runtime: CokeRuntime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    fact_id = payload.get("notification_fact_id")
    if not isinstance(fact_id, str) or not fact_id:
        return payload
    repository = getattr(runtime.repositories, "social_scheduling", None)
    if repository is None or not hasattr(repository, "list_notification_facts"):
        return payload
    for fact in repository.list_notification_facts():
        if getattr(fact, "id", None) != fact_id:
            continue
        expected_hash = payload.get("facts_hash")
        if (
            isinstance(expected_hash, str)
            and expected_hash
            and getattr(fact, "facts_hash", None) != expected_hash
        ):
            return payload
        hydrated = dict(payload)
        hydrated["notification_fact"] = _notification_fact_payload(fact)
        return hydrated
    return payload


def _hydrate_undelivered_resend_payload(
    runtime: CokeRuntime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    fact_ids = [
        fact_id
        for fact_id in payload.get("notification_fact_ids", [])
        if isinstance(fact_id, str) and fact_id
    ]
    if not fact_ids:
        return payload
    repository = getattr(runtime.repositories, "social_scheduling", None)
    if repository is None or not hasattr(repository, "list_notification_facts"):
        return payload
    facts_by_id = {fact.id: fact for fact in repository.list_notification_facts()}
    hydrated = dict(payload)
    hydrated["notification_facts"] = [
        _notification_fact_payload(facts_by_id[fact_id])
        for fact_id in fact_ids
        if fact_id in facts_by_id
    ]
    return hydrated


def _notification_fact_payload(fact: Any) -> dict[str, Any]:
    return {
        "id": getattr(fact, "id", None),
        "type": getattr(fact, "type", None),
        "actor_account_id": getattr(fact, "actor_account_id", None),
        "object_type": getattr(fact, "object_type", None),
        "object_id": getattr(fact, "object_id", None),
        "status": getattr(fact, "status", None),
        "facts": dict(getattr(fact, "facts", {}) or {}),
        "facts_hash": getattr(fact, "facts_hash", None),
    }


def _unique_strings(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item))


def _conversation_row(runtime: CokeRuntime, conversation_id: str) -> Mapping[str, Any]:
    row = (
        runtime.session.execute(
            sa.select(schema.conversation).where(
                schema.conversation.c.id == conversation_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(f"conversation_not_found:{conversation_id}")
    return dict(row)


def _message_row(runtime: CokeRuntime, message_id: str) -> Mapping[str, Any]:
    row = (
        runtime.session.execute(
            sa.select(schema.message).where(schema.message.c.id == message_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(f"message_not_found:{message_id}")
    return dict(row)


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{key}_required")
    return value


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker_loop()


if __name__ == "__main__":
    main()
