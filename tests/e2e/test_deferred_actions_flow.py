from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from apscheduler.jobstores.base import JobLookupError

from agent.agno_agent.tools.deferred_action.service import DeferredActionService
from agent.runner.deferred_action_executor import DeferredActionExecutor
from agent.runner.deferred_action_scheduler import DeferredActionScheduler


def _set_nested(doc: dict, dotted_key: str, value) -> None:
    cursor = doc
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _build_context() -> dict:
    return {
        "conversation": {"conversation_info": {"chat_history": []}},
        "relation": {"uid": "user-1", "cid": "char-1"},
    }


class InMemoryActionDAO:
    def __init__(self) -> None:
        self._actions: dict[str, dict] = {}
        self._counter = 0

    def create_action(self, action: dict) -> str:
        self._counter += 1
        action_id = f"action-{self._counter}"
        stored = copy.deepcopy(action)
        stored["_id"] = action_id
        self._actions[action_id] = stored
        return action_id

    def get_action(self, action_id: str) -> dict | None:
        action = self._actions.get(str(action_id))
        return copy.deepcopy(action) if action else None

    def update_action(
        self,
        action_id: str,
        *,
        updates: dict,
        expected_revision: int,
        now: datetime,
    ) -> bool:
        stored = self._actions[str(action_id)]
        if stored["revision"] != expected_revision:
            return False
        for key, value in updates.items():
            _set_nested(stored, key, value)
        stored["revision"] = expected_revision + 1
        stored["updated_at"] = now
        return True

    def claim_action_lease(
        self,
        *,
        action_id: str,
        revision: int,
        scheduled_for: datetime,
        token: str,
        leased_at: datetime,
        lease_until: datetime,
    ) -> bool:
        stored = self._actions[str(action_id)]
        if stored.get("lifecycle_state") != "active":
            return False
        if stored.get("revision") != revision:
            return False
        if stored.get("next_run_at") != scheduled_for:
            return False
        stored.setdefault("lease", {})
        stored["lease"]["token"] = token
        stored["lease"]["leased_at"] = leased_at
        stored["lease"]["lease_expires_at"] = lease_until
        return True

    def release_action_lease(self, action_id: str, token: str) -> bool:
        stored = self._actions[str(action_id)]
        stored.setdefault("lease", {})
        if stored["lease"].get("token") not in {None, token}:
            return False
        stored["lease"]["token"] = None
        stored["lease"]["leased_at"] = None
        stored["lease"]["lease_expires_at"] = None
        return True

    def list_active_actions(self) -> list[dict]:
        return [
            copy.deepcopy(action)
            for action in sorted(
                self._actions.values(),
                key=lambda item: item.get("next_run_at")
                or datetime.max.replace(tzinfo=UTC),
            )
            if action.get("lifecycle_state") == "active"
            and action.get("next_run_at") is not None
        ]

    def reconcile_expired_leases(self, now: datetime) -> None:
        for action in self._actions.values():
            lease = action.get("lease") or {}
            expires_at = lease.get("lease_expires_at")
            if expires_at is not None and expires_at <= now:
                lease["token"] = None
                lease["leased_at"] = None
                lease["lease_expires_at"] = None

    def list_visible_actions(self, user_id: str) -> list[dict]:
        return [
            copy.deepcopy(action)
            for action in sorted(
                self._actions.values(),
                key=lambda item: item.get("next_run_at")
                or datetime.max.replace(tzinfo=UTC),
            )
            if action.get("user_id") == user_id
            and action.get("visibility") == "visible"
        ]

    def find_active_internal_followup(self, conversation_id: str) -> dict | None:
        for action in self._actions.values():
            if (
                action.get("conversation_id") == conversation_id
                and action.get("kind") == "proactive_followup"
                and action.get("lifecycle_state") == "active"
            ):
                return copy.deepcopy(action)
        return None


class InMemoryOccurrenceDAO:
    def __init__(self) -> None:
        self._occurrences: dict[str, dict] = {}

    def claim_or_get_occurrence(
        self,
        *,
        action_id: str,
        trigger_key: str,
        scheduled_for: datetime,
        started_at: datetime,
    ) -> dict:
        if trigger_key not in self._occurrences:
            self._occurrences[trigger_key] = {
                "action_id": action_id,
                "trigger_key": trigger_key,
                "scheduled_for": scheduled_for,
                "status": "claimed",
                "attempt_count": 1,
                "last_started_at": started_at,
                "last_finished_at": None,
                "last_error": None,
            }
        return copy.deepcopy(self._occurrences[trigger_key])

    def increment_attempt_count(self, trigger_key: str, started_at: datetime) -> None:
        occurrence = self._occurrences[trigger_key]
        occurrence["attempt_count"] += 1
        occurrence["last_started_at"] = started_at
        occurrence["status"] = "claimed"

    def mark_occurrence_succeeded(
        self, trigger_key: str, finished_at: datetime
    ) -> None:
        occurrence = self._occurrences[trigger_key]
        occurrence["status"] = "succeeded"
        occurrence["last_finished_at"] = finished_at
        occurrence["last_error"] = None

    def mark_occurrence_failed(
        self,
        trigger_key: str,
        error: str,
        finished_at: datetime,
    ) -> None:
        occurrence = self._occurrences[trigger_key]
        occurrence["status"] = "failed"
        occurrence["last_finished_at"] = finished_at
        occurrence["last_error"] = error

    def put(self, trigger_key: str, occurrence: dict) -> None:
        self._occurrences[trigger_key] = copy.deepcopy(occurrence)


class RecordingSchedulerBackend:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.stopped = True

    def add_job(
        self,
        func,
        *,
        trigger,
        id,
        replace_existing,
        run_date,
        kwargs,
        misfire_grace_time,
    ):
        self.jobs[id] = {
            "func": func,
            "trigger": trigger,
            "run_date": run_date,
            "kwargs": kwargs,
            "replace_existing": replace_existing,
            "misfire_grace_time": misfire_grace_time,
        }

    def remove_job(self, job_id: str) -> None:
        if job_id not in self.jobs:
            raise JobLookupError(job_id)
        del self.jobs[job_id]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_recurring_visible_reminder_survives_restart_and_reschedules():
    created_at = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
    scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    action_dao = InMemoryActionDAO()
    occurrence_dao = InMemoryOccurrenceDAO()

    first_backend = RecordingSchedulerBackend()
    scheduler_before_restart = DeferredActionScheduler(
        action_dao=action_dao,
        executor=Mock(),
        scheduler=first_backend,
        now_provider=lambda: created_at,
    )
    service_before_restart = DeferredActionService(
        action_dao=action_dao,
        scheduler=scheduler_before_restart,
        now_provider=lambda: created_at,
    )

    reminder = service_before_restart.create_visible_reminder(
        user_id="user-1",
        character_id="char-1",
        conversation_id="conv-1",
        title="晨间喝水",
        dtstart=scheduled_for,
        timezone="UTC",
        rrule="FREQ=DAILY",
    )

    assert first_backend.jobs["deferred-action:action-1"]["run_date"] == scheduled_for

    current_time = {"value": datetime(2026, 4, 21, 8, 30, tzinfo=UTC)}
    second_backend = RecordingSchedulerBackend()
    handle_message = AsyncMock(return_value=([], _build_context(), False, False))
    executor = DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=None,
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
        context_builder=Mock(return_value=_build_context()),
        now_provider=lambda: current_time["value"],
    )
    scheduler_after_restart = DeferredActionScheduler(
        action_dao=action_dao,
        executor=executor.execute_due_action,
        scheduler=second_backend,
        now_provider=lambda: current_time["value"],
    )
    executor.scheduler = scheduler_after_restart
    scheduler_after_restart.start()

    job_id = "deferred-action:action-1"
    assert second_backend.jobs[job_id]["run_date"] == scheduled_for
    assert second_backend.jobs[job_id]["kwargs"] == {
        "action_id": reminder["_id"],
        "scheduled_for": scheduled_for,
        "revision": 0,
    }

    current_time["value"] = scheduled_for
    result = await executor.execute_due_action(
        action_id=reminder["_id"],
        scheduled_for=scheduled_for,
        revision=0,
    )

    assert result == "succeeded"
    stored = action_dao.get_action(reminder["_id"])
    assert stored["next_run_at"] == datetime(2026, 4, 22, 9, 0, tzinfo=UTC)
    assert second_backend.jobs[job_id]["kwargs"]["revision"] == 1
    assert second_backend.jobs[job_id]["run_date"] == datetime(
        2026, 4, 22, 9, 0, tzinfo=UTC
    )

    service_after_restart = DeferredActionService(
        action_dao=action_dao,
        scheduler=scheduler_after_restart,
        now_provider=lambda: current_time["value"],
    )
    internal = service_after_restart.create_or_replace_internal_followup(
        conversation_id="conv-1",
        user_id="user-1",
        character_id="char-1",
        title="跟进喝水情况",
        prompt="问问用户今天有没有按时喝水",
        dtstart=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
        timezone="UTC",
    )

    # Internal proactive follow-up remains on the legacy deferred_actions
    # boundary until that subsystem is redesigned.
    assert action_dao.get_action(internal["_id"])["kind"] == "proactive_followup"
    visible = service_after_restart.list_visible_reminders("user-1")
    assert [item["_id"] for item in visible] == ["action-1"]
    with pytest.raises(ValueError, match="visible user reminders only"):
        service_after_restart.delete_visible_reminder(str(internal["_id"]), "user-1")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_startup_recovery_reconciles_expired_leases_and_duplicate_fire_is_noop():
    scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    now = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
    action_dao = InMemoryActionDAO()
    occurrence_dao = InMemoryOccurrenceDAO()

    action_id = action_dao.create_action(
        {
            "conversation_id": "conv-1",
            "user_id": "user-1",
            "character_id": "char-1",
            "kind": "user_reminder",
            "source": "user_explicit",
            "visibility": "visible",
            "lifecycle_state": "active",
            "revision": 4,
            "title": "补水",
            "payload": {"prompt": "提醒用户补水", "metadata": {}},
            "timezone": "UTC",
            "dtstart": scheduled_for,
            "rrule": None,
            "next_run_at": scheduled_for,
            "last_run_at": None,
            "run_count": 0,
            "max_runs": None,
            "expires_at": None,
            "retry_policy": {
                "max_attempts_per_occurrence": 3,
                "base_backoff_seconds": 60,
                "max_backoff_seconds": 900,
            },
            "lease": {
                "token": "stale-token",
                "leased_at": scheduled_for - timedelta(minutes=1),
                "lease_expires_at": scheduled_for + timedelta(minutes=1),
            },
            "last_error": None,
            "created_at": scheduled_for - timedelta(hours=1),
            "updated_at": scheduled_for - timedelta(hours=1),
        }
    )

    trigger_key = f"action:{action_id}:{scheduled_for.isoformat()}"
    occurrence_dao.put(
        trigger_key,
        {
            "action_id": action_id,
            "trigger_key": trigger_key,
            "scheduled_for": scheduled_for,
            "status": "claimed",
            "attempt_count": 1,
            "last_started_at": now - timedelta(seconds=10),
            "last_finished_at": None,
            "last_error": None,
        },
    )

    current_time = {"value": now}
    backend = RecordingSchedulerBackend()
    handle_message = AsyncMock()
    executor = DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=None,
        lock_manager=Mock(
            acquire_lock_async=AsyncMock(return_value="lock-1"),
            release_lock_safe_async=AsyncMock(),
        ),
        conversation_dao=Mock(),
        user_dao=Mock(),
        handle_message_fn=handle_message,
        context_builder=Mock(return_value=_build_context()),
        now_provider=lambda: current_time["value"],
    )
    scheduler = DeferredActionScheduler(
        action_dao=action_dao,
        executor=executor.execute_due_action,
        scheduler=backend,
        now_provider=lambda: current_time["value"],
    )
    executor.scheduler = scheduler
    scheduler.start()

    recovered = action_dao.get_action(action_id)
    assert recovered["lease"]["token"] is None
    assert backend.jobs[f"deferred-action:{action_id}"]["run_date"] == now

    result = await executor.execute_due_action(
        action_id=action_id,
        scheduled_for=scheduled_for,
        revision=4,
    )

    assert result == "duplicate"
    handle_message.assert_not_called()
