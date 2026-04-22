# tests/unit/test_context_timezone.py
import pytest
from unittest.mock import MagicMock, patch


def make_minimal_user(timezone=None):
    user = {
        "_id": "507f1f77bcf86cd799439011",
        "display_name": "Test User",
    }
    if timezone is not None:
        user["timezone"] = timezone
    return user


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_uses_stored_timezone(mock_mongo, mock_dao):
    """User with stored timezone uses it, does not call update_timezone."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone="America/New_York")
    mock_mongo.return_value.find_one.return_value = {"relationship": {}, "uid": "x", "cid": "y"}
    dao_instance = MagicMock()
    mock_dao.return_value = dao_instance

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            ctx = context_prepare(
                user=user,
                character={"_id": "c1", "name": "Coke", "platforms": {}, "user_info": {}},
                conversation={
                    "_id": "conv1",
                    "platform": "wechat",
                    "conversation_info": {"chat_history": [], "input_messages": []},
                },
            )

    time_str = ctx["conversation"]["conversation_info"]["time_str"]
    assert time_str  # non-empty
    assert "future" not in ctx["conversation"]["conversation_info"]
    dao_instance.update_timezone.assert_not_called()


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_backfills_timezone_for_legacy_user(mock_mongo, mock_dao):
    """User without timezone falls back to product default without lazy backfill."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone=None)
    mock_mongo.return_value.find_one.return_value = {"relationship": {}, "uid": "x", "cid": "y"}
    dao_instance = MagicMock()
    dao_instance.update_timezone.return_value = True
    mock_dao.return_value = dao_instance

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            context_prepare(
                user=user,
                character={"_id": "c1", "name": "Coke", "platforms": {}, "user_info": {}},
                conversation={
                    "_id": "conv1",
                    "platform": "wechat",
                    "conversation_info": {"chat_history": [], "input_messages": []},
                },
            )

    dao_instance.update_timezone.assert_not_called()


def test_ensure_conversation_info_structure_drops_legacy_future():
    from dao.conversation_dao import ConversationDAO

    conversation = {
        "_id": "conv1",
        "conversation_info": {
            "chat_history": [],
            "input_messages": [],
            "future": {
                "timestamp": None,
                "action": None,
                "proactive_times": 0,
                "status": "pending",
            },
        },
    }

    normalized = ConversationDAO.ensure_conversation_info_structure(conversation)

    assert "future" not in normalized["conversation_info"]


def test_sample_context_fixture_has_no_future(sample_context):
    assert "future" not in sample_context["conversation"]["conversation_info"]


def test_private_conversation_default_payload_has_no_future():
    from dao.conversation_dao import ConversationDAO

    dao = ConversationDAO.__new__(ConversationDAO)
    dao.get_private_conversation = MagicMock(return_value=None)
    dao.create_conversation = MagicMock(return_value="conv-private")

    conversation_id, created = ConversationDAO.get_or_create_private_conversation(
        dao,
        platform="wechat",
        user_id1="user-1",
        nickname1="User 1",
        user_id2="user-2",
        nickname2="User 2",
    )

    assert conversation_id == "conv-private"
    assert created is True
    payload = dao.create_conversation.call_args.args[0]
    assert "future" not in payload["conversation_info"]


def test_group_conversation_default_payload_has_no_future():
    from dao.conversation_dao import ConversationDAO

    dao = ConversationDAO.__new__(ConversationDAO)
    dao.get_group_conversation = MagicMock(return_value=None)
    dao.create_conversation = MagicMock(return_value="conv-group")

    conversation_id, created = ConversationDAO.get_or_create_group_conversation(
        dao,
        platform="wechat",
        chatroom_name="group-1",
        initial_talkers=[{"id": "user-1", "nickname": "User 1"}],
    )

    assert conversation_id == "conv-group"
    assert created is True
    payload = dao.create_conversation.call_args.args[0]
    assert "future" not in payload["conversation_info"]
