from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class UserTurnPayload:
    current_message_ids: list[str] = field(default_factory=list)
    check_new_message: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReminderFirePayload:
    fire_id: str
    reminder_id: str
    title: str
    scheduled_for: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeferredActionPayload:
    action_id: str
    kind: str
    scheduled_for: datetime
    revision: int
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInput:
    input_type: Literal["user.turn", "reminder.fired", "deferred_action.fire"]
    conversation_id: str
    text: str | None
    payload: UserTurnPayload | ReminderFirePayload | DeferredActionPayload
    occurred_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
