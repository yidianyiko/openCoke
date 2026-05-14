import asyncio
from datetime import UTC, datetime, timedelta
from dataclasses import FrozenInstanceError
from unittest.mock import ANY, AsyncMock, Mock

import pytest

from agent.agno_agent.adapters.deferred_action_result import (
    DeferredActionFireResult,
    map_agent_result_to_deferred_status,
)
from agent.agno_agent.runtime import (
    AgentRunResult,
    OutputDisposition,
    RuntimeErrorDisposition,
)
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


_NOW = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)


def _build_executor_with_failing_occurrence_dao():
    action = build_action(_id="A1", revision=1, next_run_at=_NOW, dtstart=_NOW)
    return executor_module.DeferredActionExecutor(
        action_dao=Mock(
            get_action=Mock(return_value=action),
            claim_action_lease=Mock(return_value=True),
            update_action=Mock(return_value=True),
        ),
        occurrence_dao=Mock(
            claim_or_get_occurrence=Mock(side_effect=RuntimeError("db down")),
            mark_occurrence_failed=Mock(),
        ),
        scheduler=Mock(reschedule_action=Mock(), remove_action=Mock()),
        lock_manager=Mock(
            acquire_lock_async=AsyncMock(return_value="lock-1"),
            release_lock_safe_async=AsyncMock(),
        ),
        conversation_dao=Mock(),
        user_dao=Mock(),
        handle_message_fn=AsyncMock(),
        context_builder=Mock(),
        now_provider=lambda: _NOW,
    )


def test_occurrence_claim_failure_returns_failed_without_nameerror():
    executor = _build_executor_with_failing_occurrence_dao()
    result = asyncio.run(
        executor.execute_due_action(action_id="A1", scheduled_for=_NOW, revision=1)
    )
    assert result == "failed"


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

    async def test_old_proactive_followup_action_is_rejected_before_lock_acquisition(
        self,
    ):
        action = build_action(kind="proactive_followup")
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
            revision=action["revision"],
        )

        assert result == "unsupported_kind"
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
            conversation_dao=Mock(
                get_conversation_by_id=Mock(return_value={"_id": "conv-1"})
            ),
            user_dao=Mock(
                get_user_by_id=Mock(
                    side_effect=lambda user_id: {"_id": user_id, "nickname": user_id}
                )
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

    async def test_first_claim_is_not_treated_as_duplicate_when_mongo_truncates_millis(
        self,
    ):
        now = datetime(2026, 4, 21, 9, 0, 0, 123456, tzinfo=UTC)
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
                    "last_started_at": datetime(
                        2026, 4, 21, 9, 0, 0, 123000, tzinfo=UTC
                    ),
                }
            ),
            mark_occurrence_succeeded=Mock(),
        )
        handle_message = AsyncMock(return_value=([], build_context(), False, False))
        scheduler = Mock(remove_action=Mock())
        executor = executor_module.DeferredActionExecutor(
            action_dao=action_dao,
            occurrence_dao=occurrence_dao,
            scheduler=scheduler,
            lock_manager=Mock(
                acquire_lock_async=AsyncMock(return_value="lock-1"),
                release_lock_safe_async=AsyncMock(),
            ),
            conversation_dao=Mock(
                get_conversation_by_id=Mock(return_value={"_id": "conv-1"})
            ),
            user_dao=Mock(
                get_user_by_id=Mock(
                    side_effect=lambda user_id: {"_id": user_id, "nickname": user_id}
                )
            ),
            handle_message_fn=handle_message,
            context_builder=Mock(return_value=build_context()),
            now_provider=lambda: now,
        )

        result = await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        assert result == "succeeded"
        handle_message.assert_awaited_once()
        occurrence_dao.mark_occurrence_succeeded.assert_called_once()

    async def test_success_path_updates_lifecycle_and_reschedules_recurring_actions(
        self,
    ):
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
            conversation_dao=Mock(
                get_conversation_by_id=Mock(return_value={"_id": "conv-1"})
            ),
            user_dao=Mock(
                get_user_by_id=Mock(
                    side_effect=lambda user_id: {"_id": user_id, "nickname": user_id}
                )
            ),
            handle_message_fn=AsyncMock(
                return_value=([], build_context(), False, False)
            ),
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

    async def test_build_context_recovers_synthetic_business_user_from_conversation_talkers(
        self,
    ):
        action = build_action(
            user_id="ck_synthetic_user",
            character_id="char-1",
            conversation_id="conv-1",
        )
        conversation = {
            "_id": "conv-1",
            "platform": "business",
            "talkers": [
                {"db_user_id": "ck_synthetic_user", "nickname": "Codex Smoke"},
                {"db_user_id": "char-1", "nickname": "qiaoyun"},
            ],
        }
        context_builder = Mock(return_value=build_context())
        executor = executor_module.DeferredActionExecutor(
            action_dao=Mock(),
            occurrence_dao=Mock(),
            scheduler=Mock(),
            lock_manager=Mock(),
            conversation_dao=Mock(
                get_conversation_by_id=Mock(return_value=conversation)
            ),
            user_dao=Mock(
                get_user_by_id=Mock(
                    side_effect=lambda user_id: (
                        None
                        if user_id == "ck_synthetic_user"
                        else {"_id": "char-1", "nickname": "qiaoyun"}
                    )
                )
            ),
            handle_message_fn=AsyncMock(),
            context_builder=context_builder,
        )

        executor._build_context(action)

        context_builder.assert_called_once()
        user_arg, character_arg, conversation_arg = context_builder.call_args.args
        assert user_arg == {
            "id": "ck_synthetic_user",
            "_id": "ck_synthetic_user",
            "nickname": "Codex Smoke",
            "is_coke_account": True,
        }
        assert character_arg == {"_id": "char-1", "nickname": "qiaoyun"}
        assert conversation_arg == conversation

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
            conversation_dao=Mock(
                get_conversation_by_id=Mock(return_value={"_id": "conv-1"})
            ),
            user_dao=Mock(
                get_user_by_id=Mock(
                    side_effect=lambda user_id: {"_id": user_id, "nickname": user_id}
                )
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
            conversation_dao=Mock(
                get_conversation_by_id=Mock(return_value={"_id": "conv-1"})
            ),
            user_dao=Mock(
                get_user_by_id=Mock(
                    side_effect=lambda user_id: {"_id": user_id, "nickname": user_id}
                )
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


@pytest.mark.asyncio
async def test_executor_consumes_deferred_action_fire_result_success():
    from agent.agno_agent.runtime.result import VisibleMessage

    now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    action = build_action(kind="follow_up")
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
    scheduler = Mock(remove_action=Mock(), reschedule_action=Mock())
    lock_manager = Mock(
        acquire_lock_async=AsyncMock(return_value="lock-1"),
        release_lock_safe_async=AsyncMock(),
    )

    async def runtime_fire_handler(**kwargs):
        agent_input = kwargs["agent_input"]
        assert agent_input.input_type == "deferred_action.fire"
        assert agent_input.payload.action_id == str(action["_id"])
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="follow up")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    output_writer = Mock(return_value={"_id": "out-1"})

    executor = executor_module.DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=scheduler,
        lock_manager=lock_manager,
        conversation_dao=Mock(
            get_conversation_by_id=Mock(return_value={"_id": "conv-1"})
        ),
        user_dao=Mock(
            get_user_by_id=Mock(
                side_effect=lambda user_id: {"_id": user_id, "nickname": user_id}
            )
        ),
        context_builder=Mock(return_value=build_context()),
        now_provider=lambda: now,
        runtime_fire_handler=runtime_fire_handler,
        output_writer=output_writer,
    )

    result = await executor.execute_due_action(
        action_id=str(action["_id"]),
        scheduled_for=action["next_run_at"],
        revision=action["revision"],
    )

    assert result == "succeeded"
    output_writer.assert_called_once()
    assert output_writer.call_args.kwargs["message"] == "follow up"
    output_context = output_writer.call_args.args[0]
    assert output_context["message_source"] == "deferred_action"


def build_agent_result(*, output_disposition, error_disposition=None):
    return AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={},
        output_disposition=output_disposition,
        error_disposition=error_disposition,
    )


def test_deferred_action_mapper_maps_success_and_preserves_output_refs():
    result = build_agent_result(
        output_disposition=OutputDisposition(
            status="ok",
            output_references=["message:1", "tool:2"],
        )
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped == DeferredActionFireResult(
        status="succeeded",
        output_references=("message:1", "tool:2"),
        retryable=False,
    )


def test_deferred_action_mapper_maps_empty_output_to_retryable_no_output():
    result = build_agent_result(
        output_disposition=OutputDisposition(status="empty"),
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped.status == "no_output"
    assert mapped.output_references == ()
    assert mapped.retryable is True
    assert mapped.error_code is None
    assert mapped.error_message is None


def test_deferred_action_mapper_maps_rollback_to_retryable_rollback():
    result = build_agent_result(
        output_disposition=OutputDisposition(
            status="rollback",
            output_references=["rollback:1"],
        )
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped.status == "rollback"
    assert mapped.output_references == ("rollback:1",)
    assert mapped.retryable is True


def test_deferred_action_mapper_preserves_runtime_error_details_for_fallback():
    result = build_agent_result(
        output_disposition=OutputDisposition(status="fallback"),
        error_disposition=RuntimeErrorDisposition(
            code="agent_timeout",
            retryable=False,
            user_visible_fallback="I need more time.",
        ),
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped.status == "failed"
    assert mapped.retryable is False
    assert mapped.error_code == "agent_timeout"
    assert mapped.error_message == "I need more time."


def test_deferred_action_mapper_rejects_unknown_output_status():
    result = build_agent_result(
        output_disposition=OutputDisposition(status="future_status"),
    )

    with pytest.raises(
        ValueError,
        match="Unsupported output disposition status: future_status",
    ):
        map_agent_result_to_deferred_status(result)


def test_deferred_action_mapper_freezes_output_references_after_mapping():
    result = build_agent_result(
        output_disposition=OutputDisposition(
            status="ok",
            output_references=["message:1"],
        )
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped.output_references == ("message:1",)
    with pytest.raises(FrozenInstanceError):
        mapped.output_references = ("message:2",)
    with pytest.raises(AttributeError):
        mapped.output_references.append("message:2")


@pytest.mark.asyncio
async def test_executor_consumes_deferred_action_fire_result_success():
    from agent.agno_agent.runtime.result import VisibleMessage

    now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    action = build_action(kind="follow_up", next_run_at=now, dtstart=now)
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
    scheduler = Mock(remove_action=Mock(), reschedule_action=Mock())
    lock_manager = Mock(
        acquire_lock_async=AsyncMock(return_value="lock-1"),
        release_lock_safe_async=AsyncMock(),
    )

    async def runtime_fire_handler(**kwargs):
        agent_input = kwargs["agent_input"]
        assert agent_input.input_type == "deferred_action.fire"
        assert agent_input.payload.action_id == str(action["_id"])
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="follow up")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    output_writer = Mock(return_value={"_id": "out-1"})

    executor = executor_module.DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=scheduler,
        lock_manager=lock_manager,
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value={"_id": "conv-1"})),
        user_dao=Mock(
            get_user_by_id=Mock(side_effect=lambda user_id: {"_id": user_id, "nickname": user_id})
        ),
        context_builder=Mock(return_value=build_context()),
        now_provider=lambda: now,
        runtime_fire_handler=runtime_fire_handler,
        output_writer=output_writer,
    )

    result = await executor.execute_due_action(
        action_id=str(action["_id"]),
        scheduled_for=action["next_run_at"],
        revision=action["revision"],
    )

    assert result == "succeeded"
    output_writer.assert_called_once()
    assert output_writer.call_args.kwargs["message"] == "follow up"
    output_context = output_writer.call_args.args[0]
    assert output_context["message_source"] == "deferred_action"
