from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from coke.domains.conversation_runtime.models import (
    Conversation,
    ConversationRuntimeError,
    CurrentInputMessage,
    InboundMedia,
    InboundMediaInput,
    InboundRecordResult,
    Message,
    OutboxRecord,
    OutputDisposition,
    StagedCommand,
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
                last_closed_inbound_seq=0,
                created_at=now,
                updated_at=now,
            )
            try:
                self.repository.add_conversation(conversation)
            except ConversationRuntimeError as error:
                if error.code != "duplicate_conversation_account":
                    raise
                conversation = self.repository.get_conversation_by_account(account_id)
                if conversation is None:
                    raise
        active_turns = tuple(
            self.repository.active_interactive_turns(conversation.id)
        )

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
                "interrupted_turn_trigger_ids": [
                    turn.trigger_id for turn in active_turns
                ],
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
        interrupted_turns = self._interrupt_turns(
            active_turns,
            reason_code="interrupted_by_newer_inbound",
        )
        return InboundRecordResult(
            conversation=updated_conversation,
            message=message,
            media=preserved_media,
            outbox=outbox,
            interrupted_turns=interrupted_turns,
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
            return TurnStartResult(
                turn=existing,
                replayed=True,
                input_messages=self._input_messages_for_turn(existing),
            )

        conversation = self._require_conversation(conversation_id)
        now = self._now()
        if mode == "interactive":
            input_from_seq = conversation.last_closed_inbound_seq + 1
            input_to_seq = conversation.latest_inbound_seq
            if input_to_seq < input_from_seq:
                raise ConversationRuntimeError("no_open_inbound_window")
            input_messages = self._input_messages_for_window(
                conversation_id,
                input_from_seq,
                input_to_seq,
            )
        else:
            input_from_seq = None
            input_to_seq = None
            input_messages = ()
        turn = Turn(
            id=self._id_factory("turn"),
            conversation_id=conversation_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            mode=mode,
            input_from_seq=input_from_seq,
            input_to_seq=input_to_seq,
            superseded_by_inbound_seq=None,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_turn(turn)
        return TurnStartResult(
            turn=turn,
            replayed=False,
            input_messages=input_messages,
        )

    def commit_reply(
        self,
        turn_id: str,
        segments: Sequence[str],
        reason_code: str = "reply_ready",
        materialize_staged_command: Callable[[StagedCommand], Any] | None = None,
    ) -> OutputDisposition:
        if not 1 <= len(segments) <= 3:
            raise ConversationRuntimeError("invalid_segment_count")
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "replied":
            return existing
        self._ensure_turn_can_transition(existing, target="replied")
        conversation = None
        if existing is None:
            conversation = self._ensure_turn_can_close(turn)

        now = self._now()
        if existing is None:
            self._materialize_staged_commands(
                turn,
                now,
                materialize_staged_command,
            )
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
        disposition = self._disposition_for_transition(
            existing,
            turn.id,
            "replied",
            reason_code,
        )
        self.repository.save_disposition(disposition)
        updated_turn = replace(turn, completed_at=now, updated_at=now)
        self._save_close_state(conversation, updated_turn, now)
        return disposition

    def commit_no_reply(
        self,
        turn_id: str,
        reason_code: str = "intentional_no_reply",
        materialize_staged_command: Callable[[StagedCommand], Any] | None = None,
    ) -> OutputDisposition:
        if reason_code != "intentional_no_reply":
            raise ConversationRuntimeError("invalid_no_reply_reason")
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "no_reply":
            return existing
        self._ensure_turn_can_transition(existing, target="no_reply")
        conversation = self._ensure_turn_can_close(turn)
        now = self._now()
        self._materialize_staged_commands(turn, now, materialize_staged_command)
        disposition = self._new_disposition(turn.id, "no_reply", reason_code)
        self.repository.save_disposition(disposition)
        self._save_close_state(
            conversation,
            replace(turn, completed_at=now, updated_at=now),
            now,
        )
        return disposition

    def mark_pending_async_reply(
        self,
        turn_id: str,
        reason_code: str = "sync_timeout",
        materialize_staged_command: Callable[[StagedCommand], Any] | None = None,
    ) -> OutputDisposition:
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "pending_async_reply":
            return existing
        self._ensure_turn_can_transition(existing, target="pending_async_reply")
        conversation = self._ensure_turn_can_close(turn)
        now = self._now()
        self._materialize_staged_commands(turn, now, materialize_staged_command)
        disposition = self._new_disposition(turn.id, "pending_async_reply", reason_code)
        self.repository.save_disposition(disposition)
        self._save_close_state(
            conversation,
            replace(turn, completed_at=now, updated_at=now),
            now,
        )
        return disposition

    def mark_failed(self, turn_id: str, reason_code: str) -> OutputDisposition:
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None and existing.disposition == "failed":
            return existing
        self._ensure_turn_can_transition(existing, target="failed")
        now = self._now()
        disposition = self._disposition_for_transition(
            existing,
            turn.id,
            "failed",
            reason_code,
        )
        self.repository.save_disposition(disposition)
        self.repository.save_turn(replace(turn, completed_at=now, updated_at=now))
        return disposition

    def mark_superseded(
        self,
        turn_id: str,
        reason_code: str = "interrupted_by_newer_inbound",
    ) -> OutputDisposition:
        turn = self._require_turn(turn_id)
        existing = self.repository.get_disposition(turn_id)
        if existing is not None:
            return existing
        return self._record_superseded(turn, reason_code)

    def interrupt_active_interactive_turns(
        self,
        conversation_id: str,
        reason_code: str = "interrupted_by_newer_inbound",
    ) -> tuple[Turn, ...]:
        self._require_conversation(conversation_id)
        return self._interrupt_turns(
            tuple(self.repository.active_interactive_turns(conversation_id)),
            reason_code=reason_code,
        )

    def guard_state_change(self, turn_id: str) -> None:
        turn = self._require_turn(turn_id)
        self._ensure_turn_can_close(turn)

    def stage_command(
        self,
        *,
        turn_id: str,
        domain: str,
        operation: str,
        command_payload: Mapping[str, Any],
        preview_facts: Mapping[str, Any],
        item_index: int,
    ) -> StagedCommand:
        turn = self._require_turn(turn_id)
        self._ensure_turn_can_close(turn)
        payload_digest = _payload_digest(command_payload)
        idempotency_key = (
            f"staged:{turn.conversation_id}:{turn.input_from_seq}:"
            f"{turn.input_to_seq}:{domain}:{operation}:{item_index}:"
            f"{payload_digest}"
        )
        for existing in self.repository.staged_commands_for_turn(turn_id):
            if existing.idempotency_key == idempotency_key:
                return existing
        now = self._now()
        command = StagedCommand(
            id=self._id_factory("staged_command"),
            turn_id=turn_id,
            domain=domain,
            operation=operation,
            idempotency_key=idempotency_key,
            command_payload=dict(command_payload),
            preview_facts=dict(preview_facts),
            status="staged",
            materialized_at=None,
            created_at=now,
            updated_at=now,
        )
        return self.repository.save_staged_command(command)

    def get_disposition(self, turn_id: str) -> OutputDisposition:
        disposition = self.repository.get_disposition(turn_id)
        if disposition is None:
            raise ConversationRuntimeError("disposition_not_found")
        return disposition

    def outbound_messages_for_turn(self, turn_id: str) -> list[Message]:
        self._require_turn(turn_id)
        return self.repository.outbound_messages_for_turn(turn_id)

    def recent_turns_with_messages(
        self, conversation_id: str, *, limit: int = 10
    ) -> list[tuple[Turn, tuple[CurrentInputMessage, ...], list[Message]]]:
        self._require_conversation(conversation_id)
        contexts: list[tuple[Turn, tuple[CurrentInputMessage, ...], list[Message]]] = []
        for turn_id in self.repository.latest_turn_ids(conversation_id, limit=limit):
            turn = self._require_turn(turn_id)
            contexts.append(
                (
                    turn,
                    self._input_messages_for_turn(turn),
                    self.repository.outbound_messages_for_turn(turn_id),
                )
            )
        return contexts

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

    def _ensure_turn_can_close(self, turn: Turn) -> Conversation:
        existing = self.repository.get_disposition(turn.id)
        if existing is not None and existing.disposition == "superseded":
            raise ConversationRuntimeError(
                "turn_superseded",
                fact={"turn_id": turn.id},
            )
        conversation = self._lock_conversation(turn.conversation_id)
        if turn.input_from_seq is None or turn.input_to_seq is None:
            return conversation
        if conversation.last_closed_inbound_seq != turn.input_from_seq - 1:
            self._record_superseded(turn, reason_code="window_already_closed")
            raise ConversationRuntimeError(
                "turn_superseded",
                fact={
                    "turn_id": turn.id,
                    "input_from_seq": turn.input_from_seq,
                    "last_closed_inbound_seq": conversation.last_closed_inbound_seq,
                },
            )
        if conversation.latest_inbound_seq != turn.input_to_seq:
            self._record_superseded(turn, reason_code="newer_inbound_seq")
            raise ConversationRuntimeError(
                "turn_superseded",
                fact={
                    "turn_id": turn.id,
                    "input_to_seq": turn.input_to_seq,
                    "latest_inbound_seq": conversation.latest_inbound_seq,
                },
            )
        return conversation

    def _save_close_state(
        self,
        conversation: Conversation | None,
        turn: Turn,
        now: datetime,
    ) -> None:
        if conversation is None or turn.input_to_seq is None:
            self.repository.save_turn(turn)
            return
        self.repository.save_conversation_and_turn(
            replace(
                conversation,
                last_closed_inbound_seq=turn.input_to_seq,
                updated_at=now,
            ),
            turn,
        )

    def _materialize_staged_commands(
        self,
        turn: Turn,
        now: datetime,
        materialize_staged_command: Callable[[StagedCommand], Any] | None,
    ) -> None:
        commands = self.repository.staged_commands_for_turn(turn.id)
        for command in commands:
            if command.status != "staged":
                continue
            if materialize_staged_command is None:
                raise ConversationRuntimeError("staged_command_materializer_missing")
            materialize_staged_command(command)
            self.repository.save_staged_command(
                replace(
                    command,
                    status="materialized",
                    materialized_at=now,
                    updated_at=now,
                )
            )

    def _input_messages_for_turn(
        self,
        turn: Turn,
    ) -> tuple[CurrentInputMessage, ...]:
        if turn.input_from_seq is None or turn.input_to_seq is None:
            return ()
        return self._input_messages_for_window(
            turn.conversation_id,
            turn.input_from_seq,
            turn.input_to_seq,
        )

    def _input_messages_for_window(
        self,
        conversation_id: str,
        input_from_seq: int,
        input_to_seq: int,
    ) -> tuple[CurrentInputMessage, ...]:
        return tuple(
            CurrentInputMessage(
                message_id=message.id,
                seq=message.seq,
                text=message.text,
                payload=dict(message.payload),
                causal_inbound_event_id=message.causal_inbound_event_id,
            )
            for message in self.repository.inbound_messages_for_window(
                conversation_id,
                input_from_seq,
                input_to_seq,
            )
            if message.seq is not None
        )

    def _record_superseded(self, turn: Turn, reason_code: str) -> OutputDisposition:
        existing = self.repository.get_disposition(turn.id)
        if existing is not None:
            return existing
        now = self._now()
        conversation = self._require_conversation(turn.conversation_id)
        for command in self.repository.staged_commands_for_turn(turn.id):
            if command.status == "staged":
                self.repository.save_staged_command(
                    replace(command, status="superseded", updated_at=now)
                )
        disposition = self._new_disposition(turn.id, "superseded", reason_code)
        self.repository.save_disposition(disposition)
        self.repository.save_turn(
            replace(
                turn,
                superseded_by_inbound_seq=conversation.latest_inbound_seq,
                completed_at=now,
                updated_at=now,
            )
        )
        return disposition

    def _interrupt_turns(
        self,
        turns: tuple[Turn, ...],
        *,
        reason_code: str,
    ) -> tuple[Turn, ...]:
        interrupted: list[Turn] = []
        for turn in turns:
            existing = self.repository.get_disposition(turn.id)
            if existing is not None:
                continue
            self._record_superseded(turn, reason_code)
            interrupted.append(turn)
        return tuple(interrupted)

    def _ensure_turn_can_transition(
        self,
        existing: OutputDisposition | None,
        target: str,
    ) -> None:
        if existing is None:
            return
        if existing.disposition == "superseded":
            raise ConversationRuntimeError(
                "turn_superseded",
                fact={"turn_id": existing.turn_id},
            )
        if existing.disposition == "pending_async_reply" and target in {
            "replied",
            "failed",
        }:
            return
        if existing.disposition in TERMINAL_DISPOSITIONS:
            raise ConversationRuntimeError("turn_already_terminal")
        raise ConversationRuntimeError("invalid_disposition_transition")

    def _disposition_for_transition(
        self,
        existing: OutputDisposition | None,
        turn_id: str,
        disposition: str,
        reason_code: str | None,
    ) -> OutputDisposition:
        if existing is None:
            return self._new_disposition(turn_id, disposition, reason_code)
        return replace(
            existing,
            disposition=disposition,
            reason_code=reason_code,
            updated_at=self._now(),
        )

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


def _payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _canonical_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_payload(item) for key, item in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_canonical_payload(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return repr(value)
