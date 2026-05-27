from __future__ import annotations

from datetime import UTC, date, datetime, time

from agent.reminder.models import (
    AgentOutputTarget,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)
from agent.reminder.runtime_contract import ReminderRuntimeContract


class RecordingReminderService:
    def __init__(self) -> None:
        self.calls = []
        self.result = object()

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return self.result

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return self.result

    def cancel(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        return self.result

    def complete(self, **kwargs):
        self.calls.append(("complete", kwargs))
        return self.result

    def list_for_user(self, **kwargs):
        self.calls.append(("list_for_user", kwargs))
        return [self.result]

    def list_for_user_in_local_date_range(self, **kwargs):
        self.calls.append(("list_for_user_in_local_date_range", kwargs))
        return [self.result]

    def list_occupied_occurrences_in_local_date_range(self, **kwargs):
        self.calls.append(("list_occupied_occurrences_in_local_date_range", kwargs))
        return [self.result]

    def create_or_replace_internal_followup(self, **kwargs):
        self.calls.append(("create_or_replace_internal_followup", kwargs))
        return self.result

    def clear_internal_followup(self, **kwargs):
        self.calls.append(("clear_internal_followup", kwargs))
        return self.result

    def create_imported_reminder(self, **kwargs):
        self.calls.append(("create_imported_reminder", kwargs))
        return self.result

    def record_historical_import(self, **kwargs):
        self.calls.append(("record_historical_import", kwargs))
        return self.result

    def find_imported_duplicate(self, **kwargs):
        self.calls.append(("find_imported_duplicate", kwargs))
        return self.result


def sample_schedule() -> ReminderSchedule:
    return ReminderSchedule(
        anchor_at=datetime(2026, 5, 16, 1, 0, tzinfo=UTC),
        local_date=date(2026, 5, 16),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )


def sample_target() -> AgentOutputTarget:
    return AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="route-1",
    )


def test_create_visible_reminder_builds_visible_create_command():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    result = contract.create_visible_reminder(
        owner_user_id="user-1",
        title="weekly report",
        schedule=sample_schedule(),
        target=sample_target(),
        metadata={"projection_role": "requester"},
    )

    assert result is service.result
    assert service.calls[0][0] == "create"
    kwargs = service.calls[0][1]
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["command"].title == "weekly report"
    assert kwargs["command"].schedule == sample_schedule()
    assert kwargs["command"].agent_output_target == sample_target()
    assert kwargs["command"].created_by_system == "agent"
    assert kwargs["command"].metadata == {"projection_role": "requester"}


def test_visible_mutation_methods_delegate_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)
    patch = ReminderPatch(title="new title")
    query = ReminderQuery(lifecycle_states=["active"])

    assert (
        contract.update_visible_reminder(
            owner_user_id="user-1",
            reminder_id="rem-1",
            patch=patch,
        )
        is service.result
    )
    assert (
        contract.cancel_visible_reminder(
            owner_user_id="user-1",
            reminder_id="rem-1",
        )
        is service.result
    )
    assert (
        contract.complete_visible_reminder(
            owner_user_id="user-1",
            reminder_id="rem-1",
        )
        is service.result
    )
    assert contract.list_visible_reminders(
        owner_user_id="user-1",
        query=query,
    ) == [service.result]

    assert service.calls[0] == (
        "update",
        {"owner_user_id": "user-1", "reminder_id": "rem-1", "patch": patch},
    )
    assert service.calls[1] == (
        "cancel",
        {"owner_user_id": "user-1", "reminder_id": "rem-1"},
    )
    assert service.calls[2] == (
        "complete",
        {"owner_user_id": "user-1", "reminder_id": "rem-1"},
    )
    assert service.calls[3] == (
        "list_for_user",
        {"owner_user_id": "user-1", "query": query},
    )


def test_list_visible_reminders_in_local_date_range_delegates_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    result = contract.list_visible_reminders_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 5, 11),
        to_date=date(2026, 5, 17),
        lifecycle_states=["active"],
    )

    assert result == [service.result]
    assert service.calls == [
        (
            "list_for_user_in_local_date_range",
            {
                "owner_user_id": "user-1",
                "from_date": date(2026, 5, 11),
                "to_date": date(2026, 5, 17),
                "lifecycle_states": ["active"],
            },
        )
    ]


def test_list_occupied_reminder_occurrences_in_local_date_range_delegates_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    result = contract.list_occupied_reminder_occurrences_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 5, 11),
        to_date=date(2026, 5, 17),
        timezone="America/Los_Angeles",
        lifecycle_states=["active"],
    )

    assert result == [service.result]
    assert service.calls == [
        (
            "list_occupied_occurrences_in_local_date_range",
            {
                "owner_user_id": "user-1",
                "from_date": date(2026, 5, 11),
                "to_date": date(2026, 5, 17),
                "timezone": "America/Los_Angeles",
                "lifecycle_states": ["active"],
            },
        )
    ]


def test_internal_followup_methods_delegate_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    assert (
        contract.create_or_replace_internal_followup(
            owner_user_id="user-1",
            conversation_id="conv-1",
            character_id="char-1",
            route_key="route-1",
            title="check progress",
            prompt="Ask whether the user has started.",
            schedule=sample_schedule(),
            metadata={"proactive_times": 1},
        )
        is service.result
    )
    assert (
        contract.clear_internal_followup(
            owner_user_id="user-1",
            conversation_id="conv-1",
        )
        is service.result
    )

    assert service.calls[0] == (
        "create_or_replace_internal_followup",
        {
            "owner_user_id": "user-1",
            "conversation_id": "conv-1",
            "character_id": "char-1",
            "route_key": "route-1",
            "title": "check progress",
            "prompt": "Ask whether the user has started.",
            "schedule": sample_schedule(),
            "metadata": {"proactive_times": 1},
        },
    )
    assert service.calls[1] == (
        "clear_internal_followup",
        {"owner_user_id": "user-1", "conversation_id": "conv-1"},
    )


def test_calendar_import_methods_delegate_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)
    command = ReminderCreateCommand(
        title="imported event",
        schedule=sample_schedule(),
        agent_output_target=sample_target(),
        created_by_system="agent",
    )
    metadata = {
        "import_provider": "google_calendar",
        "source_event_id": "evt-1",
        "source_original_start_time": "2026-05-16T10:00:00",
    }

    assert (
        contract.create_imported_reminder(
            owner_user_id="user-1",
            command=command,
            import_metadata=metadata,
        )
        is service.result
    )
    assert (
        contract.record_historical_import(
            owner_user_id="user-1",
            title="past event",
            schedule=sample_schedule(),
            agent_output_target=sample_target(),
            import_metadata=metadata,
        )
        is service.result
    )
    assert (
        contract.find_imported_duplicate(
            owner_user_id="user-1",
            import_provider="google_calendar",
            source_event_id="evt-1",
            source_original_start_time="2026-05-16T10:00:00",
        )
        is service.result
    )

    assert service.calls == [
        (
            "create_imported_reminder",
            {
                "owner_user_id": "user-1",
                "command": command,
                "import_metadata": metadata,
            },
        ),
        (
            "record_historical_import",
            {
                "owner_user_id": "user-1",
                "title": "past event",
                "schedule": sample_schedule(),
                "agent_output_target": sample_target(),
                "import_metadata": metadata,
            },
        ),
        (
            "find_imported_duplicate",
            {
                "owner_user_id": "user-1",
                "import_provider": "google_calendar",
                "source_event_id": "evt-1",
                "source_original_start_time": "2026-05-16T10:00:00",
            },
        ),
    ]


def test_reminder_runtime_starts_loads_and_shuts_down_scheduler():
    from agent.reminder.runtime import ReminderRuntime

    class RecordingScheduler:
        def __init__(self):
            self.calls = []

        def start(self):
            self.calls.append("start")

        def load_from_storage(self):
            self.calls.append("load_from_storage")

        def shutdown(self):
            self.calls.append("shutdown")

    scheduler = RecordingScheduler()
    runtime = ReminderRuntime(
        contract=ReminderRuntimeContract(reminder_service=RecordingReminderService()),
        scheduler=scheduler,
        fire_consumer=object(),
    )

    runtime.start()
    runtime.load_from_storage()
    runtime.shutdown()

    assert scheduler.calls == ["start", "load_from_storage", "shutdown"]


def test_current_reminder_runtime_registry_is_used_by_default_service_scheduler():
    from agent.reminder.runtime import (
        ReminderRuntime,
        get_reminder_runtime_instance,
        set_reminder_runtime_instance,
    )
    from agent.reminder.service import ReminderService

    previous = get_reminder_runtime_instance()
    scheduler = object()
    runtime = ReminderRuntime(
        contract=ReminderRuntimeContract(reminder_service=RecordingReminderService()),
        scheduler=scheduler,
        fire_consumer=object(),
    )
    try:
        set_reminder_runtime_instance(runtime)
        service = ReminderService(reminder_dao=object())
        assert service.scheduler is scheduler
    finally:
        set_reminder_runtime_instance(previous)
