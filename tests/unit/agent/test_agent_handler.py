# -*- coding: utf-8 -*-
import importlib
import sys
import types

import pytest


def _load_agent_handler(monkeypatch):
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
    lock_stub = types.SimpleNamespace(
        acquire_lock=lambda *a, **k: None,
        renew_lock=lambda *a, **k: None,
        release_lock_safe=lambda *a, **k: (True, ""),
    )
    monkeypatch.setitem(
        sys.modules,
        "dao.lock",
        types.SimpleNamespace(
            MongoDBLockManager=lambda *args, **kwargs: lock_stub
        ),
    )

    from agent.runner import message_processor

    monkeypatch.setattr(
        message_processor, "ConversationDAO", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(message_processor, "UserDAO", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        message_processor,
        "MongoDBLockManager",
        lambda *args, **kwargs: lock_stub,
    )

    from agent.runner import agent_handler

    return importlib.reload(agent_handler)


@pytest.mark.asyncio
async def test_handle_message_marks_stream_provider_error_for_rollback(
    monkeypatch, sample_context
):
    agent_handler = _load_agent_handler(monkeypatch)

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


def test_is_new_message_coming_in_filters_by_group_and_account(monkeypatch):
    from agent.runner import agent_handler

    captured = {}

    def fake_read_all_inputmessages(
        u_id,
        c_id,
        platform,
        status=None,
        chatroom_name=None,
        account_id=None,
    ):
        captured["args"] = (
            u_id,
            c_id,
            platform,
            status,
            chatroom_name,
            account_id,
        )
        return [{"_id": "new-1"}]

    monkeypatch.setattr(
        agent_handler, "read_all_inputmessages", fake_read_all_inputmessages
    )

    has_new_message = agent_handler.is_new_message_coming_in(
        "user-1",
        "character-2",
        "wechat",
        current_message_ids=["current-1"],
        chatroom_name="room-1",
        account_id="bot-b",
    )

    assert has_new_message is True
    assert captured["args"] == (
        "user-1",
        "character-2",
        "wechat",
        "pending",
        "room-1",
        "bot-b",
    )


@pytest.mark.asyncio
async def test_handle_message_passes_group_and_account_to_new_message_check(
    monkeypatch, sample_context
):
    agent_handler = _load_agent_handler(monkeypatch)

    sample_context["conversation"]["chatroom_name"] = "room-1"
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"metadata": {"gateway": {"account_id": "bot-b"}}}
    ]

    async def fake_prepare_run(input_message, session_state):
        return {"session_state": session_state}

    captured = {}

    def fake_is_new_message_coming_in(
        u_id,
        c_id,
        platform,
        current_message_ids=None,
        chatroom_name=None,
        account_id=None,
    ):
        captured["args"] = (
            u_id,
            c_id,
            platform,
            current_message_ids,
            chatroom_name,
            account_id,
        )
        return True

    monkeypatch.setattr(agent_handler.prepare_workflow, "run", fake_prepare_run)
    monkeypatch.setattr(
        agent_handler, "is_new_message_coming_in", fake_is_new_message_coming_in
    )

    resp_messages, _, is_rollback, is_content_blocked = await agent_handler.handle_message(
        context=sample_context,
        input_message_str="你好",
        message_source="user",
        check_new_message=True,
        worker_tag="[T]",
        current_message_ids=["current-1"],
    )

    assert resp_messages == []
    assert is_rollback is True
    assert is_content_blocked is False
    assert captured["args"] == (
        str(sample_context["user"]["_id"]),
        str(sample_context["character"]["_id"]),
        "wechat",
        ["current-1"],
        "room-1",
        "bot-b",
    )


@pytest.mark.asyncio
async def test_create_handler_uses_async_delivery_for_gate_denied(monkeypatch, sample_context):
    agent_handler = _load_agent_handler(monkeypatch)
    from agent.runner import message_processor

    send_calls = []

    class DummyAcquirer:
        def __init__(self, worker_tag):
            self.worker_tag = worker_tag

        def acquire(self):
            return types.SimpleNamespace(
                user=sample_context["user"],
                character=sample_context["character"],
                conversation=sample_context["conversation"],
                input_messages=[],
                lock_id=None,
                conversation_id=None,
                context=None,
            )

        def renew_lock(self, msg_ctx):
            return None

        def release_lock(self, msg_ctx, reason=""):
            return None

    class DummyDispatcher:
        def __init__(self, worker_tag):
            self.worker_tag = worker_tag
            self.access_gate = types.SimpleNamespace(
                get_message=lambda name, checkout_url="": f"{name}:{checkout_url}"
            )

        def dispatch(self, msg_ctx):
            return "gate_denied", {"checkout_url": "https://checkout.example.com"}

    class DummyFinalizer:
        def __init__(self, worker_tag, max_conversation_round):
            self.worker_tag = worker_tag

        def finalize_success(self, *args, **kwargs):
            return None

        def finalize_hardfinish(self, *args, **kwargs):
            return None

        def finalize_blocked(self, *args, **kwargs):
            return None

        def finalize_hold(self, *args, **kwargs):
            return None

        def finalize_rollback(self, *args, **kwargs):
            return False

        def finalize_error(self, *args, **kwargs):
            return None

    async def fake_send_message_via_delivery(*args, **kwargs):
        send_calls.append({"args": args, "kwargs": kwargs})
        return {"_id": "out-1"}

    monkeypatch.setattr(message_processor, "MessageAcquirer", DummyAcquirer)
    monkeypatch.setattr(message_processor, "MessageDispatcher", DummyDispatcher)
    monkeypatch.setattr(message_processor, "MessageFinalizer", DummyFinalizer)
    monkeypatch.setattr(agent_handler, "send_message_via_delivery", fake_send_message_via_delivery)
    monkeypatch.setattr(agent_handler, "_get_delivery_service", lambda: object())
    monkeypatch.setattr(
        agent_handler,
        "context_prepare",
        lambda user, character, conversation: {
            "user": user,
            "character": character,
            "conversation": conversation,
        },
    )

    handler = agent_handler.create_handler(0)
    await handler()

    assert len(send_calls) == 1
    assert send_calls[0]["kwargs"]["message"].startswith("gate_denied:")
    assert send_calls[0]["kwargs"]["message_type"] == "text"
