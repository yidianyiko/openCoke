from __future__ import annotations

import copy
from datetime import UTC, date, datetime, time
from unittest.mock import Mock

import pytest
from apscheduler.jobstores.base import JobLookupError

from agent.reminder.models import (
    AgentOutputTarget,
    ReminderCreateCommand,
    ReminderSchedule,
)
from agent.reminder.service import ReminderService
from agent.agno_agent.tools.reminder_protocol import set_reminder_session_state
from agent.runner.reminder_event_handler import ReminderFireEventHandler
from agent.runner.reminder_scheduler import ReminderScheduler


class InMemoryReminderDAO:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.next_id = 1

    def insert_reminder(self, document: dict) -> str:
        reminder_id = f"rem-{self.next_id}"
        self.next_id += 1
        stored = copy.deepcopy(document)
        stored["_id"] = reminder_id
        self.documents[reminder_id] = stored
        return reminder_id

    def get_reminder(self, reminder_id: str) -> dict | None:
        document = self.documents.get(reminder_id)
        return copy.deepcopy(document) if document else None

    def get_reminder_for_owner(
        self, reminder_id: str, owner_user_id: str
    ) -> dict | None:
        document = self.documents.get(reminder_id)
        if document is None or document["owner_user_id"] != owner_user_id:
            return None
        return copy.deepcopy(document)

    def list_for_owner(
        self, owner_user_id: str, lifecycle_states: list[str] | None = None
    ) -> list[dict]:
        documents = [
            copy.deepcopy(document)
            for document in self.documents.values()
            if document["owner_user_id"] == owner_user_id
        ]
        if lifecycle_states is not None:
            documents = [
                document
                for document in documents
                if document["lifecycle_state"] in lifecycle_states
            ]
        return sorted(documents, key=lambda document: document["_id"])

    def list_due_active(self) -> list[dict]:
        return [
            copy.deepcopy(document)
            for document in sorted(
                self.documents.values(),
                key=lambda document: document["next_fire_at"]
                or datetime.max.replace(tzinfo=UTC),
            )
            if document["lifecycle_state"] == "active"
            and document.get("next_fire_at") is not None
        ]

    def replace_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        updates: dict,
        lifecycle_state: str | None = None,
    ) -> bool:
        document = self.documents.get(reminder_id)
        if document is None or document["owner_user_id"] != owner_user_id:
            return False
        if (
            lifecycle_state is not None
            and document["lifecycle_state"] != lifecycle_state
        ):
            return False
        document.update(copy.deepcopy(updates))
        return True

    def atomic_apply_fire_success(
        self,
        reminder_id: str,
        expected_next_fire_at: datetime,
        updates: dict,
    ) -> bool:
        return self._atomic_apply_fire(
            reminder_id,
            expected_next_fire_at,
            updates,
        )

    def atomic_apply_fire_failure(
        self,
        reminder_id: str,
        expected_next_fire_at: datetime,
        updates: dict,
    ) -> bool:
        return self._atomic_apply_fire(
            reminder_id,
            expected_next_fire_at,
            updates,
        )

    def _atomic_apply_fire(
        self,
        reminder_id: str,
        expected_next_fire_at: datetime,
        updates: dict,
    ) -> bool:
        document = self.documents.get(reminder_id)
        if (
            document is None
            or document["lifecycle_state"] != "active"
            or document["next_fire_at"] != expected_next_fire_at
        ):
            return False
        document.update(copy.deepcopy(updates))
        return True


class FailFastDeferredActionService:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError(
            "visible reminder protocol must not touch deferred_actions"
        )


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
            "replace_existing": replace_existing,
            "run_date": run_date,
            "kwargs": kwargs,
            "misfire_grace_time": misfire_grace_time,
        }

    def remove_job(self, job_id: str) -> None:
        if job_id not in self.jobs:
            raise JobLookupError(job_id)
        del self.jobs[job_id]


class FakeLockManager:
    def __init__(self) -> None:
        self.acquired: list[tuple] = []
        self.released: list[tuple] = []

    async def acquire_lock_async(
        self, resource_type, resource_id, timeout=120, max_wait=1
    ):
        self.acquired.append((resource_type, resource_id, timeout, max_wait))
        return "lock-1"

    async def release_lock_safe_async(self, resource_type, resource_id, lock_id):
        self.released.append((resource_type, resource_id, lock_id))
        return True, "released"


def _schedule(
    anchor_at: datetime,
    *,
    rrule: str | None = None,
) -> ReminderSchedule:
    return ReminderSchedule(
        anchor_at=anchor_at,
        local_date=date(anchor_at.year, anchor_at.month, anchor_at.day),
        local_time=time(anchor_at.hour, anchor_at.minute),
        timezone="UTC",
        rrule=rrule,
    )


def _create_command(
    *,
    title: str = "drink water",
    anchor_at: datetime,
    rrule: str | None = None,
) -> ReminderCreateCommand:
    return ReminderCreateCommand(
        title=title,
        schedule=_schedule(anchor_at, rrule=rrule),
        agent_output_target=AgentOutputTarget(
            conversation_id="conv-1",
            character_id="char-1",
            route_key="wechat_personal:primary",
        ),
        created_by_system="agent",
    )


def _reminder_service(
    *,
    reminder_dao: InMemoryReminderDAO,
    scheduler: ReminderScheduler | None = None,
    now: datetime,
) -> ReminderService:
    return ReminderService(
        reminder_dao=reminder_dao,
        scheduler=scheduler,
        now_provider=lambda: now,
    )


def _event_handler(output_writer: Mock) -> ReminderFireEventHandler:
    conversation = {
        "_id": "conv-1",
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    return ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[owner, character])),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(return_value={"conversation": conversation}),
    )


@pytest.mark.e2e
def test_agent_visible_reminder_tool_create_writes_reminders_not_deferred_actions(
    monkeypatch,
):
    now = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    reminder_dao = InMemoryReminderDAO()
    scheduler_backend = RecordingSchedulerBackend()
    scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=Mock(),
        scheduler=scheduler_backend,
        now_provider=lambda: now,
    )
    service = _reminder_service(
        reminder_dao=reminder_dao,
        scheduler=scheduler,
        now=now,
    )

    import agent.agno_agent.tools.deferred_action.service as legacy_service_module
    import agent.agno_agent.tools.deferred_action.tool as legacy_tool_module
    import agent.agno_agent.tools.reminder_protocol.tool as reminder_tool_module
    from agent.agno_agent.agents import reminder_detect_agent

    monkeypatch.setattr(reminder_tool_module, "ReminderService", lambda: service)
    monkeypatch.setattr(
        legacy_service_module,
        "DeferredActionService",
        FailFastDeferredActionService,
    )
    monkeypatch.setattr(
        legacy_tool_module,
        "DeferredActionService",
        FailFastDeferredActionService,
    )
    set_reminder_session_state(
        {
            "user": {"id": "user-1", "effective_timezone": "UTC"},
            "character": {"id": "char-1"},
            "conversation": {"id": "conv-1"},
            "delivery_route_key": "wechat_personal:primary",
        }
    )
    [configured_tool] = reminder_detect_agent.tools
    entrypoint = getattr(configured_tool, "entrypoint", configured_tool)
    entrypoint = getattr(entrypoint, "raw_function", entrypoint)
    assert entrypoint.__module__ == "agent.agno_agent.tools.reminder_protocol.tool"

    result = entrypoint(
        action="create",
        title="drink water",
        trigger_at=scheduled_for.isoformat(),
    )

    assert result == "已创建提醒：drink water"
    [reminder_id] = reminder_dao.documents
    reminder = reminder_dao.documents[reminder_id]
    assert list(reminder_dao.documents) == [reminder_id]
    assert reminder["owner_user_id"] == "user-1"
    assert reminder["agent_output_target"] == {
        "conversation_id": "conv-1",
        "character_id": "char-1",
        "route_key": "wechat_personal:primary",
    }
    assert reminder["next_fire_at"] == scheduled_for
    assert reminder["lifecycle_state"] == "active"
    assert (
        scheduler_backend.jobs[f"reminder:{reminder_id}"]["run_date"] == scheduled_for
    )


@pytest.mark.e2e
def test_scheduler_restart_reconstructs_jobs_from_reminders_next_fire_at():
    now = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    reminder_dao = InMemoryReminderDAO()
    first_scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=Mock(),
        scheduler=RecordingSchedulerBackend(),
        now_provider=lambda: now,
    )
    service = _reminder_service(
        reminder_dao=reminder_dao,
        scheduler=first_scheduler,
        now=now,
    )
    reminder = service.create(
        owner_user_id="user-1",
        command=_create_command(anchor_at=scheduled_for),
    )

    restarted_backend = RecordingSchedulerBackend()
    restarted_scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=Mock(),
        scheduler=restarted_backend,
        now_provider=lambda: now,
    )
    restarted_scheduler.start()

    assert restarted_backend.started is True
    assert (
        restarted_backend.jobs[f"reminder:{reminder.id}"]["run_date"] == scheduled_for
    )
    assert restarted_backend.jobs[f"reminder:{reminder.id}"]["kwargs"] == {
        "reminder_id": reminder.id,
        "next_fire_at": scheduled_for,
    }


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_one_shot_fired_event_enters_agent_handler_and_completes_reminder():
    now = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    fired_at = datetime(2026, 4, 29, 1, 0, 2, tzinfo=UTC)
    reminder_dao = InMemoryReminderDAO()
    output_writer = Mock(return_value={"_id": "out-1"})
    scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=_event_handler(output_writer),
        scheduler=RecordingSchedulerBackend(),
        now_provider=lambda: fired_at,
    )
    service = _reminder_service(
        reminder_dao=reminder_dao,
        scheduler=scheduler,
        now=now,
    )
    reminder = service.create(
        owner_user_id="user-1",
        command=_create_command(anchor_at=scheduled_for, title="stand up"),
    )

    await scheduler._execute_job(reminder.id, scheduled_for)

    stored = reminder_dao.documents[reminder.id]
    assert stored["lifecycle_state"] == "completed"
    assert stored["next_fire_at"] is None
    assert stored["last_fired_at"] == scheduled_for
    assert stored["last_event_ack_at"] == fired_at
    output_writer.assert_called_once()
    assert output_writer.call_args.args[1] == "提醒：stand up"
    assert output_writer.call_args.kwargs["metadata"]["reminder_id"] == reminder.id


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_recurring_reminder_advances_next_fire_at_after_success():
    now = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    fired_at = datetime(2026, 4, 29, 1, 0, 2, tzinfo=UTC)
    reminder_dao = InMemoryReminderDAO()
    scheduler_backend = RecordingSchedulerBackend()
    scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=_event_handler(Mock(return_value={"_id": "out-1"})),
        scheduler=scheduler_backend,
        now_provider=lambda: fired_at,
    )
    service = _reminder_service(
        reminder_dao=reminder_dao,
        scheduler=scheduler,
        now=now,
    )
    reminder = service.create(
        owner_user_id="user-1",
        command=_create_command(anchor_at=scheduled_for, rrule="FREQ=DAILY;COUNT=2"),
    )

    await scheduler._execute_job(reminder.id, scheduled_for)

    next_fire_at = datetime(2026, 4, 30, 1, 0, tzinfo=UTC)
    stored = reminder_dao.documents[reminder.id]
    assert stored["lifecycle_state"] == "active"
    assert stored["next_fire_at"] == next_fire_at
    assert stored["last_fired_at"] == scheduled_for
    assert scheduler_backend.jobs[f"reminder:{reminder.id}"]["run_date"] == next_fire_at


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_failed_event_handling_marks_reminder_failed():
    now = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    fired_at = datetime(2026, 4, 29, 1, 0, 2, tzinfo=UTC)
    reminder_dao = InMemoryReminderDAO()
    scheduler_backend = RecordingSchedulerBackend()
    scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_event_handler=_event_handler(
            Mock(
                return_value={
                    "_id": "out-1",
                    "status": "failed",
                    "last_error": "no route",
                }
            )
        ),
        scheduler=scheduler_backend,
        now_provider=lambda: fired_at,
    )
    service = _reminder_service(
        reminder_dao=reminder_dao,
        scheduler=scheduler,
        now=now,
    )
    reminder = service.create(
        owner_user_id="user-1",
        command=_create_command(anchor_at=scheduled_for),
    )

    await scheduler._execute_job(reminder.id, scheduled_for)

    stored = reminder_dao.documents[reminder.id]
    assert stored["lifecycle_state"] == "failed"
    assert stored["next_fire_at"] is None
    assert stored["last_fired_at"] == scheduled_for
    assert stored["last_error"] == "no route"
    assert stored["failed_at"] == fired_at
    assert f"reminder:{reminder.id}" not in scheduler_backend.jobs
