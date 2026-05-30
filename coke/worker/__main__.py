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


def _turn_trigger_from_event(runtime: CokeRuntime, event: StreamEvent) -> TurnTrigger:
    topic = event.topic
    payload = dict(event.payload)
    if topic == "turn.inbound":
        return _inbound_trigger(runtime, payload)
    if topic in {
        "turn.reminder_fire",
        "turn.nightly_summary",
        "turn.proactive_fire",
        "turn.notification",
    }:
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
    account_id = _required_str(payload, "account_id")
    conversation_id = str(payload.get("conversation_id") or "")
    if not conversation_id:
        conversation = runtime.repositories.conversation_runtime.get_conversation_by_account(
            account_id
        )
        if conversation is None:
            raise RuntimeError(f"conversation_not_found_for_account:{account_id}")
        conversation_id = conversation.id
    trigger_type = {
        "turn.reminder_fire": "ReminderFireTurn",
        "turn.nightly_summary": "NightlySummaryTurn",
        "turn.proactive_fire": "ProactiveFireTurn",
        "turn.notification": "NotificationTurn",
    }[topic]
    return TurnTrigger(
        trigger_id=_required_str(payload, "trigger_id"),
        trigger_type=trigger_type,
        mode=TurnMode.RENDER,
        conversation_id=conversation_id,
        account_id=account_id,
        payload=dict(payload),
    )


def _conversation_row(runtime: CokeRuntime, conversation_id: str) -> Mapping[str, Any]:
    row = runtime.session.execute(
        sa.select(schema.conversation).where(schema.conversation.c.id == conversation_id)
    ).mappings().one_or_none()
    if row is None:
        raise RuntimeError(f"conversation_not_found:{conversation_id}")
    return dict(row)


def _message_row(runtime: CokeRuntime, message_id: str) -> Mapping[str, Any]:
    row = runtime.session.execute(
        sa.select(schema.message).where(schema.message.c.id == message_id)
    ).mappings().one_or_none()
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
