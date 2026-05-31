from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

MessageDirection = Literal["inbound", "outbound"]
OutputDispositionState = Literal[
    "replied",
    "no_reply",
    "pending_async_reply",
    "failed",
    "superseded",
]

TERMINAL_DISPOSITIONS = frozenset({"replied", "no_reply", "failed", "superseded"})
NON_TERMINAL_DISPOSITIONS = frozenset({"pending_async_reply"})


class ConversationRuntimeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    account_id: str
    latest_inbound_seq: int
    last_closed_inbound_seq: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    conversation_id: str
    turn_id: str | None
    direction: MessageDirection
    segment_index: int | None
    seq: int | None
    channel_identity_id: str | None
    causal_inbound_event_id: str | None
    text: str | None
    payload: Mapping[str, Any]
    facts_hash: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class InboundMedia:
    id: str
    message_id: str
    media_type: str
    storage_uri: str
    processing_status: str
    agent_reference: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Turn:
    id: str
    conversation_id: str
    trigger_id: str
    trigger_type: str
    mode: str
    input_from_seq: int | None
    input_to_seq: int | None
    superseded_by_inbound_seq: int | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentInputMessage:
    message_id: str
    seq: int
    text: str | None
    payload: Mapping[str, Any]
    causal_inbound_event_id: str | None


@dataclass(frozen=True, slots=True)
class StagedCommand:
    id: str
    turn_id: str
    domain: str
    operation: str
    idempotency_key: str
    command_payload: Mapping[str, Any]
    preview_facts: Mapping[str, Any]
    status: Literal["staged", "materialized", "superseded"]
    materialized_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OutputDisposition:
    id: str
    turn_id: str
    disposition: OutputDispositionState
    reason_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    id: str
    topic: str
    idempotency_key: str
    payload: Mapping[str, Any]
    traceparent: str
    status: str
    created_at: datetime
    published_at: datetime | None
    processed_at: datetime | None
    acked_at: datetime | None
    retry_count: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class InboundMediaInput:
    media_type: str
    storage_uri: str
    agent_label: str


@dataclass(frozen=True, slots=True)
class InboundRecordResult:
    conversation: Conversation
    message: Message
    media: tuple[InboundMedia, ...]
    outbox: OutboxRecord


@dataclass(frozen=True, slots=True)
class TurnStartResult:
    turn: Turn
    replayed: bool
    input_messages: tuple[CurrentInputMessage, ...] = ()
