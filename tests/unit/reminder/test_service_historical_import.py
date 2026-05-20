from datetime import UTC, date, datetime, time
from unittest.mock import Mock

from agent.reminder.models import AgentOutputTarget, ReminderSchedule
from agent.reminder.service import ReminderService


NOW = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
PAST = datetime(2026, 4, 27, 1, 0, tzinfo=UTC)


class InMemoryReminderDAO:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def insert_reminder(self, document: dict) -> str:
        reminder_id = "rem-1"
        self.documents[reminder_id] = {**document, "_id": reminder_id}
        return reminder_id


def test_record_historical_import_completes_without_scheduler_registration():
    dao = InMemoryReminderDAO()
    scheduler = Mock()
    service = ReminderService(
        reminder_dao=dao,
        scheduler=scheduler,
        now_provider=lambda: NOW,
    )

    reminder = service.record_historical_import(
        owner_user_id="user-1",
        title="Past event",
        schedule=ReminderSchedule(
            anchor_at=PAST,
            local_date=date(2026, 4, 27),
            local_time=time(10, 0),
            timezone="Asia/Tokyo",
            rrule=None,
        ),
        agent_output_target=AgentOutputTarget(
            conversation_id="conv-1",
            character_id="char-1",
            route_key=None,
        ),
        import_metadata={
            "import_provider": "google_calendar",
            "source_event_id": "evt-old",
            "source_original_start_time": "2026-04-27T10:00:00",
        },
    )

    assert reminder.lifecycle_state == "completed"
    assert reminder.completed_at == NOW
    assert reminder.next_fire_at is None
    assert reminder.metadata == {
        "import_provider": "google_calendar",
        "source_event_id": "evt-old",
        "source_original_start_time": "2026-04-27T10:00:00",
    }
    assert dao.documents["rem-1"]["completed_at"] == NOW
    scheduler.register_reminder.assert_not_called()
