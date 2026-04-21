from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, Mock

import pytest

from agent.runner import deferred_action_executor as executor_module


def build_action(**overrides):
    action = {
        "_id": "action-1",
        "conversation_id": "conv-1",
        "user_id": "user-1",
        "character_id": "char-1",
        "kind": "user_reminder",
        "title": "喝水",
        "payload": {"prompt": "提醒用户喝水"},
        "lifecycle_state": "active",
        "revision": 3,
        "next_run_at": datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        "dtstart": datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        "rrule": None,
        "run_count": 0,
        "max_runs": None,
        "expires_at": None,
        "retry_policy": {
            "max_attempts_per_occurrence": 3,
            "base_backoff_seconds": 60,
            "max_backoff_seconds": 900,
        },
    }
    action.update(overrides)
    return action


def build_context():
    return {
        "conversation": {"conversation_info": {"chat_history": []}},
        "relation": {"uid": "user-1", "cid": "char-1"},
    }


@pytest.mark.asyncio
class TestDeferredActionExecutor:
    async def test_stale_job_payload_is_rejected_before_lock_acquisition(self):
        action = build_action(revision=4)
        lock_manager = Mock(acquire_lock_async=AsyncMock())
        executor = executor_module.DeferredActionExecutor(
            action_dao=Mock(get_action=Mock(return_value=action)),
            occurrence_dao=Mock(),
            scheduler=Mock(),
            lock_manager=lock_manager,
            conversation_dao=Mock(),
            user_dao=Mock(),
            handle_message_fn=AsyncMock(),
            context_builder=Mock(),
            now_provider=lambda: datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        )

        result = await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=3,
        )

        assert result == "stale"
        lock_manager.acquire_lock_async.assert_not_called()

    async def test_conversation_lock_is_acquired_before_handle_message(self):
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        action = build_action()
        events = []
        lock_manager = Mock(
            acquire_lock_async=AsyncMock(
                side_effect=lambda *args, **kwargs: events.append("lock") or "lock-1"
            ),
            release_lock_safe_async=AsyncMock(),
        )
        handle_message = AsyncMock(
            side_effect=lambda **kwargs: events.append("handle")
            or ([], build_context(), False, False)
        )
        executor = executor_module.DeferredActionExecutor(
            action_dao=Mock(
                get_action=Mock(return_value=action),
                claim_action_lease=Mock(return_value=True),
                update_action=Mock(return_value=True),
            ),
            occurrence_dao=Mock(
                claim_or_get_occurrence=Mock(
                    return_value={
                        "trigger_key": "action:action-1:2026-04-21T09:00:00+00:00",
                        "status": "claimed",
                        "attempt_count": 1,
                        "last_started_at": now,
                    }
                ),
                mark_occurrence_succeeded=Mock(),
            ),
            scheduler=Mock(remove_action=Mock()),
            lock_manager=lock_manager,
            conversation_dao=Mock(get_conversation_by_id=Mock(return_value={"_id": "conv-1"})),
            user_dao=Mock(
                get_user_by_id=Mock(side_effect=lambda user_id: {"_id": user_id, "nickname": user_id})
            ),
            handle_message_fn=handle_message,
            context_builder=Mock(return_value=build_context()),
            now_provider=lambda: now,
        )

        await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        assert events == ["lock", "handle"]
        handle_message.assert_awaited_once()
        assert handle_message.await_args.kwargs["message_source"] == "deferred_action"

    async def test_duplicate_wakeup_becomes_noop_via_occurrence_claim(self):
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        action = build_action()
        action_dao = Mock(
            get_action=Mock(return_value=action),
            claim_action_lease=Mock(return_value=True),
            release_action_lease=Mock(return_value=True),
        )
        occurrence_dao = Mock(
            claim_or_get_occurrence=Mock(
                return_value={
                    "trigger_key": "action:action-1:2026-04-21T09:00:00+00:00",
                    "status": "claimed",
                    "attempt_count": 1,
                    "last_started_at": now - timedelta(seconds=5),
                }
            )
        )
        handle_message = AsyncMock()
        lock_manager = Mock(
            acquire_lock_async=AsyncMock(return_value="lock-1"),
            release_lock_safe_async=AsyncMock(),
        )
        executor = executor_module.DeferredActionExecutor(
            action_dao=action_dao,
            occurrence_dao=occurrence_dao,
            scheduler=Mock(),
            lock_manager=lock_manager,
            conversation_dao=Mock(),
            user_dao=Mock(),
            handle_message_fn=handle_message,
            context_builder=Mock(),
            now_provider=lambda: now,
        )

        result = await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        assert result == "duplicate"
        handle_message.assert_not_called()
        action_dao.release_action_lease.assert_called_once_with("action-1", ANY)

    async def test_success_path_updates_lifecycle_and_reschedules_recurring_actions(self):
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        action = build_action(rrule="FREQ=DAILY")
        action_dao = Mock(
            get_action=Mock(return_value=action),
            claim_action_lease=Mock(return_value=True),
            update_action=Mock(return_value=True),
        )
        occurrence_dao = Mock(
            claim_or_get_occurrence=Mock(
                return_value={
                    "trigger_key": "action:action-1:2026-04-21T09:00:00+00:00",
                    "status": "claimed",
                    "attempt_count": 1,
                    "last_started_at": now,
                }
            ),
            mark_occurrence_succeeded=Mock(),
        )
        scheduler = Mock(reschedule_action=Mock(), remove_action=Mock())
        executor = executor_module.DeferredActionExecutor(
            action_dao=action_dao,
            occurrence_dao=occurrence_dao,
            scheduler=scheduler,
            lock_manager=Mock(
                acquire_lock_async=AsyncMock(return_value="lock-1"),
                release_lock_safe_async=AsyncMock(),
            ),
            conversation_dao=Mock(get_conversation_by_id=Mock(return_value={"_id": "conv-1"})),
            user_dao=Mock(
                get_user_by_id=Mock(side_effect=lambda user_id: {"_id": user_id, "nickname": user_id})
            ),
            handle_message_fn=AsyncMock(return_value=([], build_context(), False, False)),
            context_builder=Mock(return_value=build_context()),
            now_provider=lambda: now,
        )

        await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        action_dao.update_action.assert_called_once()
        call = action_dao.update_action.call_args
        assert call.kwargs["expected_revision"] == 3
        assert call.kwargs["updates"]["run_count"] == 1
        assert call.kwargs["updates"]["next_run_at"] == datetime(
            2026, 4, 22, 9, 0, tzinfo=UTC
        )
        occurrence_dao.mark_occurrence_succeeded.assert_called_once()
        scheduler.reschedule_action.assert_called_once()
        scheduler.remove_action.assert_not_called()

    async def test_failure_path_retries_one_shot_actions(self):
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        action = build_action()
        action_dao = Mock(
            get_action=Mock(return_value=action),
            claim_action_lease=Mock(return_value=True),
            update_action=Mock(return_value=True),
        )
        occurrence_dao = Mock(
            claim_or_get_occurrence=Mock(
                return_value={
                    "trigger_key": "action:action-1:2026-04-21T09:00:00+00:00",
                    "status": "claimed",
                    "attempt_count": 1,
                    "last_started_at": now,
                }
            ),
            mark_occurrence_failed=Mock(),
        )
        scheduler = Mock(reschedule_action=Mock(), remove_action=Mock())
        executor = executor_module.DeferredActionExecutor(
            action_dao=action_dao,
            occurrence_dao=occurrence_dao,
            scheduler=scheduler,
            lock_manager=Mock(
                acquire_lock_async=AsyncMock(return_value="lock-1"),
                release_lock_safe_async=AsyncMock(),
            ),
            conversation_dao=Mock(get_conversation_by_id=Mock(return_value={"_id": "conv-1"})),
            user_dao=Mock(
                get_user_by_id=Mock(side_effect=lambda user_id: {"_id": user_id, "nickname": user_id})
            ),
            handle_message_fn=AsyncMock(side_effect=RuntimeError("send failed")),
            context_builder=Mock(return_value=build_context()),
            now_provider=lambda: now,
        )

        await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        call = action_dao.update_action.call_args
        assert call.kwargs["updates"]["next_run_at"] == now + timedelta(seconds=60)
        assert call.kwargs["updates"]["last_error"] == "send failed"
        occurrence_dao.mark_occurrence_failed.assert_called_once()
        scheduler.reschedule_action.assert_called_once()
        scheduler.remove_action.assert_not_called()

    async def test_terminal_failure_marks_one_shot_failed(self):
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        action = build_action(
            retry_policy={
                "max_attempts_per_occurrence": 1,
                "base_backoff_seconds": 60,
                "max_backoff_seconds": 900,
            }
        )
        action_dao = Mock(
            get_action=Mock(return_value=action),
            claim_action_lease=Mock(return_value=True),
            update_action=Mock(return_value=True),
        )
        occurrence_dao = Mock(
            claim_or_get_occurrence=Mock(
                return_value={
                    "trigger_key": "action:action-1:2026-04-21T09:00:00+00:00",
                    "status": "claimed",
                    "attempt_count": 1,
                    "last_started_at": now,
                }
            ),
            mark_occurrence_failed=Mock(),
        )
        scheduler = Mock(reschedule_action=Mock(), remove_action=Mock())
        executor = executor_module.DeferredActionExecutor(
            action_dao=action_dao,
            occurrence_dao=occurrence_dao,
            scheduler=scheduler,
            lock_manager=Mock(
                acquire_lock_async=AsyncMock(return_value="lock-1"),
                release_lock_safe_async=AsyncMock(),
            ),
            conversation_dao=Mock(get_conversation_by_id=Mock(return_value={"_id": "conv-1"})),
            user_dao=Mock(
                get_user_by_id=Mock(side_effect=lambda user_id: {"_id": user_id, "nickname": user_id})
            ),
            handle_message_fn=AsyncMock(side_effect=RuntimeError("boom")),
            context_builder=Mock(return_value=build_context()),
            now_provider=lambda: now,
        )

        await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        call = action_dao.update_action.call_args
        assert call.kwargs["updates"]["lifecycle_state"] == "failed"
        assert call.kwargs["updates"]["next_run_at"] is None
        scheduler.remove_action.assert_called_once_with("action-1")
        scheduler.reschedule_action.assert_not_called()
