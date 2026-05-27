from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent.reminder.errors import InvalidArgument, InvalidOutputTarget
from agent.reminder.models import AgentOutputTarget, ReminderSchedule
from agent.reminder.runtime import get_reminder_runtime_instance
from agent.reminder.runtime_contract import ReminderRuntimeContract
from util.time_util import get_default_timezone


@dataclass(frozen=True)
class CokeReminderContext:
    owner_user_id: str
    target: AgentOutputTarget
    timezone: str
    current_time: datetime | None


@dataclass(frozen=True)
class CokeReminderFollowupScope:
    owner_user_id: str
    conversation_id: str


class CokeReminderAdapter:
    def derive_context(self, session_state: dict[str, Any]) -> CokeReminderContext:
        user = session_state.get("user") or {}
        character = session_state.get("character") or {}
        conversation = session_state.get("conversation") or {}
        conversation_info = conversation.get("conversation_info") or {}

        owner_user_id = self._string_value(user.get("id") or user.get("_id"))
        character_id = self._string_value(character.get("_id") or character.get("id"))
        conversation_id = self._string_value(
            conversation.get("_id")
            or conversation.get("id")
            or session_state.get("conversation_id")
        )
        route_key = (
            session_state.get("route_key")
            or session_state.get("delivery_route_key")
            or conversation.get("route_key")
            or conversation.get("delivery_route_key")
            or conversation.get("business_conversation_key")
            or conversation_info.get("route_key")
            or conversation_info.get("delivery_route_key")
            or conversation_info.get("business_conversation_key")
        )
        timezone = self._string_value(
            user.get("effective_timezone")
            or user.get("timezone")
            or get_default_timezone().key
        )

        if not owner_user_id:
            raise InvalidArgument(
                "Reminder owner_user_id is missing",
                detail={"field": "owner_user_id"},
            )
        if not conversation_id:
            raise InvalidOutputTarget(
                "Reminder output target conversation_id must be non-empty",
                detail={"field": "conversation_id"},
            )
        if not character_id:
            raise InvalidOutputTarget(
                "Reminder output target character_id must be non-empty",
                detail={"field": "character_id"},
            )

        return CokeReminderContext(
            owner_user_id=owner_user_id,
            target=AgentOutputTarget(
                conversation_id=conversation_id,
                character_id=character_id,
                route_key=self._string_value(route_key) if route_key else None,
            ),
            timezone=timezone,
            current_time=self.parse_current_time(session_state.get("current_time")),
        )

    def reminder_contract(
        self, session_state: dict[str, Any]
    ) -> ReminderRuntimeContract:
        runtime = get_reminder_runtime_instance()
        if runtime is None:
            raise RuntimeError(
                "Reminder runtime is not initialized; "
                "call set_reminder_runtime_instance() during boot or test setup."
            )
        return runtime.contract

    def create_or_replace_internal_followup(
        self,
        *,
        session_state: dict[str, Any],
        title: str,
        prompt: str,
        schedule: ReminderSchedule,
        metadata: dict | None = None,
    ):
        context = self.derive_context(session_state)
        return self.reminder_contract(
            session_state
        ).create_or_replace_internal_followup(
            owner_user_id=context.owner_user_id,
            conversation_id=context.target.conversation_id,
            character_id=context.target.character_id,
            route_key=context.target.route_key,
            title=title,
            prompt=prompt,
            schedule=schedule,
            metadata=metadata,
        )

    def clear_internal_followup(self, *, session_state: dict[str, Any]):
        scope = self.derive_followup_scope(session_state)
        return self.reminder_contract(session_state).clear_internal_followup(
            owner_user_id=scope.owner_user_id,
            conversation_id=scope.conversation_id,
        )

    def derive_followup_scope(
        self,
        session_state: dict[str, Any],
    ) -> CokeReminderFollowupScope:
        user = session_state.get("user") or {}
        conversation = session_state.get("conversation") or {}
        owner_user_id = self._string_value(user.get("id") or user.get("_id"))
        conversation_id = self._string_value(
            conversation.get("_id")
            or conversation.get("id")
            or session_state.get("conversation_id")
        )
        if not owner_user_id:
            raise InvalidArgument(
                "Reminder owner_user_id is missing",
                detail={"field": "owner_user_id"},
            )
        if not conversation_id:
            raise InvalidOutputTarget(
                "Reminder output target conversation_id must be non-empty",
                detail={"field": "conversation_id"},
            )
        return CokeReminderFollowupScope(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
        )

    def parse_current_time(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    def _string_value(self, value: Any) -> str:
        return "" if value is None else str(value)
