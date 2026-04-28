import importlib
import sys
import types
from unittest.mock import AsyncMock, Mock, call

import pytest


def import_agent_runner_with_stubs(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.agent_background_handler",
        types.SimpleNamespace(background_handler=AsyncMock()),
    )
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.agent_handler",
        types.SimpleNamespace(
            create_handler=lambda *args, **kwargs: AsyncMock(),
            handle_message=AsyncMock(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            consume_stream_batch=lambda *args, **kwargs: None,
            get_queue_mode=lambda: "poll",
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.mongo",
        types.SimpleNamespace(MongoDBBase=lambda *args, **kwargs: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "util.redis_client",
        types.SimpleNamespace(
            RedisClient=types.SimpleNamespace(from_config=lambda: None)
        ),
    )

    sys.modules.pop("agent.runner.agent_runner", None)
    return importlib.import_module("agent.runner.agent_runner")


def test_bootstrap_deferred_action_runtime_starts_single_scheduler(monkeypatch):
    agent_runner = import_agent_runner_with_stubs(monkeypatch)

    action_dao = Mock()
    occurrence_dao = Mock()
    scheduler = Mock(start=Mock(), shutdown=Mock())
    set_instance = Mock()
    get_instance = Mock(return_value=None)
    created = {}

    class FakeExecutor:
        def __init__(self, **kwargs):
            created["executor_kwargs"] = kwargs
            self.scheduler = kwargs["scheduler"]

        async def execute_due_action(self, **kwargs):
            return None

    monkeypatch.setattr(agent_runner, "DeferredActionDAO", lambda: action_dao)
    monkeypatch.setattr(
        agent_runner,
        "DeferredActionOccurrenceDAO",
        lambda: occurrence_dao,
    )
    monkeypatch.setattr(agent_runner, "DeferredActionExecutor", FakeExecutor)
    monkeypatch.setattr(
        agent_runner,
        "DeferredActionScheduler",
        lambda **kwargs: scheduler,
    )
    monkeypatch.setattr(
        agent_runner,
        "set_deferred_action_scheduler_instance",
        set_instance,
    )
    monkeypatch.setattr(
        agent_runner,
        "get_deferred_action_scheduler_instance",
        get_instance,
    )

    runtime = agent_runner.bootstrap_deferred_action_runtime()

    assert runtime is scheduler
    scheduler.start.assert_called_once()
    set_instance.assert_called_once_with(scheduler)
    assert created["executor_kwargs"]["action_dao"] is action_dao
    assert created["executor_kwargs"]["occurrence_dao"] is occurrence_dao
    assert created["executor_kwargs"]["scheduler"] is None


def test_bootstrap_deferred_action_runtime_cleans_up_when_start_raises(monkeypatch):
    agent_runner = import_agent_runner_with_stubs(monkeypatch)

    scheduler = Mock(
        start=Mock(side_effect=RuntimeError("deferred start failed")),
        shutdown=Mock(),
    )
    set_instance = Mock()

    class FakeExecutor:
        def __init__(self, **kwargs):
            self.scheduler = kwargs["scheduler"]

        async def execute_due_action(self, **kwargs):
            return None

    monkeypatch.setattr(agent_runner, "DeferredActionDAO", Mock(return_value=Mock()))
    monkeypatch.setattr(
        agent_runner,
        "DeferredActionOccurrenceDAO",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(agent_runner, "DeferredActionExecutor", FakeExecutor)
    monkeypatch.setattr(
        agent_runner,
        "DeferredActionScheduler",
        Mock(return_value=scheduler),
    )
    monkeypatch.setattr(
        agent_runner,
        "set_deferred_action_scheduler_instance",
        set_instance,
    )
    monkeypatch.setattr(
        agent_runner,
        "get_deferred_action_scheduler_instance",
        Mock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="deferred start failed"):
        agent_runner.bootstrap_deferred_action_runtime()

    scheduler.shutdown.assert_called_once()
    assert set_instance.call_args_list == [
        call(scheduler),
        call(None),
    ]


def test_bootstrap_reminder_runtime_starts_single_scheduler(monkeypatch):
    agent_runner = import_agent_runner_with_stubs(monkeypatch)

    reminder_dao = Mock()
    handler = Mock()
    scheduler = Mock(start=Mock(), shutdown=Mock())
    set_instance = Mock()
    get_instance = Mock(return_value=None)
    created = {}

    monkeypatch.setattr(agent_runner, "ReminderDAO", lambda: reminder_dao)
    monkeypatch.setattr(agent_runner, "ReminderFireEventHandler", lambda: handler)
    monkeypatch.setattr(
        agent_runner,
        "ReminderScheduler",
        lambda **kwargs: created.update({"scheduler_kwargs": kwargs}) or scheduler,
    )
    monkeypatch.setattr(agent_runner, "set_reminder_scheduler_instance", set_instance)
    monkeypatch.setattr(agent_runner, "get_reminder_scheduler_instance", get_instance)

    runtime = agent_runner.bootstrap_reminder_runtime()

    assert runtime is scheduler
    scheduler.start.assert_called_once()
    set_instance.assert_called_once_with(scheduler)
    assert created["scheduler_kwargs"]["reminder_dao"] is reminder_dao
    assert created["scheduler_kwargs"]["fire_event_handler"] is handler


def test_bootstrap_reminder_runtime_cleans_up_when_start_raises(monkeypatch):
    agent_runner = import_agent_runner_with_stubs(monkeypatch)

    scheduler = Mock(
        start=Mock(side_effect=RuntimeError("reminder start failed")),
        shutdown=Mock(),
    )
    set_instance = Mock()

    monkeypatch.setattr(agent_runner, "ReminderDAO", Mock(return_value=Mock()))
    monkeypatch.setattr(
        agent_runner,
        "ReminderFireEventHandler",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        agent_runner,
        "ReminderScheduler",
        Mock(return_value=scheduler),
    )
    monkeypatch.setattr(agent_runner, "set_reminder_scheduler_instance", set_instance)
    monkeypatch.setattr(
        agent_runner,
        "get_reminder_scheduler_instance",
        Mock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="reminder start failed"):
        agent_runner.bootstrap_reminder_runtime()

    scheduler.shutdown.assert_called_once()
    assert set_instance.call_args_list == [
        call(scheduler),
        call(None),
    ]


@pytest.mark.asyncio
async def test_main_cleans_up_deferred_scheduler_when_reminder_startup_fails(
    monkeypatch,
):
    agent_runner = import_agent_runner_with_stubs(monkeypatch)

    deferred_scheduler = Mock(shutdown=Mock())
    set_deferred_instance = Mock()
    set_reminder_instance = Mock()

    monkeypatch.setattr(
        agent_runner,
        "bootstrap_deferred_action_runtime",
        Mock(return_value=deferred_scheduler),
    )
    monkeypatch.setattr(
        agent_runner,
        "bootstrap_reminder_runtime",
        Mock(side_effect=RuntimeError("reminder start failed")),
    )
    monkeypatch.setattr(
        agent_runner,
        "set_deferred_action_scheduler_instance",
        set_deferred_instance,
    )
    monkeypatch.setattr(
        agent_runner, "set_reminder_scheduler_instance", set_reminder_instance
    )

    with pytest.raises(RuntimeError, match="reminder start failed"):
        await agent_runner.main()

    deferred_scheduler.shutdown.assert_called_once()
    set_deferred_instance.assert_called_once_with(None)
    set_reminder_instance.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_main_shutdowns_schedulers_independently_when_one_shutdown_raises(
    monkeypatch,
):
    agent_runner = import_agent_runner_with_stubs(monkeypatch)

    deferred_scheduler = Mock(shutdown=Mock(side_effect=RuntimeError("deferred boom")))
    reminder_scheduler = Mock(shutdown=Mock())
    set_deferred_instance = Mock()
    set_reminder_instance = Mock()

    async def failing_gather(*workers):
        for worker in workers:
            worker.close()
        raise RuntimeError("worker stopped")

    monkeypatch.setattr(
        agent_runner,
        "bootstrap_deferred_action_runtime",
        Mock(return_value=deferred_scheduler),
    )
    monkeypatch.setattr(
        agent_runner,
        "bootstrap_reminder_runtime",
        Mock(return_value=reminder_scheduler),
    )
    monkeypatch.setattr(agent_runner.asyncio, "gather", failing_gather)
    monkeypatch.setattr(
        agent_runner,
        "set_deferred_action_scheduler_instance",
        set_deferred_instance,
    )
    monkeypatch.setattr(
        agent_runner, "set_reminder_scheduler_instance", set_reminder_instance
    )

    with pytest.raises(RuntimeError, match="worker stopped"):
        await agent_runner.main()

    deferred_scheduler.shutdown.assert_called_once()
    reminder_scheduler.shutdown.assert_called_once()
    set_deferred_instance.assert_called_once_with(None)
    set_reminder_instance.assert_called_once_with(None)
