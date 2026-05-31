from __future__ import annotations

from dataclasses import replace

import pytest

from coke.domains.conversation_runtime.models import (
    Conversation,
    ConversationRuntimeError,
    InboundMedia,
    Message,
    OutboxRecord,
    OutputDisposition,
    Turn,
)
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
    PostgresConversationRuntimeRepository,
)

from .conftest import ACCOUNT_A, CONVERSATION_A, MESSAGE_A, NOW, TURN_A, seed_account

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _conversation() -> Conversation:
    return Conversation(CONVERSATION_A, ACCOUNT_A, 0, 0, NOW, NOW)


def _message(direction: str = "inbound") -> Message:
    return Message(
        MESSAGE_A if direction == "inbound" else "50000000000000000000000000000002",
        CONVERSATION_A,
        TURN_A if direction == "outbound" else None,
        direction,
        0 if direction == "outbound" else None,
        1 if direction == "inbound" else None,
        None,
        "provider:message-1",
        "hello",
        {"provider": "whatsapp_evolution"},
        None,
        NOW,
        NOW,
    )


def _inbound_message(message_id: str, seq: int, text: str) -> Message:
    return Message(
        message_id,
        CONVERSATION_A,
        None,
        "inbound",
        None,
        seq,
        None,
        f"provider:message-{seq}",
        text,
        {"provider": "whatsapp_evolution"},
        None,
        NOW,
        NOW,
    )


def _media() -> InboundMedia:
    return InboundMedia(
        "51000000000000000000000000000001",
        MESSAGE_A,
        "image",
        "s3://bucket/image",
        "preserved",
        {"type": "image", "label": "[image]"},
        NOW,
        NOW,
    )


def _outbox() -> OutboxRecord:
    return OutboxRecord(
        "70000000000000000000000000000002",
        "turn.inbound",
        "turn:message-1",
        {"message_id": MESSAGE_A},
        TRACEPARENT,
        "pending",
        NOW,
        None,
        None,
        None,
        0,
        None,
    )


def _outbox_for(message_id: str, seq: int) -> OutboxRecord:
    return OutboxRecord(
        f"7000000000000000000000000000000{seq}",
        "turn.inbound",
        f"turn:message-{seq}",
        {"message_id": message_id},
        TRACEPARENT,
        "pending",
        NOW,
        None,
        None,
        None,
        0,
        None,
    )


def _turn() -> Turn:
    return Turn(
        TURN_A,
        CONVERSATION_A,
        "trigger:message-1",
        "inbound_message",
        "interactive",
        1,
        1,
        None,
        NOW,
        None,
        NOW,
        NOW,
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemoryConversationRuntimeRepository()
    seed_account(postgres_session)
    return PostgresConversationRuntimeRepository(postgres_session)


def test_conversation_inbound_media_turn_outbound_and_outbox_round_trip(
    repository,
) -> None:
    conversation = _conversation()
    repository.add_conversation(conversation)
    repository.add_inbound_message_with_media_and_outbox(
        replace(conversation, latest_inbound_seq=1),
        _message("inbound"),
        (_media(),),
        _outbox(),
    )
    repository.add_turn(_turn())
    repository.add_outbound_message(_message("outbound"))
    disposition = OutputDisposition(
        "41000000000000000000000000000001",
        TURN_A,
        "replied",
        None,
        NOW,
        NOW,
    )
    repository.save_disposition(disposition)

    assert repository.get_conversation(CONVERSATION_A).latest_inbound_seq == 1
    assert repository.get_conversation_by_account(ACCOUNT_A).id == CONVERSATION_A
    assert repository.get_turn(TURN_A) == _turn()
    assert repository.get_turn_by_trigger_id("trigger:message-1") == _turn()
    assert repository.outbound_messages_for_turn(TURN_A) == [_message("outbound")]
    assert repository.get_disposition(TURN_A) == disposition
    assert repository.list_unprocessed_outbox() == [_outbox()]

    published = repository.mark_outbox_published(_outbox().id, NOW)
    processed = repository.mark_outbox_processed(_outbox().id, NOW)
    assert published.status == "published"
    assert processed.status == "processed"
    assert processed.acked_at == NOW


def test_inbound_messages_for_window_returns_ordered_inbound_only(repository) -> None:
    conversation = _conversation()
    repository.add_conversation(conversation)
    second = _inbound_message(
        "50000000000000000000000000000002",
        2,
        "second",
    )
    first = _inbound_message(
        "50000000000000000000000000000001",
        1,
        "first",
    )
    repository.add_inbound_message_with_media_and_outbox(
        replace(conversation, latest_inbound_seq=2),
        second,
        (),
        _outbox_for(second.id, 2),
    )
    repository.add_inbound_message_with_media_and_outbox(
        replace(conversation, latest_inbound_seq=2),
        first,
        (),
        _outbox_for(first.id, 1),
    )
    repository.add_turn(_turn())
    repository.add_outbound_message(_message("outbound"))

    messages = repository.inbound_messages_for_window(CONVERSATION_A, 1, 2)

    assert [message.text for message in messages] == ["first", "second"]
    assert [message.direction for message in messages] == ["inbound", "inbound"]


def test_add_inbound_message_preserves_higher_durable_last_closed_seq(
    repository,
) -> None:
    conversation = _conversation()
    repository.add_conversation(conversation)
    repository.save_conversation(
        replace(conversation, latest_inbound_seq=1, last_closed_inbound_seq=1)
    )

    repository.add_inbound_message_with_media_and_outbox(
        replace(conversation, latest_inbound_seq=2, last_closed_inbound_seq=0),
        _inbound_message("50000000000000000000000000000002", 2, "new input"),
        (),
        _outbox_for("50000000000000000000000000000002", 2),
    )

    saved = repository.get_conversation(CONVERSATION_A)
    assert saved.latest_inbound_seq == 2
    assert saved.last_closed_inbound_seq == 1


def test_conversation_uniqueness_errors_match_in_memory(repository) -> None:
    repository.add_conversation(_conversation())
    repository.add_turn(_turn())
    repository.add_outbound_message(_message("outbound"))
    repository.add_outbox(_outbox())

    with pytest.raises(
        ConversationRuntimeError, match="duplicate_conversation_account"
    ):
        repository.add_conversation(
            Conversation(
                "30000000000000000000000000000002",
                ACCOUNT_A,
                0,
                0,
                NOW,
                NOW,
            )
        )

    with pytest.raises(ConversationRuntimeError, match="duplicate_turn_trigger_id"):
        repository.add_turn(replace(_turn(), id="40000000000000000000000000000002"))

    with pytest.raises(ConversationRuntimeError, match="duplicate_outbound_segment"):
        repository.add_outbound_message(
            replace(_message("outbound"), id="50000000000000000000000000000003")
        )

    with pytest.raises(
        ConversationRuntimeError, match="duplicate_outbox_idempotency_key"
    ):
        repository.add_outbox(replace(_outbox(), id="70000000000000000000000000000003"))
