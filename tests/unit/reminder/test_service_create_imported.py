from datetime import UTC, date, datetime, time
from unittest.mock import Mock

from agent.reminder.models import (
    AgentOutputTarget,
    ReminderCreateCommand,
    ReminderSchedule,
)
from agent.reminder.service import ReminderService


NOW = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
FUTURE = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)


class InMemoryReminderDAO:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def insert_reminder(self, document: dict) -> str:
        reminder_id = "rem-1"
        self.documents[reminder_id] = {**document, "_id": reminder_id}
        return reminder_id


def test_create_imported_reminder_writes_metadata_and_registers_scheduler():
    dao = InMemoryReminderDAO()
    scheduler = Mock()
    service = ReminderService(
        reminder_dao=dao,
        scheduler=scheduler,
        now_provider=lambda: NOW,
    )

    reminder = service.create_imported_reminder(
        owner_user_id="user-1",
        command=ReminderCreateCommand(
            title="Team sync",
            schedule=ReminderSchedule(
                anchor_at=FUTURE,
                local_date=date(2026, 4, 29),
                local_time=time(10, 0),
                timezone="Asia/Tokyo",
                rrule=None,
            ),
            agent_output_target=AgentOutputTarget(
                conversation_id="conv-1",
                character_id="char-1",
                route_key=None,
            ),
            created_by_system="agent",
        ),
        import_metadata={
            "import_provider": "google_calendar",
            "source_event_id": "evt-1",
            "source_original_start_time": "2026-04-29T10:00:00",
        },
    )

    assert reminder.id == "rem-1"
    assert reminder.lifecycle_state == "active"
    assert reminder.next_fire_at == FUTURE
    assert reminder.metadata == {
        "import_provider": "google_calendar",
        "source_event_id": "evt-1",
        "source_original_start_time": "2026-04-29T10:00:00",
    }
    assert dao.documents["rem-1"]["metadata"] == reminder.metadata
    scheduler.register_reminder.assert_called_once_with(reminder)
