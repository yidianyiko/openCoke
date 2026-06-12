from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import coke.worker.__main__ as worker_main
from coke.domains.conversation_runtime.models import (
    InboundMedia,
    InboundMediaStatusUpdate,
    Message,
    OutputDisposition,
    Turn,
    TurnStartResult,
)
from coke.llm.media_text import MediaTextResolution
from coke.worker.stream_consumer import StreamEvent

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


class FakeConversationRuntimeService:
    def __init__(
        self, *, message_text: str | None, media_status: str = "preserved"
    ) -> None:
        self.message = Message(
            id="message_1",
            conversation_id="conversation_1",
            turn_id=None,
            direction="inbound",
            segment_index=None,
            seq=1,
            channel_identity_id="channel_identity_1",
            causal_inbound_event_id="provider:1",
            text=message_text,
            payload={"provider": "wechat_personal"},
            facts_hash=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.media = [
            InboundMedia(
                id="media_1",
                message_id="message_1",
                media_type="image",
                storage_uri="data:image/jpeg;base64,/9j/2w==",
                processing_status=media_status,
                agent_reference={
                    "type": "image",
                    "label": "image",
                    "mime": "image/jpeg",
                },
                created_at=NOW,
                updated_at=NOW,
            )
        ]
        self.resolution_calls = []
        self.started_turns = []
        self.no_reply_calls = []

    def get_message(self, message_id):
        assert message_id == "message_1"
        return self.message

    def inbound_media_for_message(self, message_id):
        assert message_id == "message_1"
        return tuple(self.media)

    def resolve_inbound_media(self, message_id, resolved_text, media_status_updates):
        self.resolution_calls.append(
            {
                "message_id": message_id,
                "resolved_text": resolved_text,
                "media_status_updates": tuple(media_status_updates),
            }
        )
        self.message = replace(
            self.message,
            text=resolved_text,
            updated_at=NOW,
        )
        return self.message

    def start_turn(self, conversation_id, trigger_id, trigger_type, mode):
        self.started_turns.append(
            {
                "conversation_id": conversation_id,
                "trigger_id": trigger_id,
                "trigger_type": trigger_type,
                "mode": mode,
            }
        )
        return TurnStartResult(
            turn=Turn(
                id="turn_1",
                conversation_id=conversation_id,
                trigger_id=trigger_id,
                trigger_type=trigger_type,
                mode=mode,
                input_from_seq=1,
                input_to_seq=1,
                superseded_by_inbound_seq=None,
                started_at=NOW,
                completed_at=None,
                created_at=NOW,
                updated_at=NOW,
            ),
            replayed=False,
            input_messages=(),
        )

    def commit_no_reply(
        self,
        turn_id,
        reason_code="intentional_no_reply",
    ):
        self.no_reply_calls.append({"turn_id": turn_id, "reason_code": reason_code})
        return OutputDisposition(
            id="disposition_1",
            turn_id=turn_id,
            disposition="no_reply",
            reason_code=reason_code,
            created_at=NOW,
            updated_at=NOW,
        )


class FakeResolver:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    def resolve(self, *, message, media):
        self.calls.append({"message": message, "media": tuple(media)})
        return self.result


class FakeRunner:
    def __init__(self):
        self.inbound_triggers = []

    def run_inbound_turn(self, trigger):
        self.inbound_triggers.append(trigger)
        return SimpleNamespace(
            turn_id="turn_1",
            disposition="replied",
            reason_code=None,
            visible_text="ok",
        )


class FakeRuntime:
    def __init__(self, service, resolver):
        self.conversation_runtime_service = service
        self.media_text_resolver = resolver
        self.turn_runner = FakeRunner()
        self.session = SimpleNamespace(commit=lambda: None)
        self.reply_pubsub = None


def event():
    return StreamEvent(
        event_id="outbox_1",
        topic="turn.inbound",
        idempotency_key="inbound:provider:1",
        payload={
            "conversation_id": "conversation_1",
            "message_id": "message_1",
            "trigger_id": "inbound:provider:1",
        },
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        stream_message_id="1-0",
    )


def test_worker_resolves_media_before_building_inbound_trigger(monkeypatch):
    service = FakeConversationRuntimeService(message_text="")
    resolver = FakeResolver(
        MediaTextResolution(
            resolved_text="The image says buy milk.",
            media_status_updates=(
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="resolved",
                ),
            ),
            suppress_turn=False,
        )
    )
    runtime = FakeRuntime(service, resolver)
    monkeypatch.setattr(
        worker_main,
        "_message_row",
        lambda runtime, message_id: {
            "id": message_id,
            "channel_identity_id": "channel_identity_1",
            "text": service.message.text,
            "payload": {"provider": "wechat_personal"},
            "causal_inbound_event_id": "provider:1",
        },
    )
    monkeypatch.setattr(
        worker_main,
        "_conversation_row",
        lambda runtime, conversation_id: {
            "id": conversation_id,
            "account_id": "account_1",
        },
    )

    worker_main._handle_event(runtime, event())

    assert resolver.calls[0]["message"].text == ""
    assert service.resolution_calls == [
        {
            "message_id": "message_1",
            "resolved_text": "The image says buy milk.",
            "media_status_updates": (
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="resolved",
                ),
            ),
        }
    ]
    assert (
        runtime.turn_runner.inbound_triggers[0].payload["text"]
        == "The image says buy milk."
    )


def test_worker_records_media_failure_no_reply_without_invoking_runner(monkeypatch):
    service = FakeConversationRuntimeService(message_text="")
    resolver = FakeResolver(
        MediaTextResolution(
            resolved_text="",
            media_status_updates=(
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="failed",
                ),
            ),
            suppress_turn=True,
        )
    )
    runtime = FakeRuntime(service, resolver)

    worker_main._handle_event(runtime, event())

    assert service.resolution_calls == [
        {
            "message_id": "message_1",
            "resolved_text": "",
            "media_status_updates": (
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="failed",
                ),
            ),
        }
    ]
    assert service.started_turns == [
        {
            "conversation_id": "conversation_1",
            "trigger_id": "inbound:provider:1",
            "trigger_type": "InboundTurn",
            "mode": "interactive",
        }
    ]
    assert service.no_reply_calls == [
        {"turn_id": "turn_1", "reason_code": "media_resolution_failed"}
    ]
    assert runtime.turn_runner.inbound_triggers == []
