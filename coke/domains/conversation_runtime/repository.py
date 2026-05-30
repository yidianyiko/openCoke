from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from coke.domains.conversation_runtime.models import (
    Conversation,
    ConversationRuntimeError,
    InboundMedia,
    Message,
    OutboxRecord,
    OutputDisposition,
    Turn,
)


class ConversationRuntimeRepository(Protocol):
    def get_conversation(self, conversation_id: str) -> Conversation | None: ...

    def get_conversation_by_account(self, account_id: str) -> Conversation | None: ...

    def add_conversation(self, conversation: Conversation) -> None: ...

    def save_conversation(self, conversation: Conversation) -> None: ...

    def add_inbound_message_with_media_and_outbox(
        self,
        conversation: Conversation,
        message: Message,
        media: tuple[InboundMedia, ...],
        outbox: OutboxRecord,
    ) -> None: ...

    def get_turn(self, turn_id: str) -> Turn | None: ...

    def get_turn_by_trigger_id(self, trigger_id: str) -> Turn | None: ...

    def add_turn(self, turn: Turn) -> None: ...

    def save_turn(self, turn: Turn) -> None: ...

    def add_outbound_message(self, message: Message) -> None: ...

    def outbound_messages_for_turn(self, turn_id: str) -> list[Message]: ...

    def save_disposition(self, disposition: OutputDisposition) -> None: ...

    def get_disposition(self, turn_id: str) -> OutputDisposition | None: ...

    def add_outbox(self, outbox: OutboxRecord) -> None: ...

    def list_unprocessed_outbox(self, limit: int = 100) -> list[OutboxRecord]: ...

    def mark_outbox_published(self, event_id: str, published_at: datetime) -> OutboxRecord:
        ...

    def mark_outbox_processed(self, event_id: str, processed_at: datetime) -> OutboxRecord:
        ...


class InMemoryConversationRuntimeRepository:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self.conversations_by_id: dict[str, Conversation] = {}
        self.conversations_by_account: dict[str, Conversation] = {}
        self.messages_by_id: dict[str, Message] = {}
        self.inbound_media_by_id: dict[str, InboundMedia] = {}
        self.turns_by_id: dict[str, Turn] = {}
        self.turns_by_trigger_id: dict[str, Turn] = {}
        self.dispositions_by_turn_id: dict[str, OutputDisposition] = {}
        self.outbox_by_id: dict[str, OutboxRecord] = {}
        self.outbox_by_idempotency_key: dict[str, OutboxRecord] = {}

    @property
    def outbox_records(self) -> list[OutboxRecord]:
        return list(self.outbox_by_id.values())

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.conversations_by_id.get(conversation_id)

    def get_conversation_by_account(self, account_id: str) -> Conversation | None:
        return self.conversations_by_account.get(account_id)

    def add_conversation(self, conversation: Conversation) -> None:
        if conversation.id in self.conversations_by_id:
            raise ConversationRuntimeError("duplicate_conversation_id")
        if conversation.account_id in self.conversations_by_account:
            raise ConversationRuntimeError("duplicate_conversation_account")
        self.conversations_by_id[conversation.id] = conversation
        self.conversations_by_account[conversation.account_id] = conversation

    def save_conversation(self, conversation: Conversation) -> None:
        existing = self.conversations_by_id.get(conversation.id)
        if existing is None:
            raise ConversationRuntimeError("conversation_not_found")
        account_owner = self.conversations_by_account.get(conversation.account_id)
        if account_owner is not None and account_owner.id != conversation.id:
            raise ConversationRuntimeError("duplicate_conversation_account")
        if existing.account_id != conversation.account_id:
            self.conversations_by_account.pop(existing.account_id, None)
        self.conversations_by_id[conversation.id] = conversation
        self.conversations_by_account[conversation.account_id] = conversation

    def add_inbound_message_with_media_and_outbox(
        self,
        conversation: Conversation,
        message: Message,
        media: tuple[InboundMedia, ...],
        outbox: OutboxRecord,
    ) -> None:
        if message.direction != "inbound":
            raise ConversationRuntimeError("message_not_inbound")
        self._require_message_id_available(message.id)
        if outbox.id in self.outbox_by_id:
            raise ConversationRuntimeError("duplicate_outbox_id")
        if outbox.idempotency_key in self.outbox_by_idempotency_key:
            raise ConversationRuntimeError("duplicate_outbox_idempotency_key")
        for item in media:
            if item.id in self.inbound_media_by_id:
                raise ConversationRuntimeError("duplicate_inbound_media_id")
            if item.message_id != message.id:
                raise ConversationRuntimeError("media_message_mismatch")
        self.save_conversation(conversation)
        self.messages_by_id[message.id] = message
        for item in media:
            self.inbound_media_by_id[item.id] = item
        self.outbox_by_id[outbox.id] = outbox
        self.outbox_by_idempotency_key[outbox.idempotency_key] = outbox

    def get_turn(self, turn_id: str) -> Turn | None:
        return self.turns_by_id.get(turn_id)

    def get_turn_by_trigger_id(self, trigger_id: str) -> Turn | None:
        return self.turns_by_trigger_id.get(trigger_id)

    def add_turn(self, turn: Turn) -> None:
        if turn.id in self.turns_by_id:
            raise ConversationRuntimeError("duplicate_turn_id")
        if turn.trigger_id in self.turns_by_trigger_id:
            raise ConversationRuntimeError("duplicate_turn_trigger_id")
        if turn.conversation_id not in self.conversations_by_id:
            raise ConversationRuntimeError("conversation_not_found")
        self.turns_by_id[turn.id] = turn
        self.turns_by_trigger_id[turn.trigger_id] = turn

    def save_turn(self, turn: Turn) -> None:
        existing = self.turns_by_id.get(turn.id)
        if existing is None:
            raise ConversationRuntimeError("turn_not_found")
        trigger_owner = self.turns_by_trigger_id.get(turn.trigger_id)
        if trigger_owner is not None and trigger_owner.id != turn.id:
            raise ConversationRuntimeError("duplicate_turn_trigger_id")
        if existing.trigger_id != turn.trigger_id:
            self.turns_by_trigger_id.pop(existing.trigger_id, None)
        self.turns_by_id[turn.id] = turn
        self.turns_by_trigger_id[turn.trigger_id] = turn

    def add_outbound_message(self, message: Message) -> None:
        if message.direction != "outbound":
            raise ConversationRuntimeError("message_not_outbound")
        if message.turn_id is None or message.segment_index is None:
            raise ConversationRuntimeError("outbound_turn_segment_required")
        self._require_message_id_available(message.id)
        for existing in self.messages_by_id.values():
            if (
                existing.direction == "outbound"
                and existing.turn_id == message.turn_id
                and existing.segment_index == message.segment_index
            ):
                raise ConversationRuntimeError("duplicate_outbound_segment")
        self.messages_by_id[message.id] = message

    def outbound_messages_for_turn(self, turn_id: str) -> list[Message]:
        return [
            message
            for message in self.messages_by_id.values()
            if message.direction == "outbound" and message.turn_id == turn_id
        ]

    def save_disposition(self, disposition: OutputDisposition) -> None:
        self.dispositions_by_turn_id[disposition.turn_id] = disposition

    def get_disposition(self, turn_id: str) -> OutputDisposition | None:
        return self.dispositions_by_turn_id.get(turn_id)

    def add_outbox(self, outbox: OutboxRecord) -> None:
        if outbox.id in self.outbox_by_id:
            raise ConversationRuntimeError("duplicate_outbox_id")
        if outbox.idempotency_key in self.outbox_by_idempotency_key:
            raise ConversationRuntimeError("duplicate_outbox_idempotency_key")
        self.outbox_by_id[outbox.id] = outbox
        self.outbox_by_idempotency_key[outbox.idempotency_key] = outbox

    def list_unprocessed_outbox(self, limit: int = 100) -> list[OutboxRecord]:
        return [
            record
            for record in self.outbox_by_id.values()
            if record.processed_at is None and record.acked_at is None
        ][:limit]

    def mark_outbox_published(
        self, event_id: str, published_at: datetime
    ) -> OutboxRecord:
        record = self._require_outbox(event_id)
        updated = replace(record, status="published", published_at=published_at)
        self._save_outbox(updated)
        return updated

    def mark_outbox_processed(
        self, event_id: str, processed_at: datetime
    ) -> OutboxRecord:
        record = self._require_outbox(event_id)
        updated = replace(
            record,
            status="processed",
            processed_at=processed_at,
            acked_at=processed_at,
        )
        self._save_outbox(updated)
        return updated

    def _require_message_id_available(self, message_id: str) -> None:
        if message_id in self.messages_by_id:
            raise ConversationRuntimeError("duplicate_message_id")

    def _require_outbox(self, event_id: str) -> OutboxRecord:
        record = self.outbox_by_id.get(event_id)
        if record is None:
            raise ConversationRuntimeError("outbox_not_found")
        return record

    def _save_outbox(self, outbox: OutboxRecord) -> None:
        self.outbox_by_id[outbox.id] = outbox
        self.outbox_by_idempotency_key[outbox.idempotency_key] = outbox
