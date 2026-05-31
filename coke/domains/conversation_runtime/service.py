from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from coke.domains.conversation_runtime.models import (
    Conversation,
    ConversationRuntimeError,
    InboundMedia,
    InboundMediaInput,
    InboundRecordResult,
    Message,
    OutboxRecord,
    OutputDisposition,
    TERMINAL_DISPOSITIONS,
    Turn,
    TurnStartResult,
)
from coke.domains.conversation_runtime.repository import (
    ConversationRuntimeRepository,
)


class ConversationRuntimeService:
    def __init__(
        self,
        repository: ConversationRuntimeRepository,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: uuid4().hex)

    def record_inbound(
        self,
        account_id: str,
        channel_identity_id: str,
        causal_inbound_event_id: str,
        text: str | None,
        payload: Mapping[str, Any],
        traceparent: str,
        media: Sequence[InboundMediaInput] | None = None,
    ) -> InboundRecordResult:
        conversation = self.repository.get_conversation_by_account(account_id)
        now = self._now()
        if conversation is None:
            conversation = Conversation(
                id=self._id_factory("conversation"),
                account_id=account_id,
                latest_inbound_seq=0,
                created_at=now,
                updated_at=now,
            )
            self.repository.add_conversation(conversation)

        next_seq = conversation.latest_inbound_seq + 1
        updated_conversation = replace(
            conversation,
            latest_inbound_seq=next_seq,
            updated_at=now,
        )
        message = Message(
            id=self._id_factory("message"),
            conversation_id=conversation.id,
            turn_id=None,
            direction="inbound",
            segment_index=None,
            seq=next_seq,
            channel_identity_id=channel_identity_id,
            causal_inbound_event_id=causal_inbound_event_id,
            text=text,
            payload=dict(payload),
            facts_hash=None,
            created_at=now,
            updated_at=now,
        )
        preserved_media = tuple(
            InboundMedia(
                id=self._id_factory("inbound_media"),
                message_id=message.id,
                media_type=item.media_type,
                storage_uri=item.storage_uri,
                processing_status="preserved",
                agent_reference={
                    "type": item.media_type,
                    "label": item.agent_label,
                },
                created_at=now,
                updated_at=now,
            )
            for item in (media or ())
        )
        outbox = OutboxRecord(
            id=self._id_factory("outbox"),
            topic="turn.inbound",
            idempotency_key=f"inbound:{causal_inbound_event_id}",
            payload={
                "conversation_id": updated_conversation.id,
                "message_id": message.id,
                "trigger_id": f"inbound:{causal_inbound_event_id}",
                "latest_inbound_seq": next_seq,
            },
            traceparent=traceparent,
            status="pending",
            created_at=now,
            published_at=None,
            processed_at=None,
            acked_at=None,
            retry_count=0,
            last_error=None,
        )
        self.repository.add_inbound_message_with_media_and_outbox(
            updated_conversation,
            message,
            preserved_media,
            outbox,
        )
        return InboundRecordResult(
            conversation=updated_conversation,
            message=message,
            media=preserved_media,
            outbox=outbox,
        )

    def start_turn(
        self,
        conversation_id: str,
        trigger_id: str,
        trigger_type: str,
        mode: str,
    ) -> TurnStartResult:
        existing = self.repository.get_turn_by_trigger_id(trigger_id)
        if existing is not None:
            if existing.conversation_id != conversation_id:
                raise ConversationRuntimeError("turn_trigger_conversation_mismatch")
            return TurnStartResult(turn=existing, replayed=True)

        conversation = self._require_conversation(conversation_id)
        now = self._now()
        turn = Turn(
            id=self._id_factory("turn"),
            conversation_id=conversation_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            mode=mode,
            based_on_inbound_seq=conversation.latest_inbound_seq,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_turn(turn)
        return TurnStartResult(turn=turn, replayed=False)

    def commit_reply(
        self,
        turn_id: str,
        based_on_inbound_seq: int | None,
        segments: Sequence[str],
        reason_code: str = "reply_ready",
    ) -> OutputDisposition:
        if not 1 <= len(segments) <= 3:
            raise ConversationRuntimeError("invalid_segment_count")
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "replied":
            return existing
        self._ensure_turn_can_transition(existing, target="replied")
        self._ensure_fresh(turn, based_on_inbound_seq)

        now = self._now()
        for index, text in enumerate(segments, start=1):
            self.repository.add_outbound_message(
                Message(
                    id=self._id_factory("message"),
                    conversation_id=turn.conversation_id,
                    turn_id=turn.id,
                    direction="outbound",
                    segment_index=index,
                    seq=None,
                    channel_identity_id=None,
                    causal_inbound_event_id=None,
                    text=text,
                    payload={"segment_index": index},
                    facts_hash=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        disposition = self._new_disposition(turn.id, "replied", reason_code)
        self.repository.save_disposition(disposition)
        self.repository.save_turn(replace(turn, completed_at=now, updated_at=now))
        return disposition

    def commit_no_reply(
        self,
        turn_id: str,
        based_on_inbound_seq: int | None,
        reason_code: str = "intentional_no_reply",
    ) -> OutputDisposition:
        if reason_code != "intentional_no_reply":
            raise ConversationRuntimeError("invalid_no_reply_reason")
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "no_reply":
            return existing
        self._ensure_turn_can_transition(existing, target="no_reply")
        self._ensure_fresh(turn, based_on_inbound_seq)
        now = self._now()
        disposition = self._new_disposition(turn.id, "no_reply", reason_code)
        self.repository.save_disposition(disposition)
        self.repository.save_turn(replace(turn, completed_at=now, updated_at=now))
        return disposition

    def mark_pending_async_reply(
        self,
        turn_id: str,
        based_on_inbound_seq: int | None,
        reason_code: str = "sync_timeout",
    ) -> OutputDisposition:
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "pending_async_reply":
            return existing
        self._ensure_turn_can_transition(existing, target="pending_async_reply")
        self._ensure_fresh(turn, based_on_inbound_seq)
        disposition = self._new_disposition(turn.id, "pending_async_reply", reason_code)
        self.repository.save_disposition(disposition)
        return disposition

    def mark_failed(self, turn_id: str, reason_code: str) -> OutputDisposition:
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "failed":
            return existing
        self._ensure_turn_can_transition(existing, target="failed")
        now = self._now()
        disposition = self._new_disposition(turn.id, "failed", reason_code)
        self.repository.save_disposition(disposition)
        self.repository.save_turn(replace(turn, completed_at=now, updated_at=now))
        return disposition

    def guard_state_change(
        self,
        turn_id: str,
        based_on_inbound_seq: int | None,
    ) -> None:
        turn = self._require_turn(turn_id)
        self._ensure_fresh(turn, based_on_inbound_seq)

    def get_disposition(self, turn_id: str) -> OutputDisposition:
        disposition = self.repository.get_disposition(turn_id)
        if disposition is None:
            raise ConversationRuntimeError("disposition_not_found")
        return disposition

    def outbound_messages_for_turn(self, turn_id: str) -> list[Message]:
        self._require_turn(turn_id)
        return self.repository.outbound_messages_for_turn(turn_id)

    def record_outbound_message(
        self,
        turn_id: str,
        text: str,
        *,
        segment_index: int,
        payload: Mapping[str, Any] | None = None,
    ) -> Message:
        turn = self._require_turn(turn_id)
        now = self._now()
        message = Message(
            id=self._id_factory("message"),
            conversation_id=turn.conversation_id,
            turn_id=turn.id,
            direction="outbound",
            segment_index=segment_index,
            seq=None,
            channel_identity_id=None,
            causal_inbound_event_id=None,
            text=text,
            payload=dict(payload or {}),
            facts_hash=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_outbound_message(message)
        return message

    def latest_context_token(self, conversation_id: str) -> str | None:
        self._require_conversation(conversation_id)
        return self.repository.latest_inbound_context_token(conversation_id)

    def enqueue_render_turn(
        self,
        *,
        topic: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        traceparent: str,
    ) -> OutboxRecord:
        now = self._now()
        outbox = OutboxRecord(
            id=self._id_factory("outbox"),
            topic=topic,
            idempotency_key=idempotency_key,
            payload=dict(payload),
            traceparent=traceparent,
            status="pending",
            created_at=now,
            published_at=None,
            processed_at=None,
            acked_at=None,
            retry_count=0,
            last_error=None,
        )
        self.repository.add_outbox(outbox)
        return outbox

    def _ensure_fresh(self, turn: Turn, based_on_inbound_seq: int | None) -> None:
        if turn.based_on_inbound_seq != based_on_inbound_seq:
            raise ConversationRuntimeError("based_on_inbound_seq_mismatch")
        conversation = self._lock_conversation(turn.conversation_id)
        if (
            based_on_inbound_seq is not None
            and conversation.latest_inbound_seq != based_on_inbound_seq
        ):
            self._record_superseded(turn, reason_code="newer_inbound_seq")
            raise ConversationRuntimeError(
                "turn_superseded",
                fact={
                    "turn_id": turn.id,
                    "based_on_inbound_seq": based_on_inbound_seq,
                    "latest_inbound_seq": conversation.latest_inbound_seq,
                },
            )

    def _record_superseded(self, turn: Turn, reason_code: str) -> OutputDisposition:
        now = self._now()
        disposition = self._new_disposition(turn.id, "superseded", reason_code)
        self.repository.save_disposition(disposition)
        self.repository.save_turn(replace(turn, completed_at=now, updated_at=now))
        return disposition

    def _ensure_turn_can_transition(
        self,
        existing: OutputDisposition | None,
        target: str,
    ) -> None:
        if existing is None:
            return
        if existing.disposition == "pending_async_reply" and target in {
            "replied",
            "failed",
        }:
            return
        if existing.disposition in TERMINAL_DISPOSITIONS:
            raise ConversationRuntimeError("turn_already_terminal")
        raise ConversationRuntimeError("invalid_disposition_transition")

    def _new_disposition(
        self,
        turn_id: str,
        disposition: str,
        reason_code: str | None,
    ) -> OutputDisposition:
        now = self._now()
        return OutputDisposition(
            id=self._id_factory("output_disposition"),
            turn_id=turn_id,
            disposition=disposition,
            reason_code=reason_code,
            created_at=now,
            updated_at=now,
        )

    def _require_conversation(self, conversation_id: str) -> Conversation:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationRuntimeError("conversation_not_found")
        return conversation

    def _lock_conversation(self, conversation_id: str) -> Conversation:
        conversation = self.repository.lock_conversation(conversation_id)
        if conversation is None:
            raise ConversationRuntimeError("conversation_not_found")
        return conversation

    def _require_turn(self, turn_id: str) -> Turn:
        turn = self.repository.get_turn(turn_id)
        if turn is None:
            raise ConversationRuntimeError("turn_not_found")
        return turn
