from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent.reminder.errors import (
    InvalidArgument,
    InvalidOutputTarget,
    InvalidSchedule,
    RRULENotSupported,
    ReminderNotFound,
)
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderSchedule,
)
from agent.reminder.runtime_contract import ReminderRuntimeContract

_ALLOWED_LIFECYCLE_STATES = {"active", "completed", "cancelled", "failed"}
_MAX_LIST_RANGE_DAYS_INCLUSIVE = 31
_MAX_TITLE_LENGTH = 200


def serialize_reminder(reminder: Reminder) -> dict[str, Any]:
    return {
        "id": reminder.id,
        "ownerUserId": reminder.owner_user_id,
        "title": reminder.title,
        "schedule": {
            "anchorAt": _datetime_to_json(reminder.schedule.anchor_at),
            "localDate": reminder.schedule.local_date.isoformat(),
            "localTime": reminder.schedule.local_time.isoformat(),
            "timezone": reminder.schedule.timezone,
            "rrule": reminder.schedule.rrule,
            "durationMinutes": reminder.schedule.duration_minutes,
        },
        "agentOutputTarget": {
            "conversationId": reminder.agent_output_target.conversation_id,
            "characterId": reminder.agent_output_target.character_id,
            "routeKey": reminder.agent_output_target.route_key,
        },
        "createdBySystem": reminder.created_by_system,
        "metadata": reminder.metadata or {},
        "lifecycleState": reminder.lifecycle_state,
        "nextFireAt": _datetime_to_json(reminder.next_fire_at),
        "lastFiredAt": _datetime_to_json(reminder.last_fired_at),
        "lastEventAckAt": _datetime_to_json(reminder.last_event_ack_at),
        "lastError": reminder.last_error,
        "createdAt": _datetime_to_json(reminder.created_at),
        "updatedAt": _datetime_to_json(reminder.updated_at),
        "completedAt": _datetime_to_json(reminder.completed_at),
        "cancelledAt": _datetime_to_json(reminder.cancelled_at),
        "failedAt": _datetime_to_json(reminder.failed_at),
    }


def build_schedule(
    *,
    local_date: str,
    local_time: str,
    timezone: str,
    rrule: str | None = None,
    duration_minutes: int | None = None,
) -> ReminderSchedule:
    parsed_date = _parse_local_date(local_date)
    parsed_time = _parse_local_time(local_time)
    try:
        ReminderRuntimeContract.validate_timezone(timezone)
        if rrule is not None:
            ReminderRuntimeContract.validate_rrule(rrule)
        duration_minutes = ReminderRuntimeContract.validate_duration_minutes(
            duration_minutes
        )
        local_zone = ZoneInfo(timezone)
    except (InvalidSchedule, RRULENotSupported, ZoneInfoNotFoundError) as exc:
        raise ValueError("invalid_schedule") from exc

    local_anchor = datetime.combine(parsed_date, parsed_time, tzinfo=local_zone)
    return ReminderSchedule(
        anchor_at=local_anchor.astimezone(UTC),
        local_date=parsed_date,
        local_time=parsed_time,
        timezone=timezone,
        rrule=rrule,
        duration_minutes=duration_minutes,
    )


class ReminderManagementService:
    def __init__(
        self,
        *,
        reminder_runtime=None,
        conversation_dao=None,
        character_id_provider=None,
        now_provider=None,
    ) -> None:
        if reminder_runtime is None:
            reminder_runtime = ReminderRuntimeContract()
        if conversation_dao is None:
            from dao.conversation_dao import ConversationDAO

            conversation_dao = ConversationDAO()
        if character_id_provider is None:
            from agent.role.bootstrap import ensure_default_character_seeded

            character_id_provider = ensure_default_character_seeded

        self.reminder_runtime = reminder_runtime
        self.conversation_dao = conversation_dao
        self.character_id_provider = character_id_provider
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def list_reminders(
        self,
        *,
        customer_id: str,
        from_date: str,
        to_date: str,
        lifecycle_states: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            parsed_from_date = _parse_local_date(from_date)
            parsed_to_date = _parse_local_date(to_date)
            parsed_states = _validate_lifecycle_states(lifecycle_states)
            if parsed_from_date > parsed_to_date:
                raise ValueError("invalid_body")
            if (
                parsed_to_date - parsed_from_date
            ).days + 1 > _MAX_LIST_RANGE_DAYS_INCLUSIVE:
                raise ValueError("invalid_body")
            reminders = (
                self.reminder_runtime.list_visible_reminders_in_local_date_range(
                    owner_user_id=_require_string(customer_id, "customer_id"),
                    from_date=parsed_from_date,
                    to_date=parsed_to_date,
                    lifecycle_states=parsed_states,
                )
            )
        except InvalidArgument as exc:
            raise ValueError("invalid_body") from exc
        return [serialize_reminder(reminder) for reminder in reminders]

    def create_reminder(
        self, *, customer_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ValueError("invalid_body")
        customer_id = _require_string(customer_id, "customer_id")
        metadata = _validate_optional_metadata(body.get("metadata"))
        character_id = _require_string(
            body.get("characterId") or self.character_id_provider(),
            "character_id",
        )
        conversation = self._find_business_conversation(
            character_id=character_id,
            business_conversation_key=body.get("businessConversationKey")
            or body.get("business_conversation_key"),
            gateway_conversation_id=body.get("gatewayConversationId")
            or body.get("gateway_conversation_id"),
        )
        if not conversation:
            conversation = (
                self.conversation_dao.find_latest_private_conversation_by_db_user_ids(
                    customer_id,
                    character_id,
                )
            )
        if not conversation:
            raise ValueError("conversation_required")

        command = ReminderCreateCommand(
            title=_validate_title(body.get("title")),
            schedule=self._build_schedule_from_body(body),
            agent_output_target=AgentOutputTarget(
                conversation_id=str(conversation["_id"]),
                character_id=character_id,
                route_key=_conversation_route_key(conversation),
            ),
            created_by_system="agent",
            metadata=metadata,
        )
        try:
            reminder = self.reminder_runtime.create_visible_reminder(
                owner_user_id=customer_id,
                title=command.title,
                schedule=command.schedule,
                target=command.agent_output_target,
                metadata=command.metadata,
            )
        except (InvalidSchedule, RRULENotSupported) as exc:
            raise ValueError("invalid_schedule") from exc
        except (InvalidArgument, InvalidOutputTarget) as exc:
            raise ValueError("invalid_reminder") from exc
        return serialize_reminder(reminder)

    def update_reminder(
        self,
        *,
        customer_id: str,
        reminder_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ValueError("invalid_body")
        schedule = None
        if any(
            key in body
            for key in (
                "localDate",
                "localTime",
                "timezone",
                "rrule",
                "durationMinutes",
            )
        ):
            schedule = self._build_schedule_from_body(body)
        patch = ReminderPatch(
            title=_validate_optional_title(body.get("title")),
            schedule=schedule,
        )
        try:
            reminder = self.reminder_runtime.update_visible_reminder(
                reminder_id=_require_string(reminder_id, "reminder_id"),
                owner_user_id=_require_string(customer_id, "customer_id"),
                patch=patch,
            )
        except (InvalidSchedule, RRULENotSupported) as exc:
            raise ValueError("invalid_schedule") from exc
        except ReminderNotFound as exc:
            raise ValueError("reminder_not_found") from exc
        except (InvalidArgument, InvalidOutputTarget) as exc:
            raise ValueError("invalid_reminder") from exc
        return serialize_reminder(reminder)

    def complete_reminder(
        self, *, customer_id: str, reminder_id: str
    ) -> dict[str, Any]:
        try:
            reminder = self.reminder_runtime.complete_visible_reminder(
                owner_user_id=_require_string(customer_id, "customer_id"),
                reminder_id=_require_string(reminder_id, "reminder_id"),
            )
        except ReminderNotFound as exc:
            raise ValueError("reminder_not_found") from exc
        except InvalidArgument as exc:
            raise ValueError("invalid_reminder") from exc
        return serialize_reminder(reminder)

    def cancel_reminder(self, *, customer_id: str, reminder_id: str) -> dict[str, Any]:
        try:
            reminder = self.reminder_runtime.cancel_visible_reminder(
                owner_user_id=_require_string(customer_id, "customer_id"),
                reminder_id=_require_string(reminder_id, "reminder_id"),
            )
        except ReminderNotFound as exc:
            raise ValueError("reminder_not_found") from exc
        except InvalidArgument as exc:
            raise ValueError("invalid_reminder") from exc
        return serialize_reminder(reminder)

    def _build_schedule_from_body(self, body: dict[str, Any]) -> ReminderSchedule:
        try:
            schedule = build_schedule(
                local_date=_require_string(body.get("localDate"), "localDate"),
                local_time=_require_string(body.get("localTime"), "localTime"),
                timezone=_require_string(body.get("timezone"), "timezone"),
                rrule=_optional_string(body.get("rrule")),
                duration_minutes=_validate_optional_duration_minutes(
                    body.get("durationMinutes")
                ),
            )
        except ValueError as exc:
            if str(exc) == "invalid_schedule":
                raise
            raise ValueError("invalid_body") from exc
        if schedule.rrule is None and schedule.anchor_at <= self.now_provider():
            raise ValueError("invalid_schedule")
        return schedule

    def _find_business_conversation(
        self,
        *,
        character_id: str,
        business_conversation_key: str | None,
        gateway_conversation_id: str | None,
    ) -> dict[str, Any] | None:
        get_private_conversation = getattr(
            self.conversation_dao,
            "get_private_conversation",
            None,
        )
        if not callable(get_private_conversation):
            return None

        character_platform_id = f"clawscale-character:{character_id}"
        for candidate in (business_conversation_key, gateway_conversation_id):
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            conversation = get_private_conversation(
                "business",
                f"clawscale:{candidate.strip()}",
                character_platform_id,
            )
            if conversation:
                return conversation
        return None


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _parse_local_date(value: Any) -> date:
    try:
        return date.fromisoformat(_require_string(value, "date"))
    except ValueError as exc:
        raise ValueError("invalid_body") from exc


def _parse_local_time(value: Any) -> time:
    try:
        return time.fromisoformat(_require_string(value, "time"))
    except ValueError as exc:
        raise ValueError("invalid_body") from exc


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid_body")
    return value.strip()


def _validate_title(value: Any) -> str:
    title = _require_string(value, "title")
    if len(title) > _MAX_TITLE_LENGTH:
        raise ValueError("invalid_body")
    return title


def _validate_optional_title(value: Any) -> str | None:
    if value is None:
        return None
    return _validate_title(value)


def _validate_lifecycle_states(values: list[str] | None) -> list[str]:
    if values is None:
        return ["active"]
    if not isinstance(values, list):
        raise ValueError("invalid_body")
    states = []
    for value in values:
        state = _require_string(value, "state")
        if state not in _ALLOWED_LIFECYCLE_STATES:
            raise ValueError("invalid_body")
        states.append(state)
    return states or ["active"]


def _validate_optional_metadata(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid_body")
    return dict(value)


def _validate_optional_duration_minutes(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("invalid_body")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _conversation_route_key(conversation: dict[str, Any]) -> str | None:
    conversation_info = conversation.get("conversation_info")
    if not isinstance(conversation_info, dict):
        conversation_info = {}

    for value in (
        conversation.get("route_key"),
        conversation_info.get("route_key"),
        conversation_info.get("delivery_route_key"),
        conversation.get("business_conversation_key"),
        conversation_info.get("business_conversation_key"),
    ):
        route_key = _optional_string(value)
        if route_key:
            return route_key
    return None
