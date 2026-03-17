# -*- coding: utf-8 -*-
import sys
import types

import pytest


@pytest.mark.asyncio
async def test_handle_message_marks_stream_provider_error_for_rollback(
    monkeypatch, sample_context
):
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.agent_hardcode_handler",
        types.SimpleNamespace(handle_hardcode=lambda *args, **kwargs: None, supported_hardcode=()),
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
        types.SimpleNamespace(UserDAO=lambda *args, **kwargs: object()),
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

    resp_messages, _, is_rollback, is_content_blocked = await agent_handler.handle_message(
        context=sample_context,
        input_message_str="你好",
        message_source="user",
        check_new_message=False,
        worker_tag="[T]",
        current_message_ids=[],
    )

    assert resp_messages == []
    assert is_rollback is True
    assert is_content_blocked is False
