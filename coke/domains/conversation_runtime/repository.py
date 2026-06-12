from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import (
    db_id,
    insert_row,
    json_value,
    many,
    one_or_none,
    update_row,
)
from coke.domains.conversation_runtime.models import (
    ContextTokenObservation,
    Conversation,
    ConversationRuntimeError,
    InboundMedia,
    InboundMediaStatusUpdate,
    Message,
    OutboxRecord,
    OutputDisposition,
    Turn,
    WaitingReplyCandidate,
)


class ConversationRuntimeRepository(Protocol):
    def get_conversation(self, conversation_id: str) -> Conversation | None: ...

    def lock_conversation(self, conversation_id: str) -> Conversation | None: ...

    def get_conversation_by_account(self, account_id: str) -> Conversation | None: ...

    def get_message(self, message_id: str) -> Message | None: ...

    def inbound_media_for_message(self, message_id: str) -> list[InboundMedia]: ...

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
        resolved_at: datetime,
    ) -> Message: ...

    def list_open_inbound_conversations(self) -> list[Conversation]: ...

    def add_conversation(self, conversation: Conversation) -> None: ...

    def save_conversation(self, conversation: Conversation) -> None: ...

    def add_inbound_message_with_media_and_outbox(
        self,
        conversation: Conversation,
        message: Message,
        media: tuple[InboundMedia, ...],
        outbox: OutboxRecord,
    ) -> None: ...

    def inbound_messages_for_window(
        self, conversation_id: str, input_from_seq: int, input_to_seq: int
    ) -> list[Message]: ...

    def get_turn(self, turn_id: str) -> Turn | None: ...

    def get_turn_by_trigger_id(self, trigger_id: str) -> Turn | None: ...

    def latest_turn_ids(self, conversation_id: str, limit: int = 10) -> list[str]: ...

    def active_interactive_turns(self, conversation_id: str) -> list[Turn]: ...

    def waiting_reply_candidates(
        self, *, cutoff: datetime, limit: int = 25
    ) -> list[WaitingReplyCandidate]: ...

    def add_turn(self, turn: Turn) -> None: ...

    def save_turn(self, turn: Turn) -> None: ...

    def save_conversation_and_turn(
        self, conversation: Conversation, turn: Turn
    ) -> None: ...

    def add_outbound_message(self, message: Message) -> None: ...

    def outbound_messages_for_turn(self, turn_id: str) -> list[Message]: ...

    def latest_inbound_context_token(self, conversation_id: str) -> str | None: ...

    def latest_inbound_context_observation(
        self, conversation_id: str
    ) -> ContextTokenObservation: ...

    def save_disposition(self, disposition: OutputDisposition) -> None: ...

    def get_disposition(self, turn_id: str) -> OutputDisposition | None: ...

    def add_outbox(self, outbox: OutboxRecord) -> None: ...

    def list_unprocessed_outbox(self, limit: int = 100) -> list[OutboxRecord]: ...

    def mark_outbox_published(
        self, event_id: str, published_at: datetime
    ) -> OutboxRecord: ...

    def mark_outbox_processed(
        self, event_id: str, processed_at: datetime
    ) -> OutboxRecord: ...


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

    def lock_conversation(self, conversation_id: str) -> Conversation | None:
        return self.get_conversation(conversation_id)

    def get_conversation_by_account(self, account_id: str) -> Conversation | None:
        return self.conversations_by_account.get(account_id)

    def get_message(self, message_id: str) -> Message | None:
        return self.messages_by_id.get(message_id)

    def inbound_media_for_message(self, message_id: str) -> list[InboundMedia]:
        media = [
            item
            for item in self.inbound_media_by_id.values()
            if item.message_id == message_id
        ]
        media.sort(key=lambda item: (item.created_at, item.id))
        return media

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
        resolved_at: datetime,
    ) -> Message:
        message = self.messages_by_id.get(message_id)
        if message is None:
            raise ConversationRuntimeError("message_not_found")
        update_by_id = {item.media_id: item for item in media_status_updates}
        for media_id, update in update_by_id.items():
            media = self.inbound_media_by_id.get(media_id)
            if media is None:
                raise ConversationRuntimeError("inbound_media_not_found")
            if media.message_id != message_id:
                raise ConversationRuntimeError("media_message_mismatch")
            if update.processing_status not in {"preserved", "resolved", "failed"}:
                raise ConversationRuntimeError("invalid_media_processing_status")
        updated_message = replace(
            message,
            text=resolved_text,
            updated_at=resolved_at,
        )
        self.messages_by_id[message_id] = updated_message
        for media_id, update in update_by_id.items():
            media = self.inbound_media_by_id[media_id]
            self.inbound_media_by_id[media_id] = replace(
                media,
                processing_status=update.processing_status,
                updated_at=resolved_at,
            )
        return updated_message

    def list_open_inbound_conversations(self) -> list[Conversation]:
        conversations = [
            conversation
            for conversation in self.conversations_by_id.values()
            if conversation.latest_inbound_seq > conversation.last_closed_inbound_seq
        ]
        conversations.sort(key=lambda conversation: conversation.id)
        return conversations

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
        if message.seq is None:
            raise ConversationRuntimeError("inbound_seq_required")
        self._require_message_id_available(message.id)
        for existing_message in self.messages_by_id.values():
            if (
                existing_message.conversation_id == message.conversation_id
                and existing_message.direction == "inbound"
                and existing_message.seq == message.seq
            ):
                raise ConversationRuntimeError("duplicate_inbound_seq")
        if outbox.id in self.outbox_by_id:
            raise ConversationRuntimeError("duplicate_outbox_id")
        if outbox.idempotency_key in self.outbox_by_idempotency_key:
            raise ConversationRuntimeError("duplicate_outbox_idempotency_key")
        for item in media:
            if item.id in self.inbound_media_by_id:
                raise ConversationRuntimeError("duplicate_inbound_media_id")
            if item.message_id != message.id:
                raise ConversationRuntimeError("media_message_mismatch")
        existing = self.conversations_by_id.get(conversation.id)
        if existing is None:
            raise ConversationRuntimeError("conversation_not_found")
        self.save_conversation(
            replace(
                conversation,
                latest_inbound_seq=max(
                    existing.latest_inbound_seq,
                    conversation.latest_inbound_seq,
                ),
                last_closed_inbound_seq=max(
                    existing.last_closed_inbound_seq,
                    conversation.last_closed_inbound_seq,
                ),
            )
        )
        self.messages_by_id[message.id] = message
        for item in media:
            self.inbound_media_by_id[item.id] = item
        self.outbox_by_id[outbox.id] = outbox
        self.outbox_by_idempotency_key[outbox.idempotency_key] = outbox

    def inbound_messages_for_window(
        self, conversation_id: str, input_from_seq: int, input_to_seq: int
    ) -> list[Message]:
        messages = [
            message
            for message in self.messages_by_id.values()
            if (
                message.conversation_id == conversation_id
                and message.direction == "inbound"
                and message.seq is not None
                and input_from_seq <= message.seq <= input_to_seq
            )
        ]
        messages.sort(key=lambda message: (message.seq or 0, message.id))
        return messages

    def get_turn(self, turn_id: str) -> Turn | None:
        return self.turns_by_id.get(turn_id)

    def get_turn_by_trigger_id(self, trigger_id: str) -> Turn | None:
        return self.turns_by_trigger_id.get(trigger_id)

    def latest_turn_ids(self, conversation_id: str, limit: int = 10) -> list[str]:
        turns = [
            turn
            for turn in self.turns_by_id.values()
            if turn.conversation_id == conversation_id
        ]
        turns.sort(
            key=lambda turn: (turn.started_at, turn.created_at, turn.id),
            reverse=True,
        )
        return [turn.id for turn in turns[:limit]]

    def active_interactive_turns(self, conversation_id: str) -> list[Turn]:
        turns = [
            turn
            for turn in self.turns_by_id.values()
            if (
                turn.conversation_id == conversation_id
                and turn.mode == "interactive"
                and turn.completed_at is None
                and (
                    turn.id not in self.dispositions_by_turn_id
                    or self.dispositions_by_turn_id[turn.id].disposition
                    == "pending_async_reply"
                )
            )
        ]
        turns.sort(key=lambda turn: (turn.started_at, turn.created_at, turn.id))
        return turns

    def waiting_reply_candidates(
        self, *, cutoff: datetime, limit: int = 25
    ) -> list[WaitingReplyCandidate]:
        candidates: list[WaitingReplyCandidate] = []
        for turn in sorted(
            self.turns_by_id.values(),
            key=lambda item: (item.started_at, item.created_at, item.id),
        ):
            if len(candidates) >= limit:
                break
            if turn.mode != "interactive" or turn.trigger_type != "InboundTurn":
                continue
            if turn.completed_at is not None or turn.started_at > cutoff:
                continue
            if turn.id in self.dispositions_by_turn_id:
                continue
            conversation = self.conversations_by_id.get(turn.conversation_id)
            if conversation is None:
                continue
            if conversation.latest_inbound_seq != turn.input_to_seq:
                continue
            candidates.append(
                WaitingReplyCandidate(
                    turn_id=turn.id,
                    trigger_id=turn.trigger_id,
                    conversation_id=turn.conversation_id,
                    account_id=conversation.account_id,
                    input_to_seq=turn.input_to_seq,
                )
            )
        return candidates

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

    def save_conversation_and_turn(
        self, conversation: Conversation, turn: Turn
    ) -> None:
        self.save_conversation(conversation)
        self.save_turn(turn)

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

    def latest_inbound_context_token(self, conversation_id: str) -> str | None:
        return self.latest_inbound_context_observation(conversation_id).token

    def latest_inbound_context_observation(
        self, conversation_id: str
    ) -> ContextTokenObservation:
        messages = sorted(
            (
                message
                for message in self.messages_by_id.values()
                if (
                    message.conversation_id == conversation_id
                    and message.direction == "inbound"
                    and message.seq is not None
                )
            ),
            key=lambda message: (message.seq or 0, message.id),
            reverse=True,
        )
        for message in messages:
            token = _context_token(message.payload)
            if token is not None:
                return ContextTokenObservation(
                    token=token,
                    source="latest_inbound_message",
                    observed_at=message.created_at,
                    traceparent=_traceparent_for_inbound_message(
                        self.outbox_by_id.values(),
                        message.id,
                    ),
                )
        return ContextTokenObservation(
            token=None,
            source="none",
            observed_at=None,
            traceparent=None,
        )

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


class PostgresConversationRuntimeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def outbox_records(self) -> list[OutboxRecord]:
        return [_outbox(row) for row in many(self.session, schema.outbox)]

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        row = one_or_none(
            self.session,
            schema.conversation,
            schema.conversation.c.id == conversation_id,
        )
        return _conversation(row) if row else None

    def lock_conversation(self, conversation_id: str) -> Conversation | None:
        statement = (
            sa.select(schema.conversation)
            .where(schema.conversation.c.id == conversation_id)
            .with_for_update()
        )
        row = self.session.execute(statement).mappings().one_or_none()
        return _conversation(dict(row)) if row else None

    def get_conversation_by_account(self, account_id: str) -> Conversation | None:
        statement = (
            sa.select(schema.conversation)
            .where(schema.conversation.c.account_id == account_id)
            .with_for_update()
        )
        row = self.session.execute(statement).mappings().one_or_none()
        return _conversation(dict(row)) if row else None

    def get_message(self, message_id: str) -> Message | None:
        row = one_or_none(
            self.session,
            schema.message,
            schema.message.c.id == db_id(message_id),
        )
        return _message(row) if row else None

    def inbound_media_for_message(self, message_id: str) -> list[InboundMedia]:
        rows = self.session.execute(
            sa.select(schema.inbound_media)
            .where(schema.inbound_media.c.message_id == db_id(message_id))
            .order_by(
                schema.inbound_media.c.created_at.asc(),
                schema.inbound_media.c.id.asc(),
            )
        ).mappings()
        return [_media(dict(row)) for row in rows]

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
        resolved_at: datetime,
    ) -> Message:
        update_by_id = {item.media_id: item for item in media_status_updates}
        for update in update_by_id.values():
            if update.processing_status not in {"preserved", "resolved", "failed"}:
                raise ConversationRuntimeError("invalid_media_processing_status")

        def _write() -> Message:
            message_row = (
                self.session.execute(
                    sa.select(schema.message)
                    .where(schema.message.c.id == db_id(message_id))
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if message_row is None:
                raise ConversationRuntimeError("message_not_found")
            for update in update_by_id.values():
                media_row = (
                    self.session.execute(
                        sa.select(schema.inbound_media)
                        .where(schema.inbound_media.c.id == db_id(update.media_id))
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if media_row is None:
                    raise ConversationRuntimeError("inbound_media_not_found")
                if db_id(media_row["message_id"]) != message_id:
                    raise ConversationRuntimeError("media_message_mismatch")
                self.session.execute(
                    schema.inbound_media.update()
                    .where(schema.inbound_media.c.id == db_id(update.media_id))
                    .values(
                        processing_status=update.processing_status,
                        updated_at=resolved_at,
                    )
                )
            self.session.execute(
                schema.message.update()
                .where(schema.message.c.id == db_id(message_id))
                .values(text=resolved_text, updated_at=resolved_at)
            )
            updated_row = (
                self.session.execute(
                    sa.select(schema.message).where(
                        schema.message.c.id == db_id(message_id)
                    )
                )
                .mappings()
                .one()
            )
            return _message(dict(updated_row))

        return _write()

    def list_open_inbound_conversations(self) -> list[Conversation]:
        rows = self.session.execute(
            sa.select(schema.conversation)
            .where(
                schema.conversation.c.latest_inbound_seq
                > schema.conversation.c.last_closed_inbound_seq
            )
            .order_by(schema.conversation.c.id)
        ).mappings()
        return [_conversation(dict(row)) for row in rows]

    def add_conversation(self, conversation: Conversation) -> None:
        insert_row(
            self.session,
            schema.conversation,
            _conversation_values(conversation),
            {
                "pk_conversation": "duplicate_conversation_id",
                "uq_conversation_account": "duplicate_conversation_account",
            },
            default_error="duplicate_conversation_account",
            error_type=ConversationRuntimeError,
        )

    def save_conversation(self, conversation: Conversation) -> None:
        if (
            update_row(
                self.session,
                schema.conversation,
                _conversation_values(conversation),
                {"uq_conversation_account": "duplicate_conversation_account"},
                default_error="duplicate_conversation_account",
                error_type=ConversationRuntimeError,
            )
            == 0
        ):
            raise ConversationRuntimeError("conversation_not_found")

    def add_inbound_message_with_media_and_outbox(
        self,
        conversation: Conversation,
        message: Message,
        media: tuple[InboundMedia, ...],
        outbox: OutboxRecord,
    ) -> None:
        if message.direction != "inbound":
            raise ConversationRuntimeError("message_not_inbound")
        for item in media:
            if item.message_id != message.id:
                raise ConversationRuntimeError("media_message_mismatch")

        def _write() -> None:
            rowcount = self.session.execute(
                schema.conversation.update()
                .where(schema.conversation.c.id == conversation.id)
                .values(
                    account_id=conversation.account_id,
                    latest_inbound_seq=sa.func.greatest(
                        schema.conversation.c.latest_inbound_seq,
                        conversation.latest_inbound_seq,
                    ),
                    last_closed_inbound_seq=sa.func.greatest(
                        schema.conversation.c.last_closed_inbound_seq,
                        conversation.last_closed_inbound_seq,
                    ),
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            ).rowcount
            if not rowcount:
                raise ConversationRuntimeError("conversation_not_found")
            self.session.execute(
                schema.message.insert().values(**_message_values(message))
            )
            for item in media:
                self.session.execute(
                    schema.inbound_media.insert().values(**_media_values(item))
                )
            self.session.execute(
                schema.outbox.insert().values(**_outbox_values(outbox))
            )

        from coke.domains._pg import write_with_integrity

        write_with_integrity(
            self.session,
            _write,
            {
                "pk_message": "duplicate_message_id",
                "pk_inbound_media": "duplicate_inbound_media_id",
                "pk_outbox": "duplicate_outbox_id",
                "uq_message_inbound_seq": "duplicate_inbound_seq",
                "uq_outbox_idempotency_key": "duplicate_outbox_idempotency_key",
            },
            default_error="duplicate_message_id",
            error_type=ConversationRuntimeError,
        )

    def inbound_messages_for_window(
        self, conversation_id: str, input_from_seq: int, input_to_seq: int
    ) -> list[Message]:
        rows = self.session.execute(
            sa.select(schema.message)
            .where(
                schema.message.c.conversation_id == db_id(conversation_id),
                schema.message.c.direction == "inbound",
                schema.message.c.seq >= input_from_seq,
                schema.message.c.seq <= input_to_seq,
            )
            .order_by(schema.message.c.seq.asc(), schema.message.c.id.asc())
        ).mappings()
        return [_message(dict(row)) for row in rows]

    def get_turn(self, turn_id: str) -> Turn | None:
        row = one_or_none(self.session, schema.turn, schema.turn.c.id == turn_id)
        return _turn(row) if row else None

    def get_turn_by_trigger_id(self, trigger_id: str) -> Turn | None:
        row = one_or_none(
            self.session, schema.turn, schema.turn.c.trigger_id == trigger_id
        )
        return _turn(row) if row else None

    def latest_turn_ids(self, conversation_id: str, limit: int = 10) -> list[str]:
        statement = (
            sa.select(schema.turn.c.id)
            .where(schema.turn.c.conversation_id == conversation_id)
            .order_by(
                schema.turn.c.started_at.desc(),
                schema.turn.c.created_at.desc(),
                schema.turn.c.id.desc(),
            )
            .limit(max(1, limit))
        )
        return [db_id(row[0]) for row in self.session.execute(statement).all()]

    def active_interactive_turns(self, conversation_id: str) -> list[Turn]:
        statement = (
            sa.select(schema.turn)
            .outerjoin(
                schema.output_disposition,
                schema.output_disposition.c.turn_id == schema.turn.c.id,
            )
            .where(
                schema.turn.c.conversation_id == db_id(conversation_id),
                schema.turn.c.mode == "interactive",
                schema.turn.c.completed_at.is_(None),
                sa.or_(
                    schema.output_disposition.c.turn_id.is_(None),
                    schema.output_disposition.c.disposition == "pending_async_reply",
                ),
            )
            .order_by(
                schema.turn.c.started_at.asc(),
                schema.turn.c.created_at.asc(),
                schema.turn.c.id.asc(),
            )
        )
        return [_turn(dict(row)) for row in self.session.execute(statement).mappings()]

    def waiting_reply_candidates(
        self, *, cutoff: datetime, limit: int = 25
    ) -> list[WaitingReplyCandidate]:
        statement = (
            sa.select(
                schema.turn.c.id.label("turn_id"),
                schema.turn.c.trigger_id,
                schema.turn.c.conversation_id,
                schema.conversation.c.account_id,
                schema.turn.c.input_to_seq,
            )
            .select_from(
                schema.turn.join(
                    schema.conversation,
                    schema.conversation.c.id == schema.turn.c.conversation_id,
                ).outerjoin(
                    schema.output_disposition,
                    schema.output_disposition.c.turn_id == schema.turn.c.id,
                )
            )
            .where(
                schema.turn.c.mode == "interactive",
                schema.turn.c.trigger_type == "InboundTurn",
                schema.turn.c.completed_at.is_(None),
                schema.turn.c.started_at <= cutoff,
                schema.conversation.c.latest_inbound_seq == schema.turn.c.input_to_seq,
                schema.output_disposition.c.id.is_(None),
            )
            .order_by(
                schema.turn.c.started_at,
                schema.turn.c.created_at,
                schema.turn.c.id,
            )
            .limit(max(1, limit))
        )
        return [
            WaitingReplyCandidate(
                turn_id=db_id(row["turn_id"]),
                trigger_id=row["trigger_id"],
                conversation_id=db_id(row["conversation_id"]),
                account_id=db_id(row["account_id"]),
                input_to_seq=row["input_to_seq"],
            )
            for row in self.session.execute(statement).mappings()
        ]

    def add_turn(self, turn: Turn) -> None:
        if self.get_conversation(turn.conversation_id) is None:
            raise ConversationRuntimeError("conversation_not_found")
        insert_row(
            self.session,
            schema.turn,
            _turn_values(turn),
            {
                "pk_turn": "duplicate_turn_id",
                "uq_turn_trigger_id": "duplicate_turn_trigger_id",
            },
            default_error="duplicate_turn_trigger_id",
            error_type=ConversationRuntimeError,
        )

    def save_turn(self, turn: Turn) -> None:
        if (
            update_row(
                self.session,
                schema.turn,
                _turn_values(turn),
                {"uq_turn_trigger_id": "duplicate_turn_trigger_id"},
                default_error="duplicate_turn_trigger_id",
                error_type=ConversationRuntimeError,
            )
            == 0
        ):
            raise ConversationRuntimeError("turn_not_found")

    def save_conversation_and_turn(
        self, conversation: Conversation, turn: Turn
    ) -> None:
        self.save_conversation(conversation)
        self.save_turn(turn)

    def add_outbound_message(self, message: Message) -> None:
        if message.direction != "outbound":
            raise ConversationRuntimeError("message_not_outbound")
        if message.turn_id is None or message.segment_index is None:
            raise ConversationRuntimeError("outbound_turn_segment_required")
        insert_row(
            self.session,
            schema.message,
            _message_values(message),
            {
                "pk_message": "duplicate_message_id",
                "uq_message_turn_segment": "duplicate_outbound_segment",
            },
            default_error="duplicate_outbound_segment",
            error_type=ConversationRuntimeError,
        )

    def outbound_messages_for_turn(self, turn_id: str) -> list[Message]:
        return [
            _message(row)
            for row in many(
                self.session,
                schema.message,
                schema.message.c.direction == "outbound",
                schema.message.c.turn_id == turn_id,
                order_by=(schema.message.c.segment_index, schema.message.c.id),
            )
        ]

    def latest_inbound_context_token(self, conversation_id: str) -> str | None:
        return self.latest_inbound_context_observation(conversation_id).token

    def latest_inbound_context_observation(
        self, conversation_id: str
    ) -> ContextTokenObservation:
        statement = (
            sa.select(
                schema.message,
                schema.outbox.c.traceparent.label("inbound_traceparent"),
            )
            .select_from(
                schema.message.outerjoin(
                    schema.outbox,
                    sa.and_(
                        schema.outbox.c.topic == "turn.inbound",
                        schema.outbox.c.payload["message_id"].astext
                        == sa.cast(schema.message.c.id, sa.String),
                    ),
                )
            )
            .where(
                schema.message.c.conversation_id == conversation_id,
                schema.message.c.direction == "inbound",
            )
            .order_by(schema.message.c.seq.desc(), schema.message.c.id.desc())
        )
        for row in self.session.execute(statement).mappings():
            token = _context_token(dict(row["payload"]))
            if token is not None:
                return ContextTokenObservation(
                    token=token,
                    source="latest_inbound_message",
                    observed_at=row["created_at"],
                    traceparent=row["inbound_traceparent"],
                )
        return ContextTokenObservation(
            token=None,
            source="none",
            observed_at=None,
            traceparent=None,
        )

    def save_disposition(self, disposition: OutputDisposition) -> None:
        existing = self.get_disposition(disposition.turn_id)
        if existing is None:
            insert_row(
                self.session,
                schema.output_disposition,
                _disposition_values(disposition),
                {"uq_output_disposition_turn": "duplicate_output_disposition_turn"},
                default_error="duplicate_output_disposition_turn",
                error_type=ConversationRuntimeError,
            )
        else:
            update_row(
                self.session,
                schema.output_disposition,
                _disposition_values(disposition),
                {"uq_output_disposition_turn": "duplicate_output_disposition_turn"},
                default_error="duplicate_output_disposition_turn",
                error_type=ConversationRuntimeError,
            )

    def get_disposition(self, turn_id: str) -> OutputDisposition | None:
        row = one_or_none(
            self.session,
            schema.output_disposition,
            schema.output_disposition.c.turn_id == turn_id,
        )
        return _disposition(row) if row else None

    def add_outbox(self, outbox: OutboxRecord) -> None:
        insert_row(
            self.session,
            schema.outbox,
            _outbox_values(outbox),
            {
                "pk_outbox": "duplicate_outbox_id",
                "uq_outbox_idempotency_key": "duplicate_outbox_idempotency_key",
            },
            default_error="duplicate_outbox_idempotency_key",
            error_type=ConversationRuntimeError,
        )

    def list_unprocessed_outbox(self, limit: int = 100) -> list[OutboxRecord]:
        statement = (
            sa.select(schema.outbox)
            .where(
                schema.outbox.c.processed_at.is_(None),
                schema.outbox.c.acked_at.is_(None),
            )
            .order_by(schema.outbox.c.created_at, schema.outbox.c.id)
            .limit(limit)
        )
        return [
            _outbox(dict(row)) for row in self.session.execute(statement).mappings()
        ]

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

    def _require_outbox(self, event_id: str) -> OutboxRecord:
        row = one_or_none(self.session, schema.outbox, schema.outbox.c.id == event_id)
        if row is None:
            raise ConversationRuntimeError("outbox_not_found")
        return _outbox(row)

    def _save_outbox(self, outbox: OutboxRecord) -> None:
        update_row(
            self.session,
            schema.outbox,
            _outbox_values(outbox),
            {"uq_outbox_idempotency_key": "duplicate_outbox_idempotency_key"},
            default_error="duplicate_outbox_idempotency_key",
            error_type=ConversationRuntimeError,
        )


def _conversation_values(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "account_id": conversation.account_id,
        "latest_inbound_seq": conversation.latest_inbound_seq,
        "last_closed_inbound_seq": conversation.last_closed_inbound_seq,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _conversation(row: Mapping) -> Conversation:
    return Conversation(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["latest_inbound_seq"],
        row["last_closed_inbound_seq"],
        row["created_at"],
        row["updated_at"],
    )


def _message_values(message: Message) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "turn_id": message.turn_id,
        "direction": message.direction,
        "segment_index": message.segment_index,
        "seq": message.seq,
        "channel_identity_id": message.channel_identity_id,
        "causal_inbound_event_id": message.causal_inbound_event_id,
        "text": message.text,
        "payload": json_value(message.payload),
        "facts_hash": message.facts_hash,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }


def _message(row: Mapping) -> Message:
    return Message(
        db_id(row["id"]),
        db_id(row["conversation_id"]),
        db_id(row["turn_id"]) if row["turn_id"] is not None else None,
        row["direction"],
        row["segment_index"],
        row["seq"],
        (
            db_id(row["channel_identity_id"])
            if row["channel_identity_id"] is not None
            else None
        ),
        row["causal_inbound_event_id"],
        row["text"],
        dict(row["payload"]),
        row["facts_hash"],
        row["created_at"],
        row["updated_at"],
    )


def _context_token(payload: Mapping) -> str | None:
    token = payload.get("context_token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _traceparent_for_inbound_message(outbox_records, message_id: str) -> str | None:
    for outbox in outbox_records:
        if (
            outbox.topic == "turn.inbound"
            and isinstance(outbox.payload, Mapping)
            and outbox.payload.get("message_id") == message_id
        ):
            return outbox.traceparent
    return None


def _media_values(media: InboundMedia) -> dict:
    return {
        "id": media.id,
        "message_id": media.message_id,
        "media_type": media.media_type,
        "storage_uri": media.storage_uri,
        "processing_status": media.processing_status,
        "agent_reference": json_value(media.agent_reference),
        "created_at": media.created_at,
        "updated_at": media.updated_at,
    }


def _media(row: Mapping) -> InboundMedia:
    return InboundMedia(
        id=db_id(row["id"]),
        message_id=db_id(row["message_id"]),
        media_type=row["media_type"],
        storage_uri=row["storage_uri"],
        processing_status=row["processing_status"],
        agent_reference=dict(row["agent_reference"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _turn_values(turn: Turn) -> dict:
    return {
        "id": turn.id,
        "conversation_id": turn.conversation_id,
        "trigger_id": turn.trigger_id,
        "trigger_type": turn.trigger_type,
        "mode": turn.mode,
        "input_from_seq": turn.input_from_seq,
        "input_to_seq": turn.input_to_seq,
        "superseded_by_inbound_seq": turn.superseded_by_inbound_seq,
        "started_at": turn.started_at,
        "completed_at": turn.completed_at,
        "created_at": turn.created_at,
        "updated_at": turn.updated_at,
    }


def _turn(row: Mapping) -> Turn:
    return Turn(
        db_id(row["id"]),
        db_id(row["conversation_id"]),
        row["trigger_id"],
        row["trigger_type"],
        row["mode"],
        row["input_from_seq"],
        row["input_to_seq"],
        row["superseded_by_inbound_seq"],
        row["started_at"],
        row["completed_at"],
        row["created_at"],
        row["updated_at"],
    )


def _disposition_values(disposition: OutputDisposition) -> dict:
    return {
        "id": disposition.id,
        "turn_id": disposition.turn_id,
        "disposition": disposition.disposition,
        "reason_code": disposition.reason_code,
        "created_at": disposition.created_at,
        "updated_at": disposition.updated_at,
    }


def _disposition(row: Mapping) -> OutputDisposition:
    return OutputDisposition(
        db_id(row["id"]),
        db_id(row["turn_id"]),
        row["disposition"],
        row["reason_code"],
        row["created_at"],
        row["updated_at"],
    )


def _outbox_values(outbox: OutboxRecord) -> dict:
    return {
        "id": outbox.id,
        "topic": outbox.topic,
        "idempotency_key": outbox.idempotency_key,
        "payload": json_value(outbox.payload),
        "traceparent": outbox.traceparent,
        "status": outbox.status,
        "created_at": outbox.created_at,
        "published_at": outbox.published_at,
        "processed_at": outbox.processed_at,
        "acked_at": outbox.acked_at,
        "retry_count": outbox.retry_count,
        "last_error": outbox.last_error,
    }


def _outbox(row: Mapping) -> OutboxRecord:
    return OutboxRecord(
        db_id(row["id"]),
        row["topic"],
        row["idempotency_key"],
        dict(row["payload"]),
        row["traceparent"],
        row["status"],
        row["created_at"],
        row["published_at"],
        row["processed_at"],
        row["acked_at"],
        row["retry_count"],
        row["last_error"],
    )
