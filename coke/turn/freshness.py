from __future__ import annotations

from dataclasses import dataclass

from coke.domains.conversation_runtime.service import ConversationRuntimeService


@dataclass(frozen=True, slots=True)
class FreshnessGuard:
    conversation_runtime: ConversationRuntimeService
    turn_id: str
    based_on_inbound_seq: int | None

    def guard_state_change(self) -> None:
        self.conversation_runtime.guard_state_change(
            turn_id=self.turn_id,
            based_on_inbound_seq=self.based_on_inbound_seq,
        )
