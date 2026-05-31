from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from coke.domains.conversation_runtime.service import ConversationRuntimeService


@dataclass(frozen=True, slots=True)
class FreshnessGuard:
    conversation_runtime: ConversationRuntimeService
    turn_id: str
    input_from_seq: int | None = None
    input_to_seq: int | None = None

    def guard_state_change(self) -> None:
        self.conversation_runtime.guard_state_change(turn_id=self.turn_id)

    def stage_command(
        self,
        *,
        domain: str,
        operation: str,
        command_payload: Mapping[str, Any],
        preview_facts: Mapping[str, Any],
        item_index: int,
    ) -> Any:
        return self.conversation_runtime.stage_command(
            turn_id=self.turn_id,
            domain=domain,
            operation=operation,
            command_payload=command_payload,
            preview_facts=preview_facts,
            item_index=item_index,
        )
