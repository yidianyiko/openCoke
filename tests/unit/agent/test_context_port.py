from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from agent.agno_agent.capabilities.context_port import ContextPort
from agent.agno_agent.runtime.context import build_agent_run_context


def _legacy_context():
    return {
        "user": {
            "id": "user-stable-id",
            "_id": "user-mongo-id",
            "display_name": "Display User",
            "nickname": "User",
            "timezone": "Asia/Tokyo",
        },
        "character": {
            "id": "char-stable-id",
            "_id": "char-mongo-id",
            "nickname": "Coke",
        },
        "conversation": {
            "id": "conv-stable-id",
            "_id": "conv-mongo-id",
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
        "relation": {"uid": "user-stable-id", "cid": "char-stable-id"},
        "conversation_id": "conv-legacy-id",
        "platform": "business",
        "recent_chat_history": "User: hello",
    }


def test_build_agent_run_context_preserves_trusted_ids_timezone_and_history():
    context = build_agent_run_context(
        _legacy_context(),
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )

    assert context.user.id == "user-stable-id"
    assert context.user.nickname == "Display User"
    assert context.user.timezone == "Asia/Tokyo"
    assert context.character.id == "char-stable-id"
    assert context.character.nickname == "Coke"
    assert context.conversation.id == "conv-stable-id"
    assert context.conversation.platform == "business"
    assert context.conversation.route_key == "route-1"
    assert context.relation.uid == "user-stable-id"
    assert context.relation.cid == "char-stable-id"
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
            "id": "user-stable-id",
            "nickname": "Display User",
            "timezone": "Asia/Tokyo",
        },
        "character": {"id": "char-stable-id", "nickname": "Coke"},
        "conversation": {
            "id": "conv-stable-id",
            "platform": "business",
            "route_key": "route-1",
        },
        "relation": {"uid": "user-stable-id", "cid": "char-stable-id"},
        "current_time": "2026-05-01T01:00:00+00:00",
        "recent_chat_history": "User: hello",
        "runtime_metadata": {"worker_tag": "[T]"},
    }


def test_builder_uses_conversation_mongo_id_when_stable_id_is_absent():
    legacy_context = _legacy_context()
    legacy_context["conversation"].pop("id")

    context = build_agent_run_context(
        legacy_context,
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )

    assert context.conversation.id == "conv-mongo-id"


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


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda context: context["user"].clear(), "missing user id"),
        (lambda context: context["character"].clear(), "missing character id"),
        (
            lambda context: (
                context["conversation"].pop("id"),
                context["conversation"].pop("_id"),
                context.pop("conversation_id", None),
            ),
            "missing conversation id",
        ),
    ],
)
def test_builder_rejects_missing_required_ids(mutation, message):
    legacy_context = _legacy_context()
    mutation(legacy_context)

    with pytest.raises(ValueError, match=message):
        build_agent_run_context(
            legacy_context,
            current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "relation",
    [
        {"uid": "wrong-user", "cid": "char-stable-id"},
        {"uid": "user-stable-id", "cid": "wrong-character"},
    ],
)
def test_builder_rejects_relation_ids_that_conflict_with_trusted_ids(relation):
    legacy_context = _legacy_context()
    legacy_context["relation"] = relation

    with pytest.raises(ValueError, match="relation .* conflicts"):
        build_agent_run_context(
            legacy_context,
            current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        )
