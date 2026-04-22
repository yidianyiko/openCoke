from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
def test_resolve_latest_private_conversation_by_db_user_ids_prefers_recent_conversation():
    from dao.conversation_dao import ConversationDAO

    dao = ConversationDAO.__new__(ConversationDAO)
    dao.collection = MagicMock()
    dao.collection.find.return_value.sort.return_value.limit.return_value = [
        {
            "_id": "conv-2",
            "platform": "wechat",
            "chatroom_name": None,
            "talkers": [],
        }
    ]

    conversation = ConversationDAO.find_latest_private_conversation_by_db_user_ids(
        dao,
        db_user_id1="ck_1",
        db_user_id2="char_1",
    )

    assert str(conversation["_id"]) == "conv-2"
    dao.collection.find.assert_called_once_with(
        {
            "chatroom_name": None,
            "talkers.db_user_id": {"$all": ["ck_1", "char_1"]},
            "$where": "this.talkers.length === 2",
        }
    )

