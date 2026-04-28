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
async def test_orchestrator_timeout_still_runs_detector_for_explicit_reminder(monkeypatch):
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
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "今天17:57提醒我喝水",
            session_state,
        )

    [tool_result] = result["session_state"]["tool_results"]
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert tool_result["tool_name"] == "提醒操作"
    assert tool_result["ok"] is False
    assert "提醒识别超时" in tool_result["result_summary"]
