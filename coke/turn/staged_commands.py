from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from coke.domains.conversation_runtime.models import StagedCommand


@dataclass(frozen=True, slots=True)
class MaterializedCommand:
    staged_command_id: str
    facts: Mapping[str, Any]


class StagedCommandMaterializer:
    def __init__(
        self,
        *,
        reminder_tool: Any,
        social_scheduling_tool: Any,
        calendar_import_tool: Any,
        identity_access_tool: Any,
        settings_tool: Any,
    ) -> None:
        self._tools = {
            "reminder": reminder_tool,
            "social_scheduling": social_scheduling_tool,
            "calendar_import": calendar_import_tool,
            "identity_access": identity_access_tool,
            "settings": settings_tool,
        }

    def materialize(self, command: StagedCommand, guard: Any) -> MaterializedCommand:
        tool = self._tools.get(command.domain)
        if tool is None:
            raise RuntimeError(f"staged_command_domain_unsupported:{command.domain}")
        result = tool.execute_without_staging(command.command_payload, guard)
        if not result.ok:
            raise RuntimeError(
                result.reason_code or "staged_command_materialization_failed"
            )
        return MaterializedCommand(staged_command_id=command.id, facts=result.facts)
