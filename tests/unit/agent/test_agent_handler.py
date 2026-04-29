# -*- coding: utf-8 -*-
import asyncio
import sys
import types

import pytest


class _StubUserDAO:
    pass


def _install_agent_handler_agno_stubs(monkeypatch):
    agno = types.ModuleType("agno")
    agno.__path__ = []
    agno_agent = types.ModuleType("agno.agent")
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

    def _tool_decorator(*args, **kwargs):
        def _decorate(fn):
            return fn

        return _decorate

    agno_agent.Agent = _Agent
    agno_tools.tool = _tool_decorator
    agno_models_deepseek.DeepSeek = _Model
    agno_models_openai.OpenAIChat = _Model
    agno_models_siliconflow.Siliconflow = _Model

    monkeypatch.setitem(sys.modules, "agno", agno)
    monkeypatch.setitem(sys.modules, "agno.agent", agno_agent)
    monkeypatch.setitem(sys.modules, "agno.models", agno_models)
    monkeypatch.setitem(sys.modules, "agno.tools", agno_tools)
    monkeypatch.setitem(sys.modules, "agno.models.deepseek", agno_models_deepseek)
    monkeypatch.setitem(sys.modules, "agno.models.openai", agno_models_openai)
    monkeypatch.setitem(sys.modules, "agno.models.siliconflow", agno_models_siliconflow)

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


@pytest.mark.asyncio
async def test_handle_message_marks_stream_provider_error_for_rollback(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
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
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            MessageAcquirer=lambda *args, **kwargs: types.SimpleNamespace(
                acquire=lambda: None,
                renew_lock=lambda *a, **k: None,
                release_lock=lambda *a, **k: None,
            ),
            MessageDispatcher=lambda *args, **kwargs: object(),
            MessageFinalizer=lambda *args, **kwargs: object(),
        ),
    )

    from agent.runner import agent_handler

    async def fake_prepare_run(input_message, session_state):
        return {"session_state": session_state}

    async def fake_run_stream(input_message, session_state):
        yield {"type": "error", "data": {"error": "500 Internal Server Error"}}

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler.streaming_chat_workflow, "run_stream", fake_run_stream
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)

    resp_messages, _, is_rollback, is_content_blocked = (
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
    assert is_rollback is True
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_skips_post_analyze_for_deferred_actions(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
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
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            MessageAcquirer=lambda *args, **kwargs: types.SimpleNamespace(
                acquire=lambda: None,
                renew_lock=lambda *a, **k: None,
                release_lock=lambda *a, **k: None,
            ),
            MessageDispatcher=lambda *args, **kwargs: object(),
            MessageFinalizer=lambda *args, **kwargs: object(),
        ),
    )

    from agent.runner import agent_handler

    async def fake_prepare_run(input_message, session_state):
        return {"session_state": session_state}

    async def fake_run_stream(input_message, session_state):
        yield {"type": "message", "data": {"type": "text", "content": "提醒一下"}}
        yield {"type": "done", "data": {"total_messages": 1}}

    create_task_calls = []

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler.streaming_chat_workflow, "run_stream", fake_run_stream
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )
    monkeypatch.setattr(
        agent_handler.asyncio,
        "create_task",
        lambda coro: create_task_calls.append(coro),
    )

    resp_messages, _, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="[系统提醒触发] 喝水",
            message_source="deferred_action",
            metadata={"kind": "user_reminder"},
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert len(resp_messages) == 1
    assert is_rollback is False
    assert is_content_blocked is False
    assert create_task_calls == []


@pytest.mark.asyncio
async def test_handle_message_finishes_sync_business_text_after_first_reply(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
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
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            MessageAcquirer=lambda *args, **kwargs: types.SimpleNamespace(
                acquire=lambda: None,
                renew_lock=lambda *a, **k: None,
                release_lock=lambda *a, **k: None,
            ),
            MessageDispatcher=lambda *args, **kwargs: object(),
            MessageFinalizer=lambda *args, **kwargs: object(),
        ),
    )

    from agent.runner import agent_handler

    sample_context["conversation"]["platform"] = "business"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "causal_inbound_event_id": "in_evt_1",
                },
            }
        }
    ]

    async def fake_prepare_run(input_message, session_state):
        return {"session_state": session_state}

    sent = []
    second_chunk_requested = False

    async def fake_run_stream(input_message, session_state):
        nonlocal second_chunk_requested
        yield {"type": "message", "data": {"type": "text", "content": "第一段"}}
        assert sent == [{"type": "text", "content": "第一段"}]
        second_chunk_requested = True
        yield {"type": "message", "data": {"type": "text", "content": "第二段"}}
        yield {"type": "done", "data": {"total_messages": 2}}

    def fake_send_single_message(**kwargs):
        content = kwargs["multimodal_response"]["content"]
        sent.append(kwargs["multimodal_response"])
        return {"message": content}, kwargs["expect_output_timestamp"]

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler.streaming_chat_workflow, "run_stream", fake_run_stream
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)
    monkeypatch.setattr(agent_handler, "_send_single_message", fake_send_single_message)
    monkeypatch.setattr(agent_handler.asyncio, "create_task", lambda coro: coro.close())

    resp_messages, _, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert resp_messages == [{"message": "第一段"}]
    assert sent == [{"type": "text", "content": "第一段"}]
    assert second_chunk_requested is False
    assert is_rollback is False
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_writes_fallback_when_chat_stream_times_out(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
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
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            MessageAcquirer=lambda *args, **kwargs: types.SimpleNamespace(
                acquire=lambda: None,
                renew_lock=lambda *a, **k: None,
                release_lock=lambda *a, **k: None,
            ),
            MessageDispatcher=lambda *args, **kwargs: object(),
            MessageFinalizer=lambda *args, **kwargs: object(),
        ),
    )

    from agent.runner import agent_handler

    sample_context["conversation"]["platform"] = "business"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "causal_inbound_event_id": "in_evt_timeout",
                },
            }
        }
    ]

    async def fake_prepare_run(input_message, session_state):
        return {"session_state": session_state}

    async def fake_run_stream(input_message, session_state):
        await asyncio.sleep(0.05)
        yield {"type": "message", "data": {"type": "text", "content": "太晚了"}}

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler.streaming_chat_workflow, "run_stream", fake_run_stream
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: True)
    monkeypatch.setattr(agent_handler, "CHAT_RESPONSE_STREAM_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )
    monkeypatch.setattr(agent_handler.asyncio, "create_task", lambda coro: coro.close())

    resp_messages, context, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你还记得昨天写的计划吗",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            lock_id="lock-1",
            conversation_id="conversation-1",
            current_message_ids=[],
        )
    )

    assert len(resp_messages) == 1
    assert "计划" in resp_messages[0]["message"]
    assert context["stream_error"] == "chat_response_timeout:0.01s"
    assert is_rollback is False
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_uses_cancel_clarification_fallback_on_pending_stop_intent(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
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
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            MessageAcquirer=lambda *args, **kwargs: types.SimpleNamespace(
                acquire=lambda: None,
                renew_lock=lambda *a, **k: None,
                release_lock=lambda *a, **k: None,
            ),
            MessageDispatcher=lambda *args, **kwargs: object(),
            MessageFinalizer=lambda *args, **kwargs: object(),
        ),
    )

    from agent.runner import agent_handler

    sample_context["conversation"]["platform"] = "business"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "causal_inbound_event_id": "in_evt_timeout",
                },
            }
        }
    ]

    async def fake_prepare_run(input_message, session_state):
        session_state["orchestrator"] = {"need_reminder_detect": True}
        session_state["prepare_reminder_intent_hint"] = "stop_or_cancel"
        return {"session_state": session_state}

    async def fake_run_stream(input_message, session_state):
        await asyncio.sleep(0.05)
        yield {"type": "message", "data": {"type": "text", "content": "太晚了"}}

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler.streaming_chat_workflow, "run_stream", fake_run_stream
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: True)
    monkeypatch.setattr(agent_handler, "CHAT_RESPONSE_STREAM_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )
    monkeypatch.setattr(agent_handler.asyncio, "create_task", lambda coro: coro.close())

    resp_messages, context, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="今天学习结束，晚安，不要打扰我了",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            lock_id="lock-1",
            conversation_id="conversation-1",
            current_message_ids=[],
        )
    )

    assert len(resp_messages) == 1
    assert "哪条提醒" in resp_messages[0]["message"]
    assert "具体时间" not in resp_messages[0]["message"]
    assert context["stream_error"] == "chat_response_timeout:0.01s"
    assert is_rollback is False
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_handle_message_writes_fallback_when_chat_stream_is_empty(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
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
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        types.SimpleNamespace(
            MessageAcquirer=lambda *args, **kwargs: types.SimpleNamespace(
                acquire=lambda: None,
                renew_lock=lambda *a, **k: None,
                release_lock=lambda *a, **k: None,
            ),
            MessageDispatcher=lambda *args, **kwargs: object(),
            MessageFinalizer=lambda *args, **kwargs: object(),
        ),
    )

    from agent.runner import agent_handler

    async def fake_prepare_run(input_message, session_state):
        return {"session_state": session_state}

    async def fake_run_stream(input_message, session_state):
        yield {"type": "done", "data": {"total_messages": 0}}

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler.streaming_chat_workflow, "run_stream", fake_run_stream
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )
    monkeypatch.setattr(agent_handler.asyncio, "create_task", lambda coro: coro.close())

    resp_messages, context, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="提醒我明天写总结",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert len(resp_messages) == 1
    assert "具体时间" in resp_messages[0]["message"]
    assert context["stream_error"] == "chat_response_empty"
    assert context["MultiModalResponses"] == [
        {"type": "text", "content": resp_messages[0]["message"]}
    ]
    assert is_rollback is False
    assert is_content_blocked is False
