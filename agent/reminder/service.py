from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson.errors import InvalidId

from agent.reminder.errors import (
    InvalidArgument,
    InvalidOutputTarget,
    ReminderError,
    ReminderNotFound,
)
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCommand,
    ReminderCommandResult,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)
from agent.reminder.schedule import compute_initial_next_fire_at


class ReminderService:
    def __init__(
        self,
        reminder_dao=None,
        scheduler=None,
        now_provider=None,
    ) -> None:
        if reminder_dao is None:
            from dao.reminder_dao import ReminderDAO

            reminder_dao = ReminderDAO()

        self.reminder_dao = reminder_dao
        self.scheduler = scheduler
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        owner_user_id: str,
        command: ReminderCreateCommand,
    ) -> Reminder:
        self._validate_create_command(command)
        now = self._now()
        next_fire_at = compute_initial_next_fire_at(command.schedule, now)
        document = {
            "owner_user_id": owner_user_id,
            "title": command.title,
            "schedule": self._schedule_to_document(command.schedule),
            "agent_output_target": self._target_to_document(
                command.agent_output_target
            ),
            "created_by_system": "agent",
            "lifecycle_state": "active",
            "next_fire_at": next_fire_at,
            "last_fired_at": None,
            "last_event_ack_at": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "cancelled_at": None,
            "failed_at": None,
        }
        reminder_id = self.reminder_dao.insert_reminder(document)
        document["_id"] = reminder_id
        reminder = self._map_document(document)
        if reminder.next_fire_at is not None:
            self._call_scheduler("register_reminder", reminder)
        return reminder

    def update(
        self,
        *,
        reminder_id: str,
        owner_user_id: str,
        patch: ReminderPatch,
    ) -> Reminder:
        existing = self._get_document_for_owner(reminder_id, owner_user_id)
        self._ensure_active_for_mutation(existing, action="update")
        updates: dict[str, Any] = {"updated_at": self._now()}
        schedule_changed = patch.schedule is not None

        if patch.title is not None:
            self._validate_title(patch.title)
            updates["title"] = patch.title

        if patch.schedule is not None:
            updates["schedule"] = self._schedule_to_document(patch.schedule)
            if existing["lifecycle_state"] == "active":
                updates["next_fire_at"] = compute_initial_next_fire_at(
                    patch.schedule,
                    updates["updated_at"],
                )

        if not self.reminder_dao.replace_reminder(reminder_id, owner_user_id, updates):
            raise ReminderNotFound(
                "Reminder not found",
                detail={"reminder_id": reminder_id},
            )

        updated = self.get(reminder_id=reminder_id, owner_user_id=owner_user_id)
        if (
            schedule_changed
            and updated.lifecycle_state == "active"
            and updated.next_fire_at is not None
        ):
            self._call_scheduler("reschedule_reminder", updated)
        return updated

    def cancel(self, *, reminder_id: str, owner_user_id: str) -> Reminder:
        now = self._now()
        existing = self._get_document_for_owner(reminder_id, owner_user_id)
        self._ensure_active_for_mutation(existing, action="cancel")
        updates = {
            "lifecycle_state": "cancelled",
            "cancelled_at": now,
            "next_fire_at": None,
            "updated_at": now,
        }
        if not self.reminder_dao.replace_reminder(reminder_id, owner_user_id, updates):
            raise ReminderNotFound(
                "Reminder not found",
                detail={"reminder_id": reminder_id},
            )
        self._call_scheduler("remove_reminder", reminder_id)
        return self.get(reminder_id=reminder_id, owner_user_id=owner_user_id)

    def complete(self, *, reminder_id: str, owner_user_id: str) -> Reminder:
        now = self._now()
        existing = self._get_document_for_owner(reminder_id, owner_user_id)
        self._ensure_active_for_mutation(existing, action="complete")
        updates = {
            "lifecycle_state": "completed",
            "completed_at": now,
            "next_fire_at": None,
            "updated_at": now,
        }
        if not self.reminder_dao.replace_reminder(reminder_id, owner_user_id, updates):
            raise ReminderNotFound(
                "Reminder not found",
                detail={"reminder_id": reminder_id},
            )
        self._call_scheduler("remove_reminder", reminder_id)
        return self.get(reminder_id=reminder_id, owner_user_id=owner_user_id)

    def get(self, *, reminder_id: str, owner_user_id: str) -> Reminder:
        return self._map_document(
            self._get_document_for_owner(reminder_id, owner_user_id)
        )

    def list_for_user(
        self,
        *,
        owner_user_id: str,
        query: ReminderQuery,
    ) -> list[Reminder]:
        documents = self.reminder_dao.list_for_owner(
            owner_user_id,
            lifecycle_states=query.lifecycle_states,
        )
        return [self._map_document(document) for document in documents]

    def execute_batch(
        self,
        *,
        owner_user_id: str,
        commands: list[ReminderCommand],
    ) -> list[ReminderCommandResult]:
        results: list[ReminderCommandResult] = []
        for command in commands:
            try:
                results.append(self._execute_one(owner_user_id, command))
            except ReminderError as exc:
                results.append(
                    ReminderCommandResult(
                        ok=False,
                        action=command.action,
                        reminder=None,
                        reminders=None,
                        error=exc,
                    )
                )
        return results

    def _execute_one(
        self,
        owner_user_id: str,
        command: ReminderCommand,
    ) -> ReminderCommandResult:
        self._validate_command_shape(command)

        if command.action == "create":
            if command.create is None:
                raise InvalidArgument(
                    "Create reminder command requires create payload",
                    detail={"action": command.action},
                )
            reminder = self.create(owner_user_id=owner_user_id, command=command.create)
            return self._single_result(command.action, reminder)

        if command.action == "update":
            if command.reminder_id is None or command.patch is None:
                raise InvalidArgument(
                    "Update reminder command requires reminder_id and patch",
                    detail={"action": command.action},
                )
            reminder = self.update(
                reminder_id=command.reminder_id,
                owner_user_id=owner_user_id,
                patch=command.patch,
            )
            return self._single_result(command.action, reminder)

        if command.action == "cancel":
            if command.reminder_id is None:
                raise InvalidArgument(
                    "Cancel reminder command requires reminder_id",
                    detail={"action": command.action},
                )
            reminder = self.cancel(
                reminder_id=command.reminder_id,
                owner_user_id=owner_user_id,
            )
            return self._single_result(command.action, reminder)

        if command.action == "complete":
            if command.reminder_id is None:
                raise InvalidArgument(
                    "Complete reminder command requires reminder_id",
                    detail={"action": command.action},
                )
            reminder = self.complete(
                reminder_id=command.reminder_id,
                owner_user_id=owner_user_id,
            )
            return self._single_result(command.action, reminder)

        if command.action == "list":
            reminders = self.list_for_user(
                owner_user_id=owner_user_id,
                query=command.query or ReminderQuery(),
            )
            return ReminderCommandResult(
                ok=True,
                action=command.action,
                reminder=None,
                reminders=reminders,
                error=None,
            )

        raise InvalidArgument(
            "Unsupported reminder command action",
            detail={"action": command.action},
        )

    def _validate_command_shape(self, command: ReminderCommand) -> None:
        allowed_fields_by_action = {
            "create": {"create"},
            "update": {"reminder_id", "patch"},
            "cancel": {"reminder_id"},
            "complete": {"reminder_id"},
            "list": {"query"},
        }
        allowed_fields = allowed_fields_by_action.get(command.action)
        if allowed_fields is None:
            return

        present_fields = {
            field_name
            for field_name in ("reminder_id", "create", "patch", "query")
            if getattr(command, field_name) is not None
        }
        unexpected_fields = sorted(present_fields - allowed_fields)
        if unexpected_fields:
            raise InvalidArgument(
                "Reminder command has payload fields that do not match its action",
                detail={
                    "action": command.action,
                    "fields": unexpected_fields,
                },
            )

    def _single_result(
        self,
        action: str,
        reminder: Reminder,
    ) -> ReminderCommandResult:
        return ReminderCommandResult(
            ok=True,
            action=action,
            reminder=reminder,
            reminders=None,
            error=None,
        )

    def _get_document_for_owner(self, reminder_id: str, owner_user_id: str) -> dict:
        try:
            document = self.reminder_dao.get_reminder_for_owner(
                reminder_id, owner_user_id
            )
        except InvalidId as exc:
            raise ReminderNotFound(
                "Reminder not found",
                detail={"reminder_id": reminder_id},
            ) from exc
        if document is None:
            raise ReminderNotFound(
                "Reminder not found",
                detail={"reminder_id": reminder_id},
            )
        return document

    def _validate_create_command(self, command: ReminderCreateCommand) -> None:
        self._validate_title(command.title)
        self._validate_output_target(command.agent_output_target)

    def _validate_title(self, title: str) -> None:
        if not title:
            raise InvalidArgument(
                "Reminder title must be non-empty",
                detail={"field": "title"},
            )

    def _ensure_active_for_mutation(self, document: dict, *, action: str) -> None:
        if document["lifecycle_state"] == "active":
            return
        raise InvalidArgument(
            "Terminal reminder cannot be mutated",
            detail={
                "action": action,
                "lifecycle_state": document["lifecycle_state"],
            },
        )

    def _validate_output_target(self, target: AgentOutputTarget) -> None:
        if not target.conversation_id:
            raise InvalidOutputTarget(
                "Reminder output target conversation_id must be non-empty",
                detail={"field": "conversation_id"},
            )
        if not target.character_id:
            raise InvalidOutputTarget(
                "Reminder output target character_id must be non-empty",
                detail={"field": "character_id"},
            )

    def _map_document(self, document: dict) -> Reminder:
        schedule = document["schedule"]
        target = document["agent_output_target"]
        return Reminder(
            id=str(document["_id"]),
            owner_user_id=document["owner_user_id"],
            title=document["title"],
            schedule=ReminderSchedule(
                anchor_at=schedule["anchor_at"],
                local_date=schedule["local_date"],
                local_time=schedule["local_time"],
                timezone=schedule["timezone"],
                rrule=schedule.get("rrule"),
            ),
            agent_output_target=AgentOutputTarget(
                conversation_id=target["conversation_id"],
                character_id=target["character_id"],
                route_key=target.get("route_key"),
            ),
            created_by_system=document["created_by_system"],
            lifecycle_state=document["lifecycle_state"],
            next_fire_at=document.get("next_fire_at"),
            last_fired_at=document.get("last_fired_at"),
            last_event_ack_at=document.get("last_event_ack_at"),
            last_error=document.get("last_error"),
            created_at=document["created_at"],
            updated_at=document["updated_at"],
            completed_at=document.get("completed_at"),
            cancelled_at=document.get("cancelled_at"),
            failed_at=document.get("failed_at"),
        )

    def _schedule_to_document(self, schedule: ReminderSchedule) -> dict:
        return {
            "anchor_at": schedule.anchor_at,
            "local_date": schedule.local_date,
            "local_time": schedule.local_time,
            "timezone": schedule.timezone,
            "rrule": schedule.rrule,
        }

    def _target_to_document(self, target: AgentOutputTarget) -> dict:
        return {
            "conversation_id": target.conversation_id,
            "character_id": target.character_id,
            "route_key": target.route_key,
        }

    def _call_scheduler(self, method_name: str, *args) -> None:
        if self.scheduler is None:
            return
        method = getattr(self.scheduler, method_name, None)
        if method is None:
            return
        try:
            method(*args)
        except ReminderError:
            raise
        except Exception as exc:
            raise ReminderError(
                "Reminder scheduler hook failed",
                detail={"hook": method_name},
            ) from exc

    def _now(self) -> datetime:
        return self.now_provider()
