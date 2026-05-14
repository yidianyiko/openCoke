from datetime import UTC, date, datetime, time
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
    monkeypatch.setattr(workflow_module, "ReminderService", lambda: service)
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

    state = build_session_state()
    state["route_key"] = "route-session"
    state["delivery_route_key"] = "route-delivery"
    state["conversation"]["route_key"] = "route-conversation"
    state["conversation"]["conversation_info"]["route_key"] = "route-info"
    state["conversation"]["conversation_info"][
        "delivery_route_key"
    ] = "route-info-delivery"

    await workflow.run(state)

    service.create_or_replace_internal_followup.assert_called_once()
    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["conversation_id"] == "conv-1"
    assert kwargs["character_id"] == "char-1"
    assert kwargs["route_key"] == "route-session"
    assert kwargs["title"] == "中午记得汇报进度"
    assert kwargs["prompt"] == "中午记得汇报进度"
    schedule = kwargs["schedule"]
    assert schedule.anchor_at == datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    assert schedule.local_date == date(2026, 4, 21)
    assert schedule.local_time == time(12, 0)
    assert schedule.local_time.tzinfo is None
    assert schedule.timezone == "UTC"
    assert schedule.rrule is None
    assert kwargs["metadata"] == {"proactive_times": 0}
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
    state["message_source"] = "reminder"
    state["system_message_metadata"] = {"kind": "internal_followup"}
    state["proactive_times"] = 1
    monkeypatch.setattr(workflow_module, "ReminderService", lambda: service)
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
    assert kwargs["route_key"] is None
    assert kwargs["metadata"] == {"proactive_times": 2}


@pytest.mark.asyncio
async def test_post_analyze_creates_internal_followup_with_alternate_id_shapes(
    monkeypatch,
):
    from agent.agno_agent.workflows import post_analyze_workflow as workflow_module

    workflow = workflow_module.PostAnalyzeWorkflow()
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    state = build_session_state()
    state["user"] = {"_id": "user-alt", "timezone": "UTC"}
    state["character"] = {"id": "char-alt"}
    state["conversation_id"] = "conv-session"
    state["conversation"] = {
        "conversation_info": {
            "time_str": "2026年04月21日09时00分",
            "input_messages_str": "hi",
            "chat_history": [],
        },
    }
    monkeypatch.setattr(workflow_module, "ReminderService", lambda: service)
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

    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["owner_user_id"] == "user-alt"
    assert kwargs["conversation_id"] == "conv-session"
    assert kwargs["character_id"] == "char-alt"


@pytest.mark.asyncio
async def test_post_analyze_clears_internal_followup(monkeypatch):
    from agent.agno_agent.workflows import post_analyze_workflow as workflow_module

    workflow = workflow_module.PostAnalyzeWorkflow()
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    monkeypatch.setattr(workflow_module, "ReminderService", lambda: service)
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

    service.clear_internal_followup.assert_called_once_with(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )
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
    monkeypatch.setattr(workflow_module, "ReminderService", lambda: service)
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

    service.clear_internal_followup.assert_called_once_with(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )
    service.create_or_replace_internal_followup.assert_not_called()
