from __future__ import annotations

from dataclasses import dataclass

from coke.domains.conversation_runtime.service import ConversationRuntimeService


@dataclass(frozen=True, slots=True)
class FreshnessGuard:
    conversation_runtime: ConversationRuntimeService
    turn_id: str
    input_from_seq: int | None = None
    input_to_seq: int | None = None

    def guard_state_change(self) -> None:
        self.conversation_runtime.guard_state_change(turn_id=self.turn_id)
