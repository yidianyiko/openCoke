from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from agent.agno_agent.capabilities.context_port import ContextPort
from agent.agno_agent.runtime.context import build_agent_run_context


def _legacy_context():
    return {
        "user": {
            "_id": "user-1",
            "id": "legacy-user-id",
            "display_name": "Display User",
            "nickname": "User",
            "timezone": "Asia/Tokyo",
        },
        "character": {
            "_id": "char-1",
            "id": "legacy-char-id",
            "nickname": "Coke",
        },
        "conversation": {
            "_id": "conv-1",
            "platform": "business",
            "route_key": "route-1",
            "conversation_info": {
                "chat_history": [
                    {
                        "from_nickname": "User",
                        "message": "hello",
                        "message_type": "text",
                    }
                ],
                "chat_history_str": "User: hello",
            },
        },
        "relation": {"uid": "user-1", "cid": "char-1"},
        "platform": "business",
        "recent_chat_history": "User: hello",
    }


def test_build_agent_run_context_preserves_trusted_ids_timezone_and_history():
    context = build_agent_run_context(
        _legacy_context(),
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )

    assert context.user.id == "user-1"
    assert context.user.nickname == "Display User"
    assert context.user.timezone == "Asia/Tokyo"
    assert context.character.id == "char-1"
    assert context.character.nickname == "Coke"
    assert context.conversation.id == "conv-1"
    assert context.conversation.platform == "business"
    assert context.conversation.route_key == "route-1"
    assert context.relation.uid == "user-1"
    assert context.relation.cid == "char-1"
    assert context.recent_chat_history == "User: hello"
    assert context.current_time == datetime(2026, 5, 1, 1, 0, tzinfo=UTC)
    assert context.runtime_metadata["worker_tag"] == "[T]"


def test_context_port_returns_deterministic_base_context():
    run_context = build_agent_run_context(
        _legacy_context(),
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )

    assert ContextPort().build_base_context(run_context) == {
        "user": {
            "id": "user-1",
            "nickname": "Display User",
            "timezone": "Asia/Tokyo",
        },
        "character": {"id": "char-1", "nickname": "Coke"},
        "conversation": {
            "id": "conv-1",
            "platform": "business",
            "route_key": "route-1",
        },
        "relation": {"uid": "user-1", "cid": "char-1"},
        "current_time": "2026-05-01T01:00:00+00:00",
        "recent_chat_history": "User: hello",
        "runtime_metadata": {"worker_tag": "[T]"},
    }


def test_builder_uses_fallbacks_and_preserves_immutable_raw_metadata():
    legacy_context = {
        "user": {"id": "user-2", "name": "Fallback User"},
        "character": {"id": "char-2"},
        "conversation_id": "conv-2",
        "conversation": {
            "conversation_info": {"chat_history_str": "Fallback User: hi"}
        },
    }

    context = build_agent_run_context(
        legacy_context,
        current_time=datetime(2026, 5, 1, 2, 0, tzinfo=UTC),
    )

    assert context.user.id == "user-2"
    assert context.user.nickname == "Fallback User"
    assert context.user.timezone == "UTC"
    assert context.character.id == "char-2"
    assert context.character.nickname == "Coke"
    assert context.conversation.id == "conv-2"
    assert context.conversation.platform == "business"
    assert context.conversation.route_key is None
    assert context.relation.uid == "user-2"
    assert context.relation.cid == "char-2"
    assert context.recent_chat_history == "Fallback User: hi"
    assert isinstance(context.user.metadata, MappingProxyType)
    assert context.user.metadata["raw"]["name"] == "Fallback User"

    legacy_context["user"]["name"] = "Mutated"

    assert context.user.metadata["raw"]["name"] == "Fallback User"
    with pytest.raises(TypeError):
        context.user.metadata["raw"]["name"] = "Mutated"
