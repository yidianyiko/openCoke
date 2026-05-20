from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from agent.agno_agent.runtime._immutability import freeze_mapping, freeze_sequence


@dataclass(frozen=True)
class UserTurnPayload:
    current_message_ids: Sequence[str] = field(default_factory=tuple)
    check_new_message: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "current_message_ids",
            freeze_sequence(self.current_message_ids),
        )
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class ReminderFirePayload:
    fire_id: str
    reminder_id: str
    title: str
    scheduled_for: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class AgentInput:
    input_type: Literal["user.turn", "reminder.fired"]
    conversation_id: str
    text: str | None
    payload: UserTurnPayload | ReminderFirePayload
    occurred_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        expected_payload_type = {
            "user.turn": UserTurnPayload,
            "reminder.fired": ReminderFirePayload,
        }.get(self.input_type)
        if expected_payload_type is None:
            raise ValueError(f"Unsupported agent input type: {self.input_type}")
        if not isinstance(self.payload, expected_payload_type):
            raise TypeError(
                f"AgentInput payload for {self.input_type} must be "
                f"{expected_payload_type.__name__}"
            )
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
