import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _load_service_module():
    module_name = "agent.agno_agent.tools.deferred_action.service"
    if module_name in sys.modules:
        return sys.modules[module_name]

    for pkg, path in (
        ("agent.agno_agent", _PROJECT_ROOT / "agent" / "agno_agent"),
        ("agent.agno_agent.tools", _PROJECT_ROOT / "agent" / "agno_agent" / "tools"),
        (
            "agent.agno_agent.tools.deferred_action",
            _PROJECT_ROOT / "agent" / "agno_agent" / "tools" / "deferred_action",
        ),
    ):
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = [str(path)]
            mod.__package__ = pkg
            mod.__spec__ = None
            sys.modules[pkg] = mod

    scheduler_module_name = "agent.runner.deferred_action_scheduler"
    if scheduler_module_name not in sys.modules:
        scheduler_module = types.ModuleType(scheduler_module_name)

        def _get_deferred_action_scheduler_instance():
            return None

        scheduler_module.get_deferred_action_scheduler_instance = (
            _get_deferred_action_scheduler_instance
        )
        sys.modules[scheduler_module_name] = scheduler_module

    spec = importlib.util.spec_from_file_location(
        module_name,
        _PROJECT_ROOT / "agent" / "agno_agent" / "tools" / "deferred_action" / "service.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


service_module = _load_service_module()


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
        assert action["schedule_kind"] == "floating_local"
        assert action["fixed_timezone"] is False
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
        existing = build_action(schedule_kind="absolute_delay", fixed_timezone=False)
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
            schedule_kind="floating_local",
        )

        action_dao.update_action.assert_called_once()
        assert updated["revision"] == 3
        assert updated["title"] == "运动"
        assert updated["schedule_kind"] == "floating_local"
        assert updated["fixed_timezone"] is False
        assert updated["next_run_at"] == datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
        scheduler.reschedule_action.assert_called_once_with(updated)

    def test_update_visible_reminder_preserves_schedule_metadata_when_not_overridden(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        existing = build_action(schedule_kind="absolute_delay", fixed_timezone=False)
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
            title="继续喝水",
        )

        assert updated["schedule_kind"] == "absolute_delay"
        assert updated["fixed_timezone"] is False

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

    def test_realign_visible_reminders_updates_floating_local_active_reminder(self):
        now = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)
        existing = build_action(
            schedule_kind="floating_local",
            fixed_timezone=False,
            timezone="UTC",
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            next_run_at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        )
        action_dao = Mock(
            list_visible_actions=Mock(return_value=[existing]),
            update_action=Mock(return_value=True),
        )
        scheduler = Mock(reschedule_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        updated = service.realign_visible_reminders_for_timezone_change(
            user_id="user-1",
            timezone="Asia/Tokyo",
        )

        assert len(updated) == 1
        realigned = updated[0]
        assert realigned["timezone"] == "Asia/Tokyo"
        assert realigned["dtstart"] == datetime(
            2026, 4, 21, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")
        )
        assert realigned["next_run_at"] == datetime(
            2026, 4, 21, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")
        )
        action_dao.update_action.assert_called_once()
        scheduler.reschedule_action.assert_called_once_with(realigned)

    def test_realign_visible_reminders_skips_absolute_delay_fixed_timezone_and_inactive(
        self,
    ):
        active_absolute_delay = build_action(
            _id="absolute-delay",
            schedule_kind="absolute_delay",
            fixed_timezone=False,
        )
        active_fixed_timezone = build_action(
            _id="fixed-timezone",
            schedule_kind="floating_local",
            fixed_timezone=True,
        )
        inactive_floating = build_action(
            _id="inactive-floating",
            schedule_kind="floating_local",
            fixed_timezone=False,
            lifecycle_state="cancelled",
        )
        action_dao = Mock(
            list_visible_actions=Mock(
                return_value=[
                    active_absolute_delay,
                    active_fixed_timezone,
                    inactive_floating,
                ]
            ),
            update_action=Mock(return_value=True),
        )
        scheduler = Mock(reschedule_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: datetime(2026, 4, 21, 0, 0, tzinfo=UTC),
        )

        updated = service.realign_visible_reminders_for_timezone_change(
            user_id="user-1",
            timezone="Asia/Tokyo",
        )

        assert updated == []
        action_dao.update_action.assert_not_called()
        scheduler.reschedule_action.assert_not_called()

    def test_realign_visible_reminders_recomputes_next_run_for_recurring_floating_local(
        self,
    ):
        now = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)
        existing = build_action(
            schedule_kind="floating_local",
            fixed_timezone=False,
            timezone="UTC",
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            rrule="FREQ=DAILY",
            next_run_at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        )
        action_dao = Mock(
            list_visible_actions=Mock(return_value=[existing]),
            update_action=Mock(return_value=True),
        )
        scheduler = Mock(reschedule_action=Mock())
        service = service_module.DeferredActionService(
            action_dao=action_dao,
            scheduler=scheduler,
            now_provider=lambda: now,
        )

        updated = service.realign_visible_reminders_for_timezone_change(
            user_id="user-1",
            timezone="America/New_York",
        )

        assert len(updated) == 1
        realigned = updated[0]
        assert realigned["dtstart"] == datetime(
            2026, 4, 21, 9, 0, tzinfo=ZoneInfo("America/New_York")
        )
        assert realigned["next_run_at"] == datetime(
            2026, 4, 21, 9, 0, tzinfo=ZoneInfo("America/New_York")
        )
        assert realigned["next_run_at"] == (
            service_module.policy.compute_initial_next_run_at(realigned, now)
        )
        scheduler.reschedule_action.assert_called_once_with(realigned)
