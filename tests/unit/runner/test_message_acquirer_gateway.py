from unittest.mock import MagicMock, patch


def test_acquirer_reads_pending_messages_for_routed_character_not_default_alias():
    from agent.runner.message_processor import MessageAcquirer

    routed_message = {
        "_id": "msg-1",
        "from_user": "user-1",
        "to_user": "character-2",
        "platform": "wechat",
        "chatroom_name": "room-1",
        "status": "pending",
        "metadata": {"gateway": {"account_id": "bot-b"}},
    }

    with patch("agent.runner.message_processor.UserDAO") as user_dao_cls, patch(
        "agent.runner.message_processor.ConversationDAO"
    ) as conversation_dao_cls, patch(
        "agent.runner.message_processor.MongoDBLockManager"
    ) as lock_manager_cls, patch(
        "agent.runner.message_processor.read_top_inputmessages"
    ) as read_top, patch(
        "agent.runner.message_processor.read_all_inputmessages"
    ) as read_all, patch(
        "agent.runner.message_processor.get_locked_conversation_ids", return_value=set()
    ):
        read_top.return_value = [routed_message]
        read_all.return_value = [routed_message]

        user_dao = user_dao_cls.return_value
        conversation_dao = conversation_dao_cls.return_value
        lock_manager = lock_manager_cls.return_value

        user_dao.find_characters.return_value = [
            {
                "_id": "character-1",
                "name": "coke",
                "platforms": {
                    "wechat": {"id": "coke-wechat", "nickname": "Coke"}
                },
            }
        ]
        user_dao.get_user_by_id.side_effect = [
            {
                "_id": "user-1",
                "platforms": {
                    "wechat": {"id": "wx-user-1", "nickname": "Alice"}
                },
            },
            {
                "_id": "character-2",
                "platforms": {
                    "wechat": {"id": "luna-wechat", "nickname": "Luna"}
                },
            },
        ]
        conversation_dao.get_or_create_group_conversation.return_value = (
            "conv-1",
            False,
        )
        conversation_dao.get_conversation_by_id.return_value = {
            "conversation_info": {}
        }
        lock_manager.acquire_lock.return_value = "lock-1"

        acquirer = MessageAcquirer("[W0]")
        ctx = acquirer.acquire()

    assert ctx is not None
    assert ctx.character["_id"] == "character-2"
    read_top.assert_called_once_with(
        to_user=None,
        status="pending",
        platform=None,
        limit=16,
        max_handle_age=43200,
    )
    read_all.assert_called_once_with(
        "user-1",
        "character-2",
        "wechat",
        "pending",
        chatroom_name="room-1",
        account_id="bot-b",
    )

