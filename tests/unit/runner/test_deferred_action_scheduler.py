from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from apscheduler.jobstores.base import JobLookupError

from agent.runner import deferred_action_scheduler as scheduler_module


def build_action(**overrides):
    action = {
        "_id": "action-1",
        "lifecycle_state": "active",
        "next_run_at": datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        "revision": 3,
    }
    action.update(overrides)
    return action


class TestDeferredActionScheduler:
    def test_constructs_single_asyncio_scheduler_when_not_injected(self, monkeypatch):
        scheduler_factory = Mock()
        monkeypatch.setattr(
            scheduler_module,
            "AsyncIOScheduler",
            scheduler_factory,
        )

        scheduler_module.DeferredActionScheduler(
            action_dao=Mock(),
            executor=Mock(),
        )

        scheduler_factory.assert_called_once()

    def test_start_reconciles_leases_before_rebuilding_schedule(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        events = []
        action = build_action()
        action_dao = Mock()
        action_dao.reconcile_expired_leases.side_effect = lambda current_now: events.append(
            ("reconcile", current_now)
        )
        action_dao.list_active_actions.side_effect = lambda: events.append("list") or [action]
        scheduler = scheduler_module.DeferredActionScheduler(
            action_dao=action_dao,
            executor=Mock(),
            scheduler=Mock(),
            now_provider=lambda: now,
        )
        scheduler.register_action = Mock(side_effect=lambda value, now=None: events.append(("register", value["_id"], now)))

        scheduler.start()

        assert events == [
            ("reconcile", now),
            "list",
            ("register", "action-1", now),
        ]

    def test_register_action_passes_action_id_scheduled_for_and_revision(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        mock_scheduler = Mock()
        scheduler = scheduler_module.DeferredActionScheduler(
            action_dao=Mock(),
            executor=Mock(),
            scheduler=mock_scheduler,
            now_provider=lambda: now,
        )
        action = build_action()

        scheduler.register_action(action)

        mock_scheduler.add_job.assert_called_once()
        _, kwargs = mock_scheduler.add_job.call_args
        assert kwargs["id"] == "deferred-action:action-1"
        assert kwargs["replace_existing"] is True
        assert kwargs["run_date"] == action["next_run_at"]
        assert kwargs["kwargs"] == {
            "action_id": "action-1",
            "scheduled_for": action["next_run_at"],
            "revision": 3,
        }

    def test_reschedule_action_replaces_existing_job_and_remove_ignores_missing_job(self):
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
        mock_scheduler = Mock()
        mock_scheduler.remove_job.side_effect = JobLookupError("missing")
        scheduler = scheduler_module.DeferredActionScheduler(
            action_dao=Mock(),
            executor=Mock(),
            scheduler=mock_scheduler,
            now_provider=lambda: now,
        )
        action = build_action(revision=4, next_run_at=now + timedelta(hours=2))

        scheduler.reschedule_action(action)
        scheduler.remove_action("missing-action")

        assert mock_scheduler.add_job.call_count == 1
        mock_scheduler.remove_job.assert_called_once_with("deferred-action:missing-action")

    def test_load_from_storage_registers_overdue_actions_for_immediate_execution(self):
        now = datetime(2026, 4, 21, 11, 30, tzinfo=UTC)
        overdue_action = build_action(next_run_at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC))
        mock_scheduler = Mock()
        scheduler = scheduler_module.DeferredActionScheduler(
            action_dao=Mock(
                reconcile_expired_leases=Mock(),
                list_active_actions=Mock(return_value=[overdue_action]),
            ),
            executor=Mock(),
            scheduler=mock_scheduler,
            now_provider=lambda: now,
        )

        scheduler.load_from_storage()

        _, kwargs = mock_scheduler.add_job.call_args
        assert kwargs["run_date"] == now
