import types


def test_message_acquirer_accepts_coke_account_sender_for_business_clawscale_message(
    monkeypatch,
):
    from agent.runner import message_processor as mp

    character_id = "65f000000000000000000002"
    captured = {}

    class FakeUserDAO:
        def find_characters(self, query):
            return []

        def get_user_by_id(self, user_id):
            if user_id == character_id:
                return {
                    "_id": character_id,
                    "name": "coke",
                    "nickname": "Coke",
                    "platforms": {},
                }
            raise ValueError(f"invalid ObjectId: {user_id}")

    def fake_get_or_create_private_conversation(**kwargs):
        captured["conversation_args"] = kwargs
        return "conv_business", True

    fake_conversation_dao = types.SimpleNamespace(
        get_or_create_private_conversation=fake_get_or_create_private_conversation,
        get_conversation_by_id=lambda conversation_id: {
            "_id": conversation_id,
            "platform": "business",
            "conversation_info": {},
        },
        update_conversation=lambda conversation_id, update_data: True,
    )
    fake_lock_manager = types.SimpleNamespace(
        acquire_lock=lambda *args, **kwargs: "lock_1",
    )

    def fake_read_all_inputmessages(from_user, to_user, platform, status=None):
        captured["read_all"] = (from_user, to_user, platform, status)
        return [{"_id": "msg_1", "from_user": from_user, "to_user": to_user}]

    monkeypatch.setattr(mp, "UserDAO", lambda *args, **kwargs: FakeUserDAO())
    monkeypatch.setattr(
        mp, "ConversationDAO", lambda *args, **kwargs: fake_conversation_dao
    )
    monkeypatch.setattr(
        mp, "MongoDBLockManager", lambda *args, **kwargs: fake_lock_manager
    )
    monkeypatch.setattr(mp, "read_all_inputmessages", fake_read_all_inputmessages)

    acquirer = mp.MessageAcquirer("[W1]")
    top_message = {
        "_id": "msg_top",
        "from_user": "acct_123",
        "to_user": character_id,
        "platform": "business",
        "status": "pending",
        "message_type": "text",
        "message": "hello",
        "metadata": {
            "source": "clawscale",
            "business_protocol": {
                "delivery_mode": "request_response",
                "gateway_conversation_id": "gw_conv_1",
                "causal_inbound_event_id": "in_evt_1",
            },
            "coke_account": {
                "id": "acct_123",
                "display_name": "Gateway Alice",
            },
        },
    }

    msg_ctx = acquirer._try_acquire_message(top_message, set())

    assert msg_ctx is not None
    assert msg_ctx.user == {
        "id": "acct_123",
        "_id": "acct_123",
        "nickname": "Gateway Alice",
        "is_coke_account": True,
    }
    assert captured["read_all"] == ("acct_123", character_id, "business", "pending")
    assert captured["conversation_args"]["db_user_id1"] == "acct_123"


def test_message_acquirer_marks_invalid_user_ids_distinct_from_missing_character(
    monkeypatch,
):
    from agent.runner import message_processor as mp

    saved_messages = []

    class FakeUserDAO:
        def find_characters(self, query):
            return []

        def get_user_by_id(self, user_id):
            return {
                "_id": user_id,
                "name": "coke",
                "nickname": "Coke",
                "platforms": {},
            }

    monkeypatch.setattr(mp, "UserDAO", lambda *args, **kwargs: FakeUserDAO())
    monkeypatch.setattr(mp, "ConversationDAO", lambda *args, **kwargs: None)
    monkeypatch.setattr(mp, "MongoDBLockManager", lambda *args, **kwargs: None)
    monkeypatch.setattr(mp, "resolve_agent_user_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(mp, "save_inputmessage", lambda message: saved_messages.append(dict(message)))

    acquirer = mp.MessageAcquirer("[W1]")
    top_message = {
        "_id": "msg_top",
        "from_user": "invalid-user",
        "to_user": "65f000000000000000000002",
        "platform": "business",
        "status": "pending",
        "message_type": "text",
        "message": "hello",
        "metadata": {},
    }

    msg_ctx = acquirer._try_acquire_message(top_message, set())

    assert msg_ctx is None
    assert saved_messages[-1]["status"] == "failed"
    assert saved_messages[-1]["error"] == "invalid_user_id"
