from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.asyncio
async def test_run_post_analyze_creates_per_call_agent_without_db(monkeypatch):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    created_agents = []
    created_models = []

    class FakeAgent:
        def __init__(self, **kwargs):
            created_agents.append(kwargs)

        async def arun(self, **kwargs):
            return SimpleNamespace(content={})

    def fake_create_llm_model(**kwargs):
        created_models.append(kwargs)
        return "post-analyze-model"

    monkeypatch.setattr(post_analyze_runtime, "Agent", FakeAgent)
    monkeypatch.setattr(post_analyze_runtime, "create_llm_model", fake_create_llm_model)
    monkeypatch.setattr(
        post_analyze_runtime.usage_tracker, "record_from_metrics", Mock()
    )

    await post_analyze_runtime.run_post_analyze(build_session_state())
    await post_analyze_runtime.run_post_analyze(build_session_state())

    assert len(created_agents) == 2
    assert created_models == [
        {"role": "post_analyze", "max_tokens": 8000},
        {"role": "post_analyze", "max_tokens": 8000},
    ]
    assert all("db" not in kwargs for kwargs in created_agents)


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
                "description": "",
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


def install_reminder_service(monkeypatch, service):
    from agent.reminder import runtime as runtime_module
    from agent.reminder.runtime import ReminderRuntime
    from agent.reminder.runtime_contract import ReminderRuntimeContract

    contract = ReminderRuntimeContract(reminder_service=service)
    runtime = ReminderRuntime(
        contract=contract, scheduler=object(), fire_consumer=object()
    )
    monkeypatch.setattr(runtime_module, "_runtime_instance", runtime)


def install_post_analyze_response(monkeypatch, content):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    fake_agent = SimpleNamespace(
        arun=AsyncMock(return_value=SimpleNamespace(content=content))
    )
    monkeypatch.setattr(
        post_analyze_runtime,
        "_create_post_analyze_agent",
        Mock(return_value=fake_agent),
    )
    return fake_agent


@pytest.mark.asyncio
async def test_post_analyze_creates_internal_followup(monkeypatch):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    install_reminder_service(monkeypatch, service)
    install_post_analyze_response(
        monkeypatch,
        {
            "FollowupPlan": {
                "FollowupAction": "create",
                "FollowupTime": "2026年04月21日12时00分",
                "FollowupPrompt": "中午记得汇报进度",
            },
        },
    )

    state = build_session_state()
    state["route_key"] = "route-session"
    state["delivery_route_key"] = "route-delivery"
    state["conversation"]["route_key"] = "route-conversation"
    state["conversation"]["conversation_info"]["route_key"] = "route-info"
    state["conversation"]["conversation_info"][
        "delivery_route_key"
    ] = "route-info-delivery"

    await post_analyze_runtime.run_post_analyze(state)

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
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    state = build_session_state()
    state["message_source"] = "reminder"
    state["system_message_metadata"] = {"kind": "internal_followup"}
    state["proactive_times"] = 1
    install_reminder_service(monkeypatch, service)
    install_post_analyze_response(
        monkeypatch,
        {
            "FollowupPlan": {
                "FollowupAction": "replace",
                "FollowupTime": "2026年04月22日09时00分",
                "FollowupPrompt": "明早问一下今天计划",
            },
        },
    )

    await post_analyze_runtime.run_post_analyze(state)

    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["route_key"] is None
    assert kwargs["metadata"] == {"proactive_times": 2}


@pytest.mark.asyncio
async def test_post_analyze_creates_internal_followup_with_alternate_id_shapes(
    monkeypatch,
):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

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
    install_reminder_service(monkeypatch, service)
    install_post_analyze_response(
        monkeypatch,
        {
            "FollowupPlan": {
                "FollowupAction": "create",
                "FollowupTime": "2026年04月21日12时00分",
                "FollowupPrompt": "中午记得汇报进度",
            },
        },
    )

    await post_analyze_runtime.run_post_analyze(state)

    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["owner_user_id"] == "user-alt"
    assert kwargs["conversation_id"] == "conv-session"
    assert kwargs["character_id"] == "char-alt"


@pytest.mark.asyncio
async def test_post_analyze_clears_internal_followup(monkeypatch):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    install_reminder_service(monkeypatch, service)
    install_post_analyze_response(
        monkeypatch,
        {
            "FollowupPlan": {
                "FollowupAction": "clear",
                "FollowupTime": "",
                "FollowupPrompt": "无",
            },
        },
    )

    await post_analyze_runtime.run_post_analyze(build_session_state())

    service.clear_internal_followup.assert_called_once_with(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )
    service.create_or_replace_internal_followup.assert_not_called()


@pytest.mark.asyncio
async def test_post_analyze_skips_followup_when_timed_reminder_created(monkeypatch):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    state = build_session_state()
    state["relation"]["reminder_created_with_time"] = True
    install_reminder_service(monkeypatch, service)
    install_post_analyze_response(
        monkeypatch,
        {
            "FollowupPlan": {
                "FollowupAction": "create",
                "FollowupTime": "2026年04月21日12时00分",
                "FollowupPrompt": "中午记得汇报进度",
            },
        },
    )

    await post_analyze_runtime.run_post_analyze(state)

    service.clear_internal_followup.assert_called_once_with(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )
    service.create_or_replace_internal_followup.assert_not_called()


@pytest.mark.asyncio
async def test_post_analyze_clears_internal_followup_without_character_context(
    monkeypatch,
):
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    state = build_session_state()
    state["character"] = {}
    state["reminder_created_with_time"] = True
    install_reminder_service(monkeypatch, service)
    install_post_analyze_response(
        monkeypatch,
        {
            "FollowupPlan": {
                "FollowupAction": "create",
                "FollowupTime": "2026年04月21日12时00分",
                "FollowupPrompt": "中午记得汇报进度",
            },
        },
    )

    await post_analyze_runtime.run_post_analyze(state)

    service.clear_internal_followup.assert_called_once_with(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )
    service.create_or_replace_internal_followup.assert_not_called()


def test_post_analyze_normalization_omits_retired_relation_score_fields():
    from agent.agno_agent.runtime import post_analyze as post_analyze_runtime

    normalized = post_analyze_runtime._extract_content(SimpleNamespace(content={}))
    default_content = post_analyze_runtime._get_default_content()

    assert "RelationChange" not in normalized
    assert "Dislike" not in normalized
    assert "RelationChange" not in default_content
    assert "Dislike" not in default_content
