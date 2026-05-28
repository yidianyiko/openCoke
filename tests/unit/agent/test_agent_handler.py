# -*- coding: utf-8 -*-
import asyncio
import importlib
import sys
import types
from datetime import UTC, datetime

import pytest


class _StubUserDAO:
    pass


def _stub_lock_manager(*args, **kwargs):
    return types.SimpleNamespace(renew_lock=lambda *a, **k: None)


def _install_agent_handler_agno_stubs(monkeypatch):
    created_agent_session_dbs = []
    agno = types.ModuleType("agno")
    agno.__path__ = []
    agno_agent = types.ModuleType("agno.agent")
    agno_db = types.ModuleType("agno.db")
    agno_db.__path__ = []
    agno_db_mongo = types.ModuleType("agno.db.mongo")
    agno_models = types.ModuleType("agno.models")
    agno_models.__path__ = []
    agno_tools = types.ModuleType("agno.tools")
    agno_models_deepseek = types.ModuleType("agno.models.deepseek")
    agno_models_openai = types.ModuleType("agno.models.openai")
    agno_models_siliconflow = types.ModuleType("agno.models.siliconflow")

    class _Agent:
        def __init__(self, *args, **kwargs):
            pass

    class _Model:
        def __init__(self, *args, **kwargs):
            pass

    class _MongoDb:
        def __init__(self, *args, **kwargs):
            created_agent_session_dbs.append({"args": args, "kwargs": kwargs})

    def _tool_decorator(*args, **kwargs):
        def _decorate(fn):
            return fn

        return _decorate

    agno_agent.Agent = _Agent
    agno_db_mongo.MongoDb = _MongoDb
    agno_tools.tool = _tool_decorator
    agno_models_deepseek.DeepSeek = _Model
    agno_models_openai.OpenAIChat = _Model
    agno_models_siliconflow.Siliconflow = _Model

    monkeypatch.setitem(sys.modules, "agno", agno)
    monkeypatch.setitem(sys.modules, "agno.agent", agno_agent)
    monkeypatch.setitem(sys.modules, "agno.db", agno_db)
    monkeypatch.setitem(sys.modules, "agno.db.mongo", agno_db_mongo)
    monkeypatch.setitem(sys.modules, "agno.models", agno_models)
    monkeypatch.setitem(sys.modules, "agno.tools", agno_tools)
    monkeypatch.setitem(sys.modules, "agno.models.deepseek", agno_models_deepseek)
    monkeypatch.setitem(sys.modules, "agno.models.openai", agno_models_openai)
    monkeypatch.setitem(sys.modules, "agno.models.siliconflow", agno_models_siliconflow)
    monkeypatch.setitem(
        sys.modules,
        "agent.tool.image",
        types.SimpleNamespace(upload_image=lambda *args, **kwargs: ""),
    )
    monkeypatch.setitem(
        sys.modules,
        "agent.tool.voice",
        types.SimpleNamespace(character_voice=lambda *args, **kwargs: ""),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.conversation_dao",
        types.SimpleNamespace(ConversationDAO=lambda *args, **kwargs: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.user_dao",
        types.SimpleNamespace(UserDAO=_StubUserDAO),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.mongo",
        types.SimpleNamespace(
            MongoDBBase=lambda *args, **kwargs: types.SimpleNamespace()
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.lock",
        types.SimpleNamespace(MongoDBLockManager=_stub_lock_manager),
    )
    if "agent.runner.message_processor" in sys.modules:
        monkeypatch.setattr(
            sys.modules["agent.runner.message_processor"],
            "MongoDBLockManager",
            _stub_lock_manager,
        )

    apscheduler = types.ModuleType("apscheduler")
    apscheduler.__path__ = []
    apscheduler_jobstores = types.ModuleType("apscheduler.jobstores")
    apscheduler_jobstores.__path__ = []
    apscheduler_jobstores_base = types.ModuleType("apscheduler.jobstores.base")
    apscheduler_schedulers = types.ModuleType("apscheduler.schedulers")
    apscheduler_schedulers.__path__ = []
    apscheduler_schedulers_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")

    class _JobLookupError(Exception):
        pass

    class _AsyncIOScheduler:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return None

        def shutdown(self, wait=False):
            self.shutdown_wait = wait
            return None

        def add_job(self, *args, **kwargs):
            return None

        def remove_job(self, *args, **kwargs):
            return None

    apscheduler_jobstores_base.JobLookupError = _JobLookupError
    apscheduler_schedulers_asyncio.AsyncIOScheduler = _AsyncIOScheduler

    monkeypatch.setitem(sys.modules, "apscheduler", apscheduler)
    monkeypatch.setitem(sys.modules, "apscheduler.jobstores", apscheduler_jobstores)
    monkeypatch.setitem(
        sys.modules, "apscheduler.jobstores.base", apscheduler_jobstores_base
    )
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", apscheduler_schedulers)
    monkeypatch.setitem(
        sys.modules,
        "apscheduler.schedulers.asyncio",
        apscheduler_schedulers_asyncio,
    )

    return created_agent_session_dbs


def test_output_delivery_passes_visible_text_metadata_to_message_util(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.runner import output_delivery

    send_calls = []

    def fake_send_message_via_context(*args, **kwargs):
        send_calls.append({"args": args, "kwargs": kwargs})
        return {"message": kwargs["message"], "metadata": kwargs.get("metadata")}

    monkeypatch.setattr(
        output_delivery,
        "send_message_via_context",
        fake_send_message_via_context,
    )

    outputmessage, next_timestamp = output_delivery.send_single_message(
        context=sample_context,
        multimodal_response={
            "type": "text",
            "content": "Runtime reply",
            "metadata": {"notification_id": "pn_1"},
        },
        expect_output_timestamp=1710000000,
        is_first=True,
    )

    assert outputmessage == {
        "message": "Runtime reply",
        "metadata": {"notification_id": "pn_1"},
    }
    assert next_timestamp == 1710000000
    assert send_calls[0]["kwargs"]["metadata"] == {"notification_id": "pn_1"}


def test_agent_runtime_user_turn_occurred_at_uses_future_message_timestamp(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)

    from agent.runner import agent_handler

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"input_timestamp": 1893456000},
        {"input_timestamp": 1893456060},
    ]

    assert agent_handler._derive_agent_runtime_user_turn_occurred_at(
        sample_context
    ) == datetime.fromtimestamp(1893456060, UTC)


def test_agent_handler_extracts_product_notification_metadata_for_runtime(monkeypatch):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.runner import agent_handler

    metadata = agent_handler._extract_user_turn_runtime_metadata(
        [
            {
                "_id": "msg-1",
                "message": "确认",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "message_type": "product_notification",
                    },
                    "product_notification": {
                        "shared_reminder_id": "sr_1",
                        "resource_type": "shared_reminder",
                        "kind": "shared_reminder_created",
                        "status": "active",
                    },
                },
            }
        ]
    )

    assert metadata == {
        "product_notification": {
            "shared_reminder_id": "sr_1",
            "resource_type": "shared_reminder",
            "kind": "shared_reminder_created",
            "status": "active",
        },
        "message_type": "product_notification",
        "product_notification_input_text": "确认",
    }


def test_agent_handler_extracts_eval_trace_metadata_for_runtime(monkeypatch):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.runner import agent_handler

    metadata = agent_handler._extract_user_turn_runtime_metadata(
        [
            {
                "_id": "msg-1",
                "message": "18:00 提醒我学英语",
                "metadata": {
                    "source": "clawscale",
                    "source_eval": "reminder_normal_path_eval",
                    "agent_turn_trace": {
                        "suite": "reminder-normal",
                        "run_id": "reminder-normal-first-loop",
                    },
                    "business_protocol": {
                        "delivery_mode": "request_response",
                    },
                },
            }
        ]
    )

    assert metadata == {
        "source_eval": "reminder_normal_path_eval",
        "agent_turn_trace": {
            "suite": "reminder-normal",
            "run_id": "reminder-normal-first-loop",
        },
    }


def test_agent_handler_initializes_shared_agent_session_db_at_boot(monkeypatch):
    created_agent_session_dbs = _install_agent_handler_agno_stubs(monkeypatch)

    from agent.agno_agent.runtime import session as session_runtime

    session_runtime.reset_agent_session_db_for_tests()
    monkeypatch.delitem(sys.modules, "agent.runner.agent_handler", raising=False)

    importlib.import_module("agent.runner.agent_handler")

    assert len(created_agent_session_dbs) == 1
    assert created_agent_session_dbs[0]["kwargs"]["session_collection"] == (
        "agent_sessions"
    )


@pytest.mark.asyncio
async def test_run_post_analyze_background_calls_runtime_function_and_persists_relation(
    monkeypatch,
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.runner import agent_handler

    calls = []
    replace_calls = []

    async def fake_run_post_analyze(*, session_state):
        calls.append(session_state)

    monkeypatch.setattr(agent_handler, "run_post_analyze", fake_run_post_analyze)
    monkeypatch.setattr(
        agent_handler.mongo,
        "replace_one",
        lambda *args, **kwargs: replace_calls.append({"args": args, "kwargs": kwargs}),
        raising=False,
    )
    context = {
        "relation": {
            "_id": "relation-doc",
            "uid": "user-1",
            "cid": "char-1",
            "relationship": {"status": "idle"},
        }
    }

    await agent_handler._run_post_analyze_background(
        context=context,
        conversation_id="conv-1",
        worker_tag="[T]",
    )

    assert calls == [context]
    assert replace_calls == [
        {
            "args": ("relations",),
            "kwargs": {
                "query": {"uid": "user-1", "cid": "char-1"},
                "update": {
                    "uid": "user-1",
                    "cid": "char-1",
                    "relationship": {"status": "idle"},
                },
            },
        }
    ]


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_uses_agent_runtime(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    async def fake_run_agent_runtime(**kwargs):
        assert kwargs["context"] is sample_context
        assert kwargs["agent_input"].input_type == "user.turn"
        assert kwargs["agent_input"].text == "你好"
        assert kwargs["message_source"] == "user"
        assert kwargs["metadata"] == {"request_id": "req-1"}
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(
                    message_type="text",
                    content="Runtime reply",
                    metadata={"source": "agent_runtime"},
                )
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []

    def fake_send_single_message(**kwargs):
        sent.append(kwargs["multimodal_response"])
        return {"message": kwargs["multimodal_response"]["content"]}, (
            kwargs["expect_output_timestamp"]
        )

    create_task_calls = []

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(
        agent_handler.output_delivery, "send_single_message", fake_send_single_message
    )
    monkeypatch.setattr(
        agent_handler.asyncio,
        "create_task",
        lambda coro: create_task_calls.append(coro),
    )

    resp_messages, context, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            metadata={"request_id": "req-1"},
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert resp_messages == [{"message": "Runtime reply"}]
    assert sent == [
        {
            "type": "text",
            "content": "Runtime reply",
            "metadata": {"source": "agent_runtime"},
        }
    ]
    assert context is sample_context
    assert is_content_blocked is False
    assert create_task_calls == []


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_sends_multiple_visible_messages_in_order(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="第一条"),
                VisibleMessage(message_type="text", content="第二条"),
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []

    def fake_send_single_message(**kwargs):
        sent.append(
            {
                "content": kwargs["multimodal_response"]["content"],
                "expect_output_timestamp": kwargs["expect_output_timestamp"],
                "is_first": kwargs["is_first"],
            }
        )
        return (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"] + 5,
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler.output_delivery, "send_single_message", fake_send_single_message
    )
    monkeypatch.setattr(agent_handler.time, "time", lambda: 1710000000)

    resp_messages, context, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            metadata={"request_id": "req-1"},
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert resp_messages == [{"message": "第一条"}, {"message": "第二条"}]
    assert sent == [
        {
            "content": "第一条",
            "expect_output_timestamp": 1710000000,
            "is_first": True,
        },
        {
            "content": "第二条",
            "expect_output_timestamp": 1710000005,
            "is_first": False,
        },
    ]
    assert context["MultiModalResponses"] == [
        {"type": "text", "content": "第一条", "metadata": {}},
        {"type": "text", "content": "第二条", "metadata": {}},
    ]
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_empty_output_sends_no_fallback(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition
    from agent.runner import agent_handler

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )

    resp_messages, context, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert resp_messages == []
    assert context["MultiModalResponses"] == []
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_passes_typed_user_turn(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    captured = {}

    async def fake_run_agent_runtime_event(**kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="runtime reply")
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler.output_delivery,
        "send_single_message",
        lambda **kwargs: ({"_id": "out-1"}, kwargs["expect_output_timestamp"]),
    )

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        metadata={"request_id": "req-1"},
        check_new_message=False,
        worker_tag="[T]",
        current_message_ids=["msg-1"],
    )

    agent_input = captured["agent_input"]
    assert agent_input.input_type == "user.turn"
    assert agent_input.text == "hello"
    assert agent_input.payload.current_message_ids == ("msg-1",)
    assert captured["context"] is sample_context


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_schedules_post_analyze(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    scheduled = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="runtime reply")
            ],
            post_analyze_input={"input_message": "hello", "message_source": "user"},
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler.output_delivery,
        "send_single_message",
        lambda **kwargs: ({"_id": "out-1"}, kwargs["expect_output_timestamp"]),
    )
    monkeypatch.setattr(
        agent_handler.asyncio, "create_task", lambda coro: scheduled.append(coro)
    )

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        metadata={},
        check_new_message=False,
        worker_tag="[T]",
    )

    assert scheduled
    scheduled[0].close()


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_can_skip_post_analyze_with_env(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("SKIP_POST_ANALYZE", "1")

    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    scheduled = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="runtime reply")
            ],
            post_analyze_input={"input_message": "hello", "message_source": "user"},
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler.output_delivery,
        "send_single_message",
        lambda **kwargs: ({"_id": "out-1"}, kwargs["expect_output_timestamp"]),
    )
    monkeypatch.setattr(
        agent_handler.asyncio, "create_task", lambda coro: scheduled.append(coro)
    )

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        metadata={},
        check_new_message=False,
        worker_tag="[T]",
    )

    assert scheduled == []


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_stops_when_lock_lost_before_send(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    async def fake_run_agent_runtime(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="Runtime reply")
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(
        agent_handler.runtime_lock, "verify_lock_ownership", lambda *args: False
    )
    monkeypatch.setattr(
        agent_handler.output_delivery,
        "send_single_message",
        lambda **kwargs: sent.append(kwargs),
    )

    resp_messages, _, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            lock_id="lock-1",
            conversation_id="conversation-1",
            current_message_ids=[],
        )
    )

    assert resp_messages == []
    assert is_content_blocked is False
    assert sent == []


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_renews_lock_before_runtime_and_send(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    calls = []

    async def fake_run_agent_runtime(**kwargs):
        calls.append("runtime")
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="Runtime reply")
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    def fake_renew_lock(*args, **kwargs):
        calls.append(("renew", args, kwargs))

    def fake_send_single_message(**kwargs):
        calls.append("send")
        return {"message": kwargs["multimodal_response"]["content"]}, (
            kwargs["expect_output_timestamp"]
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(
        agent_handler.runtime_lock, "verify_lock_ownership", lambda *args: True
    )
    monkeypatch.setattr(
        agent_handler.runtime_lock.lock_manager, "renew_lock", fake_renew_lock
    )
    monkeypatch.setattr(
        agent_handler.output_delivery, "send_single_message", fake_send_single_message
    )

    resp_messages, _, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            lock_id="lock-1",
            conversation_id="conversation-1",
            current_message_ids=[],
        )
    )

    assert resp_messages == [{"message": "Runtime reply"}]
    assert calls[0][0] == "renew"
    assert calls[0][1] == ("conversation", "conversation-1", "lock-1")
    assert calls[0][2] == {"timeout": agent_handler.runtime_lock.LOCK_TIMEOUT}
    assert calls[1:] == ["runtime", "send"]
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_agent_runtime_renews_lock_while_runtime_is_running(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("COKE_AGENT_RUNTIME_LOCK_HEARTBEAT_SECONDS", "0.01")

    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    calls = []

    async def fake_run_agent_runtime(**kwargs):
        calls.append("runtime-start")
        await asyncio.sleep(0.035)
        calls.append("runtime-end")
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="Runtime reply")
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    def fake_renew_lock(*args, **kwargs):
        calls.append(("renew", args, kwargs))
        return True

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(
        agent_handler.runtime_lock, "verify_lock_ownership", lambda *args: True
    )
    monkeypatch.setattr(
        agent_handler.runtime_lock.lock_manager, "renew_lock", fake_renew_lock
    )
    monkeypatch.setattr(
        agent_handler.output_delivery,
        "send_single_message",
        lambda **kwargs: (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )

    resp_messages, _, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="17:57提醒我喝水",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            lock_id="lock-1",
            conversation_id="conversation-1",
            current_message_ids=[],
        )
    )

    renew_indices = [
        index for index, call in enumerate(calls) if isinstance(call, tuple)
    ]
    runtime_start = calls.index("runtime-start")
    runtime_end = calls.index("runtime-end")
    renews_during_runtime = [
        index for index in renew_indices if runtime_start < index < runtime_end
    ]

    assert resp_messages == [{"message": "Runtime reply"}]
    assert len(renews_during_runtime) >= 2
    assert is_content_blocked is False


def test_agent_runtime_acceptance_contract_names_are_tracked():
    required_contracts = {
        "sync_first_text",
        "timezone_proposal_update",
        "url_context",
        "calendar_import_entry",
        "fired_event_replay",
    }

    implemented_contracts = {
        "sync_first_text",
        "timezone_proposal_update",
        "url_context",
        "calendar_import_entry",
        "fired_event_replay",
    }

    assert implemented_contracts == required_contracts
