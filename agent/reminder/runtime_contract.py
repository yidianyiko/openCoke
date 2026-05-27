from __future__ import annotations

from datetime import date

from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderOccurrence,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)


class ReminderRuntimeContract:
    """In-process domain contract for reminder runtime adapters."""

    @staticmethod
    def validate_rrule(rrule_str: str) -> None:
        from agent.reminder.schedule import validate_rrule_subset

        validate_rrule_subset(rrule_str)

    @staticmethod
    def validate_timezone(tz: str) -> None:
        from agent.reminder.schedule import validate_timezone

        validate_timezone(tz)

    @staticmethod
    def validate_duration_minutes(duration_minutes: int | None) -> int | None:
        from agent.reminder.schedule import validate_duration_minutes

        return validate_duration_minutes(duration_minutes)

    def __init__(self, *, reminder_service=None) -> None:
        if reminder_service is None:
            from agent.reminder.service import ReminderService

            reminder_service = ReminderService()
        self.reminder_service = reminder_service

    def create_visible_reminder(
        self,
        *,
        owner_user_id: str,
        title: str,
        schedule: ReminderSchedule,
        target: AgentOutputTarget,
        metadata: dict | None = None,
    ) -> Reminder:
        command = ReminderCreateCommand(
            title=title,
            schedule=schedule,
            agent_output_target=target,
            created_by_system="agent",
            metadata=metadata,
        )
        return self.reminder_service.create(
            owner_user_id=owner_user_id,
            command=command,
        )

    def create_imported_reminder(
        self,
        *,
        owner_user_id: str,
        command: ReminderCreateCommand,
        import_metadata: dict,
    ) -> Reminder:
        return self.reminder_service.create_imported_reminder(
            owner_user_id=owner_user_id,
            command=command,
            import_metadata=import_metadata,
        )

    def record_historical_import(
        self,
        *,
        owner_user_id: str,
        title: str,
        schedule: ReminderSchedule,
        agent_output_target: AgentOutputTarget,
        import_metadata: dict,
    ) -> Reminder:
        return self.reminder_service.record_historical_import(
            owner_user_id=owner_user_id,
            title=title,
            schedule=schedule,
            agent_output_target=agent_output_target,
            import_metadata=import_metadata,
        )

    def find_imported_duplicate(
        self,
        *,
        owner_user_id: str,
        import_provider: str,
        source_event_id: str,
        source_original_start_time: str,
    ) -> dict | None:
        return self.reminder_service.find_imported_duplicate(
            owner_user_id=owner_user_id,
            import_provider=import_provider,
            source_event_id=source_event_id,
            source_original_start_time=source_original_start_time,
        )

    def find_visible_reminder_by_metadata_key(
        self, *, owner_user_id: str, key: str, value: str
    ) -> Reminder | None:
        return self.reminder_service.find_visible_by_metadata_key(
            owner_user_id=owner_user_id,
            key=key,
            value=value,
        )

    def update_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
        patch: ReminderPatch,
    ) -> Reminder:
        return self.reminder_service.update(
            owner_user_id=owner_user_id,
            reminder_id=reminder_id,
            patch=patch,
        )

    def cancel_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
    ) -> Reminder:
        return self.reminder_service.cancel(
            owner_user_id=owner_user_id,
            reminder_id=reminder_id,
        )

    def complete_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
    ) -> Reminder:
        return self.reminder_service.complete(
            owner_user_id=owner_user_id,
            reminder_id=reminder_id,
        )

    def list_visible_reminders(
        self,
        *,
        owner_user_id: str,
        query: ReminderQuery,
    ) -> list[Reminder]:
        return self.reminder_service.list_for_user(
            owner_user_id=owner_user_id,
            query=query,
        )

    def list_visible_reminders_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[Reminder]:
        return self.reminder_service.list_for_user_in_local_date_range(
            owner_user_id=owner_user_id,
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )

    def list_occupied_reminder_occurrences_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        timezone: str | None = None,
        lifecycle_states: list[str],
    ) -> list[ReminderOccurrence]:
        return self.reminder_service.list_occupied_occurrences_in_local_date_range(
            owner_user_id=owner_user_id,
            from_date=from_date,
            to_date=to_date,
            timezone=timezone,
            lifecycle_states=lifecycle_states,
        )

    def create_or_replace_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
        character_id: str,
        route_key: str | None,
        title: str,
        prompt: str,
        schedule: ReminderSchedule,
        metadata: dict | None = None,
    ) -> Reminder:
        return self.reminder_service.create_or_replace_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            character_id=character_id,
            route_key=route_key,
            title=title,
            prompt=prompt,
            schedule=schedule,
            metadata=metadata,
        )

    def clear_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> Reminder | None:
        return self.reminder_service.clear_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
        )
