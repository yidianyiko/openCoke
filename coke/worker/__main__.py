from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa

from coke import schema
from coke.composition import CokeRuntime, build_runtime_from_settings
from coke.config import Settings
from coke.domains._pg import db_id
from coke.turn.context import TurnMode, TurnTrigger
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
    attempts = 0
    while iterations is None or attempts < iterations:
        try:
            count = consumer.reclaim_pending_once(
                lambda event: _handle_event(runtime, event),
                min_idle_ms=settings.worker_reclaim_idle_ms,
            )
            if count == 0:
                count = consumer.poll_once(lambda event: _handle_event(runtime, event))
            attempts += 1
        except Exception:
            runtime.session.rollback()
            LOGGER.exception("worker loop iteration failed")
            time.sleep(1.0)
            attempts += 1


def _handle_event(runtime: CokeRuntime, event: StreamEvent) -> None:
    if _handle_non_turn_event(event):
        return
    trigger = _turn_trigger_from_event(runtime, event)
    if trigger.mode == TurnMode.RENDER:
        result = runtime.turn_runner.run_render_turn(trigger)
    else:
        result = runtime.turn_runner.run_inbound_turn(trigger)
    runtime.session.commit()
    if runtime.reply_pubsub is not None:
        causal_id = trigger.payload.get("causal_inbound_event_id")
        if isinstance(causal_id, str) and causal_id:
            runtime.reply_pubsub.publish_reply(
                causal_id,
                {
                    "event_id": event.event_id,
                    "turn_id": result.turn_id,
                    "disposition": result.disposition,
                    "reason_code": result.reason_code,
                    "visible_text": result.visible_text,
                },
            )


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
    topic = event.topic
    payload = dict(event.payload)
    if topic == "turn.inbound":
        return _inbound_trigger(runtime, payload)
    if topic in RENDER_TURN_TOPICS:
        return _render_trigger(runtime, topic, payload)
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
