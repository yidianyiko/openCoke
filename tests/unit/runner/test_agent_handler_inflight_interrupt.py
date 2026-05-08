# -*- coding: utf-8 -*-

import pytest

from tests.unit.agent.test_agent_handler import _install_agent_handler_agno_stubs


@pytest.mark.asyncio
async def test_send_loop_aborts_when_new_message_arrives_between_sends(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)

    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    sample_context["platform"] = "business"

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="first reply"),
                VisibleMessage(message_type="text", content="second reply"),
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []
    new_message_checks = iter([False, False, True])

    def fake_send_single_message(**kwargs):
        sent.append(kwargs["multimodal_response"]["content"])
        return {"message": kwargs["multimodal_response"]["content"]}, (
            kwargs["expect_output_timestamp"]
        )

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: True)
    monkeypatch.setattr(agent_handler, "_team_should_skip_post_analyze", lambda: True)
    monkeypatch.setattr(agent_handler, "_send_single_message", fake_send_single_message)
    monkeypatch.setattr(
        agent_handler,
        "is_new_message_coming_in",
        lambda u_id, c_id, platform, current_message_ids: next(new_message_checks),
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

    assert resp_messages == [{"message": "first reply"}]
    assert sent == ["first reply"]
    assert context["MultiModalResponses"] == [
        {"type": "text", "content": "first reply", "metadata": {}}
    ]
    assert is_rollback is True
    assert is_content_blocked is False


@pytest.mark.asyncio
async def test_empty_output_fallback_skipped_when_new_message_arrives(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)

    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition
    from agent.runner import agent_handler

    sample_context["platform"] = "business"

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
        )

    fallback_calls = []
    new_message_checks = iter([False, True])

    def fake_send_chat_response_fallback(**kwargs):
        fallback_calls.append(kwargs)
        return {"message": "fallback reply"}, kwargs["expect_output_timestamp"]

    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event
    )
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *args: True)
    monkeypatch.setattr(agent_handler, "_team_should_skip_post_analyze", lambda: True)
    monkeypatch.setattr(
        agent_handler, "_send_chat_response_fallback", fake_send_chat_response_fallback
    )
    monkeypatch.setattr(
        agent_handler,
        "is_new_message_coming_in",
        lambda u_id, c_id, platform, current_message_ids: next(new_message_checks),
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
    assert fallback_calls == []
    assert context["MultiModalResponses"] == []
    assert is_rollback is True
    assert is_content_blocked is False
