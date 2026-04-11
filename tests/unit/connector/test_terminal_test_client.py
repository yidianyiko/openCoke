from unittest.mock import MagicMock, call


def test_reset_test_state_clears_pending_messages_and_private_conversation(
    monkeypatch,
):
    import connector.terminal.terminal_test_client as terminal_test_client

    fake_mongo = MagicMock()
    fake_conversation_dao = MagicMock()
    fake_conversation_dao.get_private_conversation.return_value = {"_id": "conv_1"}

    monkeypatch.setattr(terminal_test_client, "MongoDBBase", lambda: fake_mongo)
    monkeypatch.setattr(
        terminal_test_client,
        "ConversationDAO",
        lambda: fake_conversation_dao,
        raising=False,
    )

    client = terminal_test_client.TerminalTestClient(
        user_id="user_1",
        character_id="char_1",
    )

    client.reset_test_state()

    assert fake_mongo.update_many.call_args_list == [
        call(
            "inputmessages",
            {
                "from_user": "user_1",
                "to_user": "char_1",
                "status": "pending",
            },
            {"$set": {"status": "canceled"}},
        ),
        call(
            "outputmessages",
            {
                "from_user": "char_1",
                "to_user": "user_1",
                "status": "pending",
            },
            {"$set": {"status": "canceled"}},
        ),
    ]
    fake_conversation_dao.get_private_conversation.assert_called_once_with(
        "wechat", "user_1", "char_1"
    )
    fake_conversation_dao.delete_conversation.assert_called_once_with("conv_1")
