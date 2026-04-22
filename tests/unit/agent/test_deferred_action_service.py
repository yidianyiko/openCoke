import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest


apscheduler_module = types.ModuleType("apscheduler")
apscheduler_jobstores_module = types.ModuleType("apscheduler.jobstores")
apscheduler_jobstores_base_module = types.ModuleType("apscheduler.jobstores.base")
apscheduler_schedulers_module = types.ModuleType("apscheduler.schedulers")
apscheduler_schedulers_asyncio_module = types.ModuleType("apscheduler.schedulers.asyncio")


class _JobLookupError(Exception):
    pass


class _AsyncIOScheduler:
    def __init__(self, *args, **kwargs):
        pass


apscheduler_jobstores_base_module.JobLookupError = _JobLookupError
apscheduler_schedulers_asyncio_module.AsyncIOScheduler = _AsyncIOScheduler
sys.modules.setdefault("apscheduler", apscheduler_module)
sys.modules.setdefault("apscheduler.jobstores", apscheduler_jobstores_module)
sys.modules.setdefault("apscheduler.jobstores.base", apscheduler_jobstores_base_module)
sys.modules.setdefault("apscheduler.schedulers", apscheduler_schedulers_module)
sys.modules.setdefault(
    "apscheduler.schedulers.asyncio", apscheduler_schedulers_asyncio_module
)

service_spec = importlib.util.spec_from_file_location(
    "test_deferred_action_service_module",
    Path(__file__).resolve().parents[3]
    / "agent"
    / "agno_agent"
    / "tools"
    / "deferred_action"
    / "service.py",
)
service_module = importlib.util.module_from_spec(service_spec)
assert service_spec.loader is not None
service_spec.loader.exec_module(service_module)


def build_action(**overrides):
    action = {
        "_id": "action-1",
        "conversation_id": "conv-1",
        "user_id": "user-1",
        "character_id": "char-1",
        "kind": "user_reminder",
        "source": "user_explicit",
        "visibility": "visible",
        "lifecycle_state": "active",
        "revision": 2,
        "title": "喝水",
        "payload": {"prompt": "提醒用户喝水"},
        "timezone": "UTC",
        "dtstart": datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        "rrule": None,
        "next_run_at": datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        "run_count": 0,
        "max_runs": None,
        "expires_at": None,
        "retry_policy": {
            "max_attempts_per_occurrence": 3,
            "base_backoff_seconds": 60,
            "max_backoff_seconds": 900,
        },
        "lease": {
            "token": None,
            "leased_at": None,
            "lease_expires_at": None,
        },
        "last_error": None,
        "created_at": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
    }
    action.update(overrides)
    return action


class TestDeferredActionService:
    def test_create_imported_future_reminder_is_active_and_visible(self):
        now = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
        action_dao = Mock(create_action=Mock(return_value="action-1"))
        scheduler = Mock(register_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        action = service.create_imported_future_reminder(
            user_id="ck_1",
            character_id="char_1",
            conversation_id="conv_1",
            title="Tomorrow meeting",
            dtstart=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
            timezone="UTC",
            metadata={
                "import_provider": "google_calendar",
                "source_event_id": "evt_1",
                "source_original_start_time": "2026-04-23T09:00:00Z",
            },
        )

        assert action["_id"] == "action-1"
        assert action["source"] == "google_calendar_import"
        assert action["lifecycle_state"] == "active"
        assert action["next_run_at"] == datetime(2026, 4, 23, 9, 0, tzinfo=UTC)
        assert action["payload"]["metadata"]["import_provider"] == "google_calendar"
        scheduler.register_action.assert_called_once_with(action)

    def test_create_visible_one_shot_reminder(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        action_dao = Mock(create_action=Mock(return_value="action-1"))
        scheduler = Mock(register_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        action = service.create_visible_reminder(
            user_id="user-1",
            character_id="char-1",
            conversation_id="conv-1",
            title="喝水",
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            timezone="UTC",
        )

        assert action["_id"] == "action-1"
        assert action["kind"] == "user_reminder"
        assert action["visibility"] == "visible"
        assert action["next_run_at"] == datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        scheduler.register_action.assert_called_once_with(action)

    def test_create_visible_recurring_rrule_reminder(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        action_dao = Mock(create_action=Mock(return_value="action-1"))
        scheduler = Mock(register_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        action = service.create_visible_reminder(
            user_id="user-1",
            character_id="char-1",
            conversation_id="conv-1",
            title="早提醒",
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            timezone="UTC",
            rrule="FREQ=DAILY",
        )

        assert action["rrule"] == "FREQ=DAILY"
        assert action["next_run_at"] == datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

    def test_create_imported_historical_reminder_uses_completed_lifecycle(self):
        action_dao = Mock(create_action=Mock(return_value="action-1"))
        scheduler = Mock()
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
        )

        action = service.create_imported_historical_reminder(
            user_id="ck_1",
            character_id="char_1",
            conversation_id="conv_1",
            title="Yesterday meeting",
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            timezone="UTC",
            metadata={
                "import_provider": "google_calendar",
                "source_event_id": "evt_2",
                "source_original_start_time": "2026-04-21T09:00:00Z",
            },
        )

        assert action["source"] == "google_calendar_import"
        assert action["lifecycle_state"] == "completed"
        assert action["next_run_at"] is None
        scheduler.register_action.assert_not_called()

    def test_create_imported_recurring_reminder_seeds_first_future_occurrence(self):
        now = datetime(2026, 4, 22, 10, 0, tzinfo=UTC)
        action_dao = Mock(create_action=Mock(return_value="action-1"))
        scheduler = Mock(register_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        action = service.create_imported_recurring_reminder(
            user_id="ck_1",
            character_id="char_1",
            conversation_id="conv_1",
            title="Daily standup",
            dtstart=datetime(2026, 4, 20, 9, 0, tzinfo=UTC),
            timezone="UTC",
            rrule="FREQ=DAILY",
            metadata={
                "import_provider": "google_calendar",
                "source_event_id": "evt_3",
                "source_original_start_time": "2026-04-20T09:00:00Z",
            },
        )

        assert action["source"] == "google_calendar_import"
        assert action["rrule"] == "FREQ=DAILY"
        assert action["next_run_at"] == datetime(2026, 4, 23, 9, 0, tzinfo=UTC)
        scheduler.register_action.assert_called_once_with(action)

    def test_create_imported_exhausted_recurring_reminder_is_completed_without_schedule(self):
        now = datetime(2026, 4, 22, 10, 0, tzinfo=UTC)
        action_dao = Mock(create_action=Mock(return_value="action-1"))
        scheduler = Mock(register_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        action = service.create_imported_recurring_reminder(
            user_id="ck_1",
            character_id="char_1",
            conversation_id="conv_1",
            title="Expired daily standup",
            dtstart=datetime(2026, 4, 20, 9, 0, tzinfo=UTC),
            timezone="UTC",
            rrule="FREQ=DAILY;COUNT=2",
            metadata={
                "import_provider": "google_calendar",
                "source_event_id": "evt_4",
                "source_original_start_time": "2026-04-20T09:00:00Z",
            },
        )

        assert action["source"] == "google_calendar_import"
        assert action["lifecycle_state"] == "completed"
        assert action["next_run_at"] is None
        scheduler.register_action.assert_not_called()

    def test_list_visible_reminders_filters_internal_followups(self):
        action_dao = Mock(
            list_visible_actions=Mock(
                return_value=[
                    build_action(_id="visible-1", visibility="visible"),
                    build_action(
                        _id="internal-1",
                        kind="proactive_followup",
                        visibility="internal",
                    ),
                ]
            )
        )
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=Mock(),
        )

        reminders = service.list_visible_reminders("user-1")

        assert [item["_id"] for item in reminders] == ["visible-1"]

    def test_update_visible_reminder_increments_revision_and_reschedules(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        existing = build_action()
        action_dao = Mock(
            get_action=Mock(return_value=existing),
            update_action=Mock(return_value=True),
        )
        scheduler = Mock(reschedule_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        updated = service.update_visible_reminder(
            action_id="action-1",
            user_id="user-1",
            title="运动",
            dtstart=datetime(2026, 4, 21, 10, 0, tzinfo=UTC),
            timezone="UTC",
        )

        action_dao.update_action.assert_called_once()
        assert updated["revision"] == 3
        assert updated["title"] == "运动"
        assert updated["next_run_at"] == datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
        scheduler.reschedule_action.assert_called_once_with(updated)

    def test_delete_and_complete_visible_reminder_unschedule_it(self):
        existing = build_action()
        action_dao = Mock(
            get_action=Mock(return_value=existing),
            update_action=Mock(return_value=True),
        )
        scheduler = Mock(remove_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
        )

        deleted = service.delete_visible_reminder("action-1", "user-1")
        completed = service.complete_visible_reminder("action-1", "user-1")

        assert deleted["lifecycle_state"] == "cancelled"
        assert completed["lifecycle_state"] == "completed"
        assert scheduler.remove_action.call_count == 2

    def test_visible_management_rejects_internal_followups(self):
        internal = build_action(
            kind="proactive_followup",
            visibility="internal",
        )
        action_dao = Mock(get_action=Mock(return_value=internal))
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=Mock(),
        )

        with pytest.raises(ValueError, match="visible user reminders"):
            service.update_visible_reminder(
                action_id="action-1",
                user_id="user-1",
                title="不应该允许",
                dtstart=datetime(2026, 4, 21, 10, 0, tzinfo=UTC),
                timezone="UTC",
            )

    def test_resolve_visible_reminder_by_keyword_prefers_exact_then_contains(self):
        action_dao = Mock(
            list_visible_actions=Mock(
                return_value=[
                    build_action(_id="a1", title="喝水"),
                    build_action(_id="a2", title="下午喝水"),
                ]
            )
        )
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=Mock(),
        )

        exact = service.resolve_visible_reminder_by_keyword("user-1", "喝水")
        fuzzy = service.resolve_visible_reminder_by_keyword("user-1", "下午")

        assert exact["_id"] == "a1"
        assert fuzzy["_id"] == "a2"
