from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import pytest

from coke.domains.conversation_runtime.models import (
    ConversationRuntimeError,
    InboundMediaInput,
    Message,
)
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


@pytest.fixture
def repository() -> InMemoryConversationRuntimeRepository:
    return InMemoryConversationRuntimeRepository(now=lambda: NOW)


@pytest.fixture
def service(repository) -> ConversationRuntimeService:
    return ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=sequence_factory("conversation"),
    )


def test_default_conversation_runtime_ids_are_schema_uuid_strings(repository):
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
    )

    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="hello",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )

    for value in [inbound.conversation.id, inbound.message.id, turn.turn.id]:
        assert UUID(value).hex == value


def test_inbound_messages_increment_durable_latest_seq_and_preserve_media_reference(
    service,
    repository,
):
    first = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="look",
        payload={"provider": "whatsapp_evolution"},
        media=[
            InboundMediaInput(
                media_type="image",
                storage_uri="s3://bucket/image-1",
                agent_label="[image]",
            )
        ],
        traceparent=TRACEPARENT,
    )
    second = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="after",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    saved = repository.get_conversation(first.conversation.id)

    assert first.message.seq == 1
    assert second.message.seq == 2
    assert saved is not None
    assert saved.latest_inbound_seq == 2
    assert first.media[0].message_id == first.message.id
    assert first.media[0].media_type == "image"
    assert first.media[0].storage_uri == "s3://bucket/image-1"
    assert first.media[0].processing_status == "preserved"
    assert first.media[0].agent_reference == {"type": "image", "label": "[image]"}
    assert repository.outbox_records[0].topic == "turn.inbound"
    assert repository.outbox_records[0].payload["message_id"] == first.message.id


def test_turn_records_based_on_inbound_seq_and_replay_reconciles_existing_turn(
    service,
    repository,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="hello",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    first = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )
    replay = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.turn.id == first.turn.id
    assert replay.turn.based_on_inbound_seq == 1
    assert len(repository.turns_by_trigger_id) == 1


def test_stale_outbound_commit_records_superseded_and_never_no_reply_or_failed(
    service,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="old request",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="new request",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.commit_reply(
            turn_id=turn.turn.id,
            based_on_inbound_seq=turn.turn.based_on_inbound_seq,
            segments=["stale reply"],
        )

    disposition = service.get_disposition(turn.turn.id)
    assert disposition.disposition == "superseded"
    assert disposition.reason_code == "newer_inbound_seq"
    assert disposition.disposition != "no_reply"
    assert disposition.disposition != "failed"


def test_stale_state_change_guard_rejects_before_business_commit(service):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="create a reminder",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="actually cancel that",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.guard_state_change(
            turn_id=turn.turn.id,
            based_on_inbound_seq=turn.turn.based_on_inbound_seq,
        )

    assert service.get_disposition(turn.turn.id).disposition == "superseded"


def test_no_reply_is_only_intentional_and_not_failure_or_supersession(service):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="thanks",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )

    disposition = service.commit_no_reply(
        turn_id=turn.turn.id,
        based_on_inbound_seq=turn.turn.based_on_inbound_seq,
        reason_code="intentional_no_reply",
    )

    assert disposition.disposition == "no_reply"
    assert disposition.reason_code == "intentional_no_reply"

    with pytest.raises(ConversationRuntimeError, match="invalid_no_reply_reason"):
        service.commit_no_reply(
            turn_id=turn.turn.id,
            based_on_inbound_seq=turn.turn.based_on_inbound_seq,
            reason_code="failure",
        )


def test_pending_async_reply_is_only_non_terminal_and_transitions_to_replied(service):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="slow request",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )

    pending = service.mark_pending_async_reply(
        turn_id=turn.turn.id,
        based_on_inbound_seq=turn.turn.based_on_inbound_seq,
        reason_code="sync_timeout",
    )
    replied = service.commit_reply(
        turn_id=turn.turn.id,
        based_on_inbound_seq=turn.turn.based_on_inbound_seq,
        segments=["final answer"],
    )

    assert pending.disposition == "pending_async_reply"
    assert replied.disposition == "replied"
    assert service.get_disposition(turn.turn.id).disposition == "replied"


def test_outbound_segments_are_unique_by_turn_id_and_segment_index(service, repository):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="reply please",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="inbound_message",
        mode="interactive",
    )
    service.commit_reply(
        turn_id=turn.turn.id,
        based_on_inbound_seq=turn.turn.based_on_inbound_seq,
        segments=["one", "two"],
    )
    existing = repository.outbound_messages_for_turn(turn.turn.id)[0]

    with pytest.raises(ConversationRuntimeError, match="duplicate_outbound_segment"):
        repository.add_outbound_message(
            Message(
                id="message_duplicate",
                conversation_id=existing.conversation_id,
                turn_id=existing.turn_id,
                direction="outbound",
                segment_index=existing.segment_index,
                seq=None,
                channel_identity_id=None,
                causal_inbound_event_id=None,
                text="duplicate",
                payload={"segment_index": existing.segment_index},
                facts_hash=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )


@pytest.mark.parametrize("segments", [[], ["one", "two", "three", "four"]])
def test_reply_requires_one_to_three_segments(service, segments):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id=f"provider:{len(segments)}",
        text="reply please",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id=f"inbound:provider:{len(segments)}",
        trigger_type="inbound_message",
        mode="interactive",
    )

    with pytest.raises(ConversationRuntimeError, match="invalid_segment_count"):
        service.commit_reply(
            turn_id=turn.turn.id,
            based_on_inbound_seq=turn.turn.based_on_inbound_seq,
            segments=segments,
        )
