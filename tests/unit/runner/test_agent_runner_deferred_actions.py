import importlib
import sys
import types
from unittest.mock import AsyncMock, Mock


def test_bootstrap_deferred_action_runtime_starts_single_scheduler(monkeypatch):
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
        types.SimpleNamespace(RedisClient=types.SimpleNamespace(from_config=lambda: None)),
    )

    sys.modules.pop("agent.runner.agent_runner", None)
    agent_runner = importlib.import_module("agent.runner.agent_runner")

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
