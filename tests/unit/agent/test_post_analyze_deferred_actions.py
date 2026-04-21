from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


def build_session_state():
    return {
        "user": {"id": "user-1", "_id": "user-1", "timezone": "UTC"},
        "character": {"_id": "char-1"},
        "conversation": {
            "_id": "conv-1",
            "conversation_info": {
                "time_str": "2026年04月21日09时00分",
                "input_messages_str": "hi",
                "chat_history": [],
            },
        },
        "context_retrieve": {
            "character_global": "",
            "character_private": "",
            "user": "",
        },
        "relation": {
            "relationship": {
                "closeness": 0,
                "trustness": 0,
                "description": "",
                "dislike": 0,
                "status": "idle",
            },
            "user_info": {"realname": "", "hobbyname": "", "description": ""},
            "character_info": {
                "longterm_purpose": "",
                "shortterm_purpose": "",
                "attitude": "",
            },
        },
        "MultiModalResponses": [],
        "message_source": "user",
        "proactive_times": 0,
    }


@pytest.mark.asyncio
async def test_post_analyze_creates_internal_followup(monkeypatch):
    from agent.agno_agent.workflows import post_analyze_workflow as workflow_module

    workflow = workflow_module.PostAnalyzeWorkflow()
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    monkeypatch.setattr(workflow_module, "DeferredActionService", lambda: service)
    monkeypatch.setattr(
        workflow_module.post_analyze_agent,
        "arun",
        AsyncMock(
            return_value=SimpleNamespace(
                content={
                    "RelationChange": {"Closeness": 0, "Trustness": 0},
                    "FollowupPlan": {
                        "FollowupAction": "create",
                        "FollowupTime": "2026年04月21日12时00分",
                        "FollowupPrompt": "中午记得汇报进度",
                    },
                }
            )
        ),
    )

    await workflow.run(build_session_state())

    service.create_or_replace_internal_followup.assert_called_once()
    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["conversation_id"] == "conv-1"
    assert kwargs["payload_metadata"] == {"proactive_times": 0}
    service.clear_internal_followup.assert_not_called()


@pytest.mark.asyncio
async def test_post_analyze_replaces_internal_followup_after_proactive_message(
    monkeypatch,
):
    from agent.agno_agent.workflows import post_analyze_workflow as workflow_module

    workflow = workflow_module.PostAnalyzeWorkflow()
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    state = build_session_state()
    state["message_source"] = "deferred_action"
    state["system_message_metadata"] = {"kind": "proactive_followup"}
    state["proactive_times"] = 1
    monkeypatch.setattr(workflow_module, "DeferredActionService", lambda: service)
    monkeypatch.setattr(
        workflow_module.post_analyze_agent,
        "arun",
        AsyncMock(
            return_value=SimpleNamespace(
                content={
                    "RelationChange": {"Closeness": 0, "Trustness": 0},
                    "FollowupPlan": {
                        "FollowupAction": "replace",
                        "FollowupTime": "2026年04月22日09时00分",
                        "FollowupPrompt": "明早问一下今天计划",
                    },
                }
            )
        ),
    )

    await workflow.run(state)

    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["payload_metadata"] == {"proactive_times": 2}


@pytest.mark.asyncio
async def test_post_analyze_clears_internal_followup(monkeypatch):
    from agent.agno_agent.workflows import post_analyze_workflow as workflow_module

    workflow = workflow_module.PostAnalyzeWorkflow()
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    monkeypatch.setattr(workflow_module, "DeferredActionService", lambda: service)
    monkeypatch.setattr(
        workflow_module.post_analyze_agent,
        "arun",
        AsyncMock(
            return_value=SimpleNamespace(
                content={
                    "RelationChange": {"Closeness": 0, "Trustness": 0},
                    "FollowupPlan": {
                        "FollowupAction": "clear",
                        "FollowupTime": "",
                        "FollowupPrompt": "无",
                    },
                }
            )
        ),
    )

    await workflow.run(build_session_state())

    service.clear_internal_followup.assert_called_once_with("conv-1")
    service.create_or_replace_internal_followup.assert_not_called()


@pytest.mark.asyncio
async def test_post_analyze_skips_followup_when_timed_reminder_created(monkeypatch):
    from agent.agno_agent.workflows import post_analyze_workflow as workflow_module

    workflow = workflow_module.PostAnalyzeWorkflow()
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    state = build_session_state()
    state["reminder_created_with_time"] = True
    monkeypatch.setattr(workflow_module, "DeferredActionService", lambda: service)
    monkeypatch.setattr(
        workflow_module.post_analyze_agent,
        "arun",
        AsyncMock(
            return_value=SimpleNamespace(
                content={
                    "RelationChange": {"Closeness": 0, "Trustness": 0},
                    "FollowupPlan": {
                        "FollowupAction": "create",
                        "FollowupTime": "2026年04月21日12时00分",
                        "FollowupPrompt": "中午记得汇报进度",
                    },
                }
            )
        ),
    )

    await workflow.run(state)

    service.clear_internal_followup.assert_called_once_with("conv-1")
    service.create_or_replace_internal_followup.assert_not_called()
