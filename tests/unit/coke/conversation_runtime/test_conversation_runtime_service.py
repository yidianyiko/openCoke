from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import pytest

from coke.domains.conversation_runtime.models import (
    ConversationRuntimeError,
    InboundMediaInput,
    InboundMediaStatusUpdate,
    Message,
    OutboxRecord,
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


def test_close_apis_do_not_accept_staged_materializer_callbacks() -> None:
    for method_name in (
        "commit_reply",
        "commit_no_reply",
        "mark_pending_async_reply",
    ):
        signature = inspect.signature(getattr(ConversationRuntimeService, method_name))
        retired_parameter = "materialize" + "_staged" + "_command"
        assert retired_parameter not in signature.parameters


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


def test_record_inbound_preserves_concurrently_closed_input_window():
    class ConcurrentCloseRepository(InMemoryConversationRuntimeRepository):
        def add_inbound_message_with_media_and_outbox(
            self,
            conversation,
            message,
            media,
            outbox,
        ) -> None:
            if message.seq == 2:
                self.save_conversation(
                    conversation.__class__(
                        conversation.id,
                        conversation.account_id,
                        1,
                        1,
                        conversation.created_at,
                        conversation.updated_at,
                    )
                )
            super().add_inbound_message_with_media_and_outbox(
                conversation,
                message,
                media,
                outbox,
            )

    repository = ConcurrentCloseRepository(now=lambda: NOW)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=sequence_factory("conversation"),
    )
    first = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="first",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    second = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    saved = repository.get_conversation(first.conversation.id)
    assert second.message.seq == 2
    assert saved is not None
    assert saved.latest_inbound_seq == 2
    assert saved.last_closed_inbound_seq == 1


def test_latest_context_token_reads_newest_inbound_message_payload(service):
    first = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="hello",
        payload={"provider": "wechat_personal", "context_token": "ctx-old"},
        traceparent=TRACEPARENT,
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="after",
        payload={"provider": "wechat_personal", "context_token": "ctx-new"},
        traceparent=TRACEPARENT,
    )

    assert service.latest_context_token(first.conversation.id) == "ctx-new"


def test_turn_records_input_window_and_replay_reconciles_existing_turn(
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
    assert replay.turn.input_from_seq == 1
    assert replay.turn.input_to_seq == 1
    assert replay.turn.superseded_by_inbound_seq is None
    assert len(repository.turns_by_trigger_id) == 1


def test_interactive_turn_claims_open_input_window(service):
    first = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="first",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    result = service.start_turn(
        conversation_id=first.conversation.id,
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert result.turn.input_from_seq == 1
    assert result.turn.input_to_seq == 2
    assert [message.text for message in result.input_messages] == ["first", "second"]


def test_start_turn_claim_does_not_lock_conversation_row():
    class LockFailingRepository(InMemoryConversationRuntimeRepository):
        def lock_conversation(self, conversation_id: str):
            raise AssertionError("start_turn must not hold a row lock during claim")

    repository = LockFailingRepository(now=lambda: NOW)
    service = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=sequence_factory("conversation"),
    )
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="hello",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    result = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert result.turn.input_from_seq == 1
    assert result.turn.input_to_seq == 1


def test_close_advances_last_closed_inbound_seq(service, repository):
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
        trigger_type="InboundTurn",
        mode="interactive",
    )

    service.commit_reply(turn_id=turn.turn.id, segments=["hello"])

    saved = repository.get_conversation(inbound.conversation.id)
    assert saved is not None
    assert saved.last_closed_inbound_seq == 1


def test_newer_inbound_before_close_supersedes_old_turn_without_closing(
    service,
    repository,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="old",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="new",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.commit_reply(turn_id=turn.turn.id, segments=["stale"])

    saved = repository.get_conversation(inbound.conversation.id)
    assert saved is not None
    assert saved.last_closed_inbound_seq == 0
    superseded = service.get_disposition(turn.turn.id)
    assert superseded.disposition == "superseded"
    assert superseded.reason_code == "interrupted_by_newer_inbound"


def test_record_inbound_interrupts_active_turn_durably_without_closing_window(
    service,
    repository,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="old",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    newer = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="new",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    saved = repository.get_conversation(inbound.conversation.id)
    superseded = service.get_disposition(turn.turn.id)
    assert saved is not None
    assert saved.last_closed_inbound_seq == 0
    assert superseded.disposition == "superseded"
    assert superseded.reason_code == "interrupted_by_newer_inbound"
    assert tuple(getattr(newer, "interrupted_turns", ())) == (turn.turn,)
    assert newer.outbox.payload.get("interrupted_turn_trigger_ids") == [
        "inbound:provider:message-1"
    ]
    assert repository.active_interactive_turns(inbound.conversation.id) == []


def test_repository_rejects_duplicate_inbound_seq_locally(service, repository):
    first = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="first",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    duplicate_message = Message(
        id="message_duplicate_seq",
        conversation_id=first.conversation.id,
        turn_id=None,
        direction="inbound",
        segment_index=None,
        seq=1,
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-duplicate",
        text="duplicate",
        payload={"provider": "whatsapp_evolution"},
        facts_hash=None,
        created_at=NOW,
        updated_at=NOW,
    )
    duplicate_outbox = OutboxRecord(
        id="outbox_duplicate_seq",
        topic="turn.inbound",
        idempotency_key="inbound:provider:message-duplicate",
        payload={"message_id": duplicate_message.id},
        traceparent=TRACEPARENT,
        status="pending",
        created_at=NOW,
        published_at=None,
        processed_at=None,
        acked_at=None,
        retry_count=0,
        last_error=None,
    )

    with pytest.raises(ConversationRuntimeError, match="duplicate_inbound_seq"):
        repository.add_inbound_message_with_media_and_outbox(
            replace(first.conversation, latest_inbound_seq=1),
            duplicate_message,
            (),
            duplicate_outbox,
        )


def test_duplicate_close_of_already_closed_window_is_superseded(service):
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
        trigger_id="inbound:provider:message-1:first",
        trigger_type="InboundTurn",
        mode="interactive",
    )
    duplicate = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1:duplicate",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    service.commit_reply(turn_id=first.turn.id, segments=["hello"])

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.commit_reply(turn_id=duplicate.turn.id, segments=["duplicate"])

    disposition = service.get_disposition(duplicate.turn.id)
    assert disposition.disposition == "superseded"
    assert disposition.reason_code == "window_already_closed"


@pytest.mark.parametrize("close_path", ["reply", "no_reply"])
def test_successful_close_advances_last_closed_inbound_seq(
    service,
    repository,
    close_path,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id=f"provider:message-{close_path}",
        text="hello",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id=f"inbound:provider:message-{close_path}",
        trigger_type="inbound_message",
        mode="interactive",
    )

    if close_path == "reply":
        service.commit_reply(
            turn_id=turn.turn.id,
            segments=["ok"],
        )
    elif close_path == "no_reply":
        service.commit_no_reply(
            turn_id=turn.turn.id,
        )
    else:
        service.mark_pending_async_reply(
            turn_id=turn.turn.id,
        )

    saved = repository.get_conversation(inbound.conversation.id)

    assert saved is not None
    assert turn.turn.input_to_seq == 1
    assert saved.last_closed_inbound_seq == turn.turn.input_to_seq


def test_pending_async_reply_allows_original_turn_to_commit_final_reply(
    service,
    repository,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="create a shared reminder",
        payload={"provider": "wechat_personal"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    pending = service.mark_pending_async_reply(
        turn_id=turn.turn.id,
        reason_code="waiting_timer_elapsed",
    )
    pending_conversation = repository.get_conversation(inbound.conversation.id)
    pending_turn = repository.get_turn(turn.turn.id)
    assert pending_conversation is not None
    assert pending_conversation.last_closed_inbound_seq == 0
    assert pending_turn is not None
    assert pending_turn.completed_at is None

    replied = service.commit_reply(
        turn_id=turn.turn.id,
        segments=["created"],
    )

    saved = repository.get_conversation(inbound.conversation.id)
    saved_turn = repository.get_turn(turn.turn.id)

    assert pending.disposition == "pending_async_reply"
    assert replied.disposition == "replied"
    assert saved is not None
    assert saved.last_closed_inbound_seq == turn.turn.input_to_seq
    assert saved_turn is not None
    assert saved_turn.completed_at == NOW


def test_recovery_reply_closes_window(
    service,
    repository,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="create a shared reminder",
        payload={"provider": "wechat_personal"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    disposition = service.commit_recovery_reply(
        turn_id=turn.turn.id,
        segments=["我没能帮你完成 music lesson，请再说一次。"],
    )

    saved = repository.get_conversation(inbound.conversation.id)
    saved_turn = repository.get_turn(turn.turn.id)
    outbound = service.outbound_messages_for_turn(turn.turn.id)

    assert disposition.disposition == "recovered"
    assert disposition.reason_code == "grounded_failure_recovery"
    assert saved is not None
    assert saved.last_closed_inbound_seq == turn.turn.input_to_seq
    assert saved_turn is not None
    assert saved_turn.completed_at == NOW
    assert [message.text for message in outbound] == [
        "我没能帮你完成 music lesson，请再说一次。"
    ]


def test_new_inbound_supersedes_pending_async_turn_before_state_change(
    service,
    repository,
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="create a shared reminder",
        payload={"provider": "wechat_personal"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )
    service.mark_pending_async_reply(
        turn_id=turn.turn.id,
        reason_code="waiting_timer_elapsed",
    )

    newer = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="actually make that 11 PM",
        payload={"provider": "wechat_personal"},
        traceparent=TRACEPARENT,
    )

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.guard_state_change(turn_id=turn.turn.id)

    saved = repository.get_conversation(inbound.conversation.id)
    disposition = service.get_disposition(turn.turn.id)
    replacement = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert newer.interrupted_turns[0].id == turn.turn.id
    assert disposition.disposition == "superseded"
    assert disposition.reason_code == "interrupted_by_newer_inbound"
    assert saved is not None
    assert saved.last_closed_inbound_seq == 0
    assert [message.seq for message in replacement.input_messages] == [1, 2]


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
            segments=["stale reply"],
        )

    disposition = service.get_disposition(turn.turn.id)
    assert disposition.disposition == "superseded"
    assert disposition.reason_code == "interrupted_by_newer_inbound"
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
        service.guard_state_change(turn_id=turn.turn.id)

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
        reason_code="intentional_no_reply",
    )

    assert disposition.disposition == "no_reply"
    assert disposition.reason_code == "intentional_no_reply"

    with pytest.raises(ConversationRuntimeError, match="invalid_no_reply_reason"):
        service.commit_no_reply(
            turn_id=turn.turn.id,
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
        reason_code="sync_timeout",
    )
    replied = service.commit_reply(
        turn_id=turn.turn.id,
        segments=["final answer"],
    )

    assert pending.disposition == "pending_async_reply"
    assert replied.disposition == "replied"
    assert replied.id == pending.id
    assert service.get_disposition(turn.turn.id).disposition == "replied"
    assert service.get_disposition(turn.turn.id).id == pending.id


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
            segments=segments,
        )


def test_resolve_inbound_media_updates_message_text_and_media_status(
    service, repository
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:image-1",
        text="",
        payload={"provider": "wechat_personal"},
        media=[
            InboundMediaInput(
                media_type="image",
                storage_uri="data:image/jpeg;base64,/9j/2w==",
                mime="image/jpeg",
                agent_label="image",
            )
        ],
        traceparent=TRACEPARENT,
    )

    updated = service.resolve_inbound_media(
        message_id=inbound.message.id,
        resolved_text="The image says buy milk at 6 PM.",
        media_status_updates=[
            InboundMediaStatusUpdate(
                media_id=inbound.media[0].id,
                processing_status="resolved",
            )
        ],
    )
    started = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:image-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert updated.text == "The image says buy milk at 6 PM."
    assert (
        repository.messages_by_id[inbound.message.id].text
        == "The image says buy milk at 6 PM."
    )
    assert (
        repository.inbound_media_by_id[inbound.media[0].id].processing_status
        == "resolved"
    )
    assert started.input_messages[0].text == "The image says buy milk at 6 PM."


def test_media_resolution_failed_no_reply_closes_window_without_reply(
    service, repository
):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:image-failed",
        text="",
        payload={"provider": "wechat_personal"},
        media=[
            InboundMediaInput(
                media_type="image",
                storage_uri="data:image/jpeg;base64,bad",
                mime="image/jpeg",
                agent_label="image",
            )
        ],
        traceparent=TRACEPARENT,
    )
    service.resolve_inbound_media(
        message_id=inbound.message.id,
        resolved_text="",
        media_status_updates=[
            InboundMediaStatusUpdate(
                media_id=inbound.media[0].id,
                processing_status="failed",
            )
        ],
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:image-failed",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    disposition = service.commit_no_reply(
        turn_id=turn.turn.id,
        reason_code="media_resolution_failed",
    )

    saved_conversation = repository.get_conversation(inbound.conversation.id)
    assert disposition.disposition == "no_reply"
    assert disposition.reason_code == "media_resolution_failed"
    assert saved_conversation is not None
    assert saved_conversation.last_closed_inbound_seq == inbound.message.seq
    assert service.repository.outbound_messages_for_turn(turn.turn.id) == []
