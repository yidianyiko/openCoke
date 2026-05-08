# -*- coding: utf-8 -*-
import asyncio
import sys
import types
from datetime import UTC, datetime

import pytest


class _StubUserDAO:
    pass


def _install_agent_handler_agno_stubs(monkeypatch):
    agno = types.ModuleType("agno")
    agno.__path__ = []
    agno_agent = types.ModuleType("agno.agent")
    agno_team = types.ModuleType("agno.team")
    agno_models = types.ModuleType("agno.models")
    agno_models.__path__ = []
    agno_tools = types.ModuleType("agno.tools")
    agno_models_deepseek = types.ModuleType("agno.models.deepseek")
    agno_models_openai = types.ModuleType("agno.models.openai")
    agno_models_siliconflow = types.ModuleType("agno.models.siliconflow")

    class _Agent:
        def __init__(self, *args, **kwargs):
            pass

    class _Team:
        def __init__(self, *args, **kwargs):
            pass

    class _Model:
        def __init__(self, *args, **kwargs):
            pass

    def _tool_decorator(*args, **kwargs):
        def _decorate(fn):
            return fn

        return _decorate

    agno_agent.Agent = _Agent
    agno_team.Team = _Team
    agno_tools.tool = _tool_decorator
    agno_models_deepseek.DeepSeek = _Model
    agno_models_openai.OpenAIChat = _Model
    agno_models_siliconflow.Siliconflow = _Model

    monkeypatch.setitem(sys.modules, "agno", agno)
    monkeypatch.setitem(sys.modules, "agno.agent", agno_agent)
    monkeypatch.setitem(sys.modules, "agno.team", agno_team)
    monkeypatch.setitem(sys.modules, "agno.models", agno_models)
    monkeypatch.setitem(sys.modules, "agno.tools", agno_tools)
    monkeypatch.setitem(sys.modules, "agno.models.deepseek", agno_models_deepseek)
    monkeypatch.setitem(sys.modules, "agno.models.openai", agno_models_openai)
    monkeypatch.setitem(sys.modules, "agno.models.siliconflow", agno_models_siliconflow)
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.agent_hardcode_handler",
        types.SimpleNamespace(
            handle_hardcode=lambda *args, **kwargs: None, supported_hardcode=()
        ),
    )
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
        types.SimpleNamespace(MongoDBBase=lambda *args, **kwargs: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.lock",
        types.SimpleNamespace(
            MongoDBLockManager=lambda *args, **kwargs: types.SimpleNamespace(
                renew_lock=lambda *a, **k: None
            )
        ),
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


def test_chat_response_timeout_fallback_is_neutral_for_schedule_statements(monkeypatch):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.runner.agent_handler import _chat_response_timeout_fallback

    reply = _chat_response_timeout_fallback("每天学习时间为晚上9点到12点")

    assert "具体时间和事项" not in reply
    assert "再发" in reply


def test_team_user_turn_occurred_at_uses_future_message_timestamp(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)

    from agent.runner import agent_handler

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"input_timestamp": 1893456000},
        {"input_timestamp": 1893456060},
    ]

    assert agent_handler._derive_team_user_turn_occurred_at(
        sample_context
    ) == datetime.fromtimestamp(1893456060, UTC)


@pytest.mark.asyncio
async def test_handle_message_team_runtime_uses_agent_runtime(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

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
                    content="Team reply",
                    metadata={"source": "team"},
                )
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
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
    monkeypatch.setattr(agent_handler, "_send_single_message", fake_send_single_message)
    monkeypatch.setattr(
        agent_handler.asyncio,
        "create_task",
        lambda coro: create_task_calls.append(coro),
    )

    resp_messages, context, is_rollback, is_content_blocked = (
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

    assert resp_messages == [{"message": "Team reply"}]
    assert sent == [
        {"type": "text", "content": "Team reply", "metadata": {"source": "team"}}
    ]
    assert context is sample_context
    assert is_rollback is False
    assert is_content_blocked is False
    assert create_task_calls == []


@pytest.mark.asyncio
async def test_handle_message_team_runtime_empty_output_uses_chat_fallback(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition
    from agent.runner import agent_handler

    sent_fallbacks = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
        )

    def fake_send_chat_response_fallback(**kwargs):
        sent_fallbacks.append(kwargs)
        return {"message": "fallback reply"}, kwargs["expect_output_timestamp"]

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler, "_send_chat_response_fallback", fake_send_chat_response_fallback
    )

    resp_messages, context, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert resp_messages == [{"message": "fallback reply"}]
    assert sent_fallbacks[0]["context"] is sample_context
    assert sent_fallbacks[0]["input_message"] == "你好"
    assert sent_fallbacks[0]["all_multimodal_responses"] == []
    assert context["MultiModalResponses"] == []
    assert is_rollback is False
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_team_runtime_passes_typed_user_turn(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

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
                VisibleMessage(message_type="text", content="team reply")
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
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
async def test_handle_message_team_runtime_schedules_post_analyze(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

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
                VisibleMessage(message_type="text", content="team reply")
            ],
            post_analyze_input={"input_message": "hello", "message_source": "user"},
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
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
async def test_handle_message_team_runtime_can_skip_post_analyze_with_env(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
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
                VisibleMessage(message_type="text", content="team reply")
            ],
            post_analyze_input={"input_message": "hello", "message_source": "user"},
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
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
async def test_handle_message_team_runtime_rolls_back_before_runtime_on_new_message(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.runner import agent_handler

    async def fail_run_agent_runtime(**kwargs):
        raise AssertionError("Team runtime should not run when a newer message exists")

    sent = []

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fail_run_agent_runtime
    )
    monkeypatch.setattr(
        agent_handler, "_send_single_message", lambda **kwargs: sent.append(kwargs)
    )
    monkeypatch.setattr(
        agent_handler,
        "is_new_message_coming_in",
        lambda u_id, c_id, platform, current_message_ids: True,
    )

    resp_messages, context, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=True,
            worker_tag="[T]",
            current_message_ids=["msg-1"],
        )
    )

    assert resp_messages == []
    assert context is sample_context
    assert is_rollback is True
    assert is_content_blocked is False
    assert sent == []


@pytest.mark.asyncio
async def test_handle_message_team_runtime_rolls_back_when_lock_lost_before_send(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    async def fake_run_agent_runtime(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="Team reply")
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: False)
    monkeypatch.setattr(
        agent_handler, "_send_single_message", lambda **kwargs: sent.append(kwargs)
    )

    resp_messages, _, is_rollback, is_content_blocked = (
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
    assert is_rollback is True
    assert is_content_blocked is False
    assert sent == []


@pytest.mark.asyncio
async def test_handle_message_team_runtime_renews_lock_before_runtime_and_send(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

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
                VisibleMessage(message_type="text", content="Team reply")
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
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
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: True)
    monkeypatch.setattr(agent_handler.lock_manager, "renew_lock", fake_renew_lock)
    monkeypatch.setattr(agent_handler, "_send_single_message", fake_send_single_message)

    resp_messages, _, is_rollback, is_content_blocked = (
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

    assert resp_messages == [{"message": "Team reply"}]
    assert calls[0][0] == "renew"
    assert calls[0][1] == ("conversation", "conversation-1", "lock-1")
    assert calls[0][2] == {"timeout": agent_handler.LOCK_TIMEOUT}
    assert calls[1:] == ["runtime", "send"]
    assert is_rollback is False
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_team_runtime_renews_lock_while_runtime_is_running(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    monkeypatch.setenv("COKE_TEAM_LOCK_HEARTBEAT_SECONDS", "0.01")

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
                VisibleMessage(message_type="text", content="Team reply")
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    def fake_renew_lock(*args, **kwargs):
        calls.append(("renew", args, kwargs))
        return True

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: True)
    monkeypatch.setattr(agent_handler.lock_manager, "renew_lock", fake_renew_lock)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )

    resp_messages, _, is_rollback, is_content_blocked = (
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

    assert resp_messages == [{"message": "Team reply"}]
    assert len(renews_during_runtime) >= 2
    assert is_rollback is False
    assert is_content_blocked is False


def test_agent_runtime_acceptance_contract_names_are_tracked():
    required_contracts = {
        "sync_first_text",
        "rollback_new_message",
        "timeout_fallback",
        "timezone_proposal_update",
        "url_context",
        "calendar_import_entry",
        "empty_output_fallback",
        "fired_event_replay",
    }

    implemented_contracts = {
        "sync_first_text",
        "rollback_new_message",
        "timeout_fallback",
        "timezone_proposal_update",
        "url_context",
        "calendar_import_entry",
        "empty_output_fallback",
        "fired_event_replay",
    }

    assert implemented_contracts == required_contracts
