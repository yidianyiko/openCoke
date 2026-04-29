# -*- coding: utf-8 -*-

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_explicit_reminder_request_runs_detector_when_orchestrator_misses_it():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "普通对话",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "请在一分钟后提醒我：这是本地一分钟主动提醒烟测。",
            session_state,
        )

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True


@pytest.mark.asyncio
async def test_nickname_only_call_me_does_not_run_reminder_detector():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "用户希望被称呼为小凡",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("叫我小凡就行了", session_state)

    reminder_detect_agent.arun.assert_not_awaited()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is False


@pytest.mark.asyncio
async def test_call_me_with_time_runs_reminder_detector_when_orchestrator_misses_it():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "普通对话",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("七点叫我可以么", session_state)

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True


@pytest.mark.asyncio
async def test_vague_reminder_capability_question_uses_detector_not_direct_reply():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "用户询问提醒能力",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("你可以循环提醒我吗", session_state)

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    assert "direct_reply" not in result["session_state"]


@pytest.mark.asyncio
async def test_underspecified_reminder_request_uses_detector_not_direct_reply():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "bare reminder request",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("你提醒我一下", session_state)

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    assert "direct_reply" not in result["session_state"]


@pytest.mark.asyncio
async def test_orchestrator_timeout_still_runs_detector_for_explicit_reminder(
    monkeypatch,
):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    async def slow_orchestrator(*_args, **_kwargs):
        await asyncio.sleep(60)

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(side_effect=slow_orchestrator)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "今天17:57提醒我喝水，17:58提醒我锻炼",
            session_state,
        )

    assert result["session_state"]["prepare_orchestrator_timeout"] is True
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    reminder_detect_agent.arun.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_timeout_routes_time_prefixed_reminder_to_detector(
    monkeypatch,
):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    async def slow_orchestrator(*_args, **_kwargs):
        await asyncio.sleep(60)

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日11时51分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(side_effect=slow_orchestrator)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "另外10:40提醒思考一个问题：工作应该去做“非我不可”的事情",
            session_state,
        )

    assert result["session_state"]["prepare_orchestrator_timeout"] is True
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    reminder_detect_agent.arun.assert_awaited_once()


@pytest.mark.asyncio
async def test_reminder_detect_timeout_records_failed_tool_result(monkeypatch):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "提醒请求",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    async def slow_reminder_detect(*_args, **_kwargs):
        await asyncio.sleep(60)

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("稍后提醒我喝水", session_state)

    [tool_result] = result["session_state"]["tool_results"]
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert tool_result["tool_name"] == "提醒操作"
    assert tool_result["ok"] is False
    assert "提醒识别超时" in tool_result["result_summary"]


def test_reminder_detect_retry_default_timeout_allows_fast_llm_budget():
    from agent.agno_agent.workflows import prepare_workflow

    assert prepare_workflow._PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS >= 30.0


@pytest.mark.asyncio
async def test_reminder_detect_timeout_retries_with_short_context_llm(monkeypatch):
    from agent.agno_agent.tools.tool_result import append_tool_result
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "提醒请求",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    async def slow_reminder_detect(*_args, **_kwargs):
        await asyncio.sleep(60)

    retry_response = MagicMock()
    retry_response.metrics = None
    retry_response.tools = [{"tool_name": "visible_reminder_tool"}]

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [{"role": "user", "content": "old context"}],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    async def retry_detect(*_args, **_kwargs):
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=True,
            result_summary="已创建提醒：喝水",
        )
        return retry_response

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=retry_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("稍后提醒我喝水", session_state)

    retry_input = reminder_detect_retry_agent.arun.await_args.kwargs["input"]
    assert "最近对话上下文" not in retry_input
    assert "当前用户消息" in retry_input
    assert "Full-context reminder detection timed out" in retry_input
    assert "explicitly asks for a reminder" in retry_input
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert result["session_state"]["prepare_reminder_detect_retry_used"] is True
    assert result["session_state"]["tool_results"][0]["ok"] is True
    assert (
        "提醒识别超时"
        not in result["session_state"]["tool_results"][0]["result_summary"]
    )


@pytest.mark.asyncio
async def test_reminder_detect_timeout_does_not_create_with_local_parser(monkeypatch):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "提醒请求",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    async def slow_reminder_detect(*_args, **_kwargs):
        await asyncio.sleep(60)

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }
    local_tool_calls = []

    def fake_visible_reminder_tool(**kwargs):
        local_tool_calls.append(kwargs)
        return "should not be called"

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        prepare_workflow,
        "visible_reminder_tool",
        fake_visible_reminder_tool,
        raising=False,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "明天继续提醒我看文章，要看完，然后要写学习笔记。小说明天也继续写！",
            session_state,
        )

    assert local_tool_calls == []
    [tool_result] = result["session_state"]["tool_results"]
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert tool_result["ok"] is False
    assert "提醒识别超时" in tool_result["result_summary"]
