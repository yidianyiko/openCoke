# tests/unit/test_context_timezone.py
import pytest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo


def make_minimal_user(timezone=None, timezone_source=None, timezone_status=None):
    user = {
        "_id": "507f1f77bcf86cd799439011",
        "display_name": "Test User",
    }
    if timezone is not None:
        user["timezone"] = timezone
    if timezone_source is not None:
        user["timezone_source"] = timezone_source
    if timezone_status is not None:
        user["timezone_status"] = timezone_status
    return user


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_uses_stored_timezone(mock_mongo, mock_dao):
    """Legacy flat timezone remains usable and is surfaced with canonical defaults."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone="America/New_York")
    mock_mongo.return_value.find_one.return_value = {
        "relationship": {},
        "uid": "x",
        "cid": "y",
    }
    dao_instance = MagicMock()
    mock_dao.return_value = dao_instance

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            ctx = context_prepare(
                user=user,
                character={
                    "_id": "c1",
                    "name": "Coke",
                    "platforms": {},
                    "user_info": {},
                },
                conversation={
                    "_id": "conv1",
                    "platform": "wechat",
                    "conversation_info": {"chat_history": [], "input_messages": []},
                },
            )

    time_str = ctx["conversation"]["conversation_info"]["time_str"]
    assert time_str  # non-empty
    assert ctx["user"]["timezone"] == "America/New_York"
    assert ctx["user"]["effective_timezone"] == "America/New_York"
    assert ctx["user"]["timezone_source"] == "legacy_preserved"
    assert ctx["user"]["timezone_status"] == "user_confirmed"
    assert "future" not in ctx["conversation"]["conversation_info"]
    dao_instance.update_timezone.assert_not_called()


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_formats_input_messages_in_user_timezone(mock_mongo, mock_dao):
    """Relative-time prompts should not mix default timezone message stamps with user timezone current time."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone="Asia/Tokyo")
    mock_mongo.return_value.find_one.return_value = {
        "relationship": {},
        "uid": "x",
        "cid": "y",
    }
    mock_dao.return_value = MagicMock()

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            ctx = context_prepare(
                user=user,
                character={
                    "_id": "c1",
                    "name": "Coke",
                    "platforms": {},
                    "user_info": {},
                },
                conversation={
                    "_id": "conv1",
                    "platform": "business",
                    "chatroom_name": None,
                    "conversation_info": {
                        "chat_history": [],
                        "input_messages": [
                            {
                                "platform": "business",
                                "from_user": "user-1",
                                "to_user": "c1",
                                "input_timestamp": 1777396434,
                                "message_type": "text",
                                "message": "请在一分钟后提醒我：烟测。",
                                "metadata": {
                                    "source": "clawscale",
                                    "coke_account": {
                                        "id": "user-1",
                                        "display_name": "tester",
                                    },
                                },
                            }
                        ],
                    },
                },
            )

    input_messages_str = ctx["conversation"]["conversation_info"]["input_messages_str"]
    time_str = ctx["conversation"]["conversation_info"]["time_str"]
    assert "2026年04月29日02时13分" in input_messages_str
    assert "2026年04月29日01时13分" not in input_messages_str
    assert "2026年04月29日02时13分" in time_str


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_surfaces_canonical_timezone_state(mock_mongo, mock_dao):
    """Canonical timezone state is copied into session_state user context."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(
        timezone="Europe/London",
        timezone_source="messaging_identity_region",
        timezone_status="system_inferred",
    )
    mock_mongo.return_value.find_one.return_value = {
        "relationship": {},
        "uid": "x",
        "cid": "y",
    }
    dao_instance = MagicMock()
    mock_dao.return_value = dao_instance

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            ctx = context_prepare(
                user=user,
                character={
                    "_id": "c1",
                    "name": "Coke",
                    "platforms": {},
                    "user_info": {},
                },
                conversation={
                    "_id": "conv1",
                    "platform": "wechat",
                    "conversation_info": {"chat_history": [], "input_messages": []},
                },
            )

    assert ctx["user"]["timezone"] == "Europe/London"
    assert ctx["user"]["effective_timezone"] == "Europe/London"
    assert ctx["user"]["timezone_source"] == "messaging_identity_region"
    assert ctx["user"]["timezone_status"] == "system_inferred"
    dao_instance.update_timezone.assert_not_called()


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_falls_back_to_default_timezone_state(mock_mongo, mock_dao):
    """User without canonical timezone state gets an in-memory deployment-default context."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone=None)
    mock_mongo.return_value.find_one.return_value = {
        "relationship": {},
        "uid": "x",
        "cid": "y",
    }
    dao_instance = MagicMock()
    mock_dao.return_value = dao_instance

    with patch(
        "agent.runner.context.get_default_timezone", return_value=ZoneInfo("Asia/Tokyo")
    ):
        with patch("agent.runner.context.get_character_prompt", return_value=None):
            with patch("agent.runner.context.ConversationDAO"):
                ctx = context_prepare(
                    user=user,
                    character={
                        "_id": "c1",
                        "name": "Coke",
                        "platforms": {},
                        "user_info": {},
                    },
                    conversation={
                        "_id": "conv1",
                        "platform": "wechat",
                        "conversation_info": {"chat_history": [], "input_messages": []},
                    },
                )

    assert "timezone" not in ctx["user"]
    assert ctx["user"]["effective_timezone"] == "Asia/Tokyo"
    assert ctx["user"]["timezone_source"] == "deployment_default"
    assert ctx["user"]["timezone_status"] == "system_inferred"
    dao_instance.update_timezone.assert_not_called()


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_drops_invalid_stored_timezone_on_fallback(
    mock_mongo, mock_dao
):
    """Invalid stored timezone must not survive beside runtime fallback fields."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone="Not/AZone")
    mock_mongo.return_value.find_one.return_value = {
        "relationship": {},
        "uid": "x",
        "cid": "y",
    }
    dao_instance = MagicMock()
    mock_dao.return_value = dao_instance

    with patch(
        "agent.runner.context.get_default_timezone", return_value=ZoneInfo("Asia/Tokyo")
    ):
        with patch("agent.runner.context.get_character_prompt", return_value=None):
            with patch("agent.runner.context.ConversationDAO"):
                ctx = context_prepare(
                    user=user,
                    character={
                        "_id": "c1",
                        "name": "Coke",
                        "platforms": {},
                        "user_info": {},
                    },
                    conversation={
                        "_id": "conv1",
                        "platform": "wechat",
                        "conversation_info": {"chat_history": [], "input_messages": []},
                    },
                )

    assert "timezone" not in ctx["user"]
    assert ctx["user"]["effective_timezone"] == "Asia/Tokyo"
    assert ctx["user"]["timezone_source"] == "deployment_default"
    assert ctx["user"]["timezone_status"] == "system_inferred"
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
