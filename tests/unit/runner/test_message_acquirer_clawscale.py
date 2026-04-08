import types


def test_message_acquirer_uses_virtual_wechat_identity_for_clawscale_request_response(
    monkeypatch,
):
    from agent.runner import message_processor as mp

    fake_user_dao = types.SimpleNamespace(
        get_user_by_id=lambda user_id: (
            {
                "_id": "69d3db920cb4b1810d8e5fca",
                "display_name": "ydyk",
                "email": "yidianyiko@foxmail.com",
                "platforms": {},
            }
            if user_id == "69d3db920cb4b1810d8e5fca"
            else {
                "_id": "65f000000000000000000002",
                "name": "coke",
                "platforms": {
                    "wechat": {
                        "id": "wxid_character",
                        "nickname": "Coke",
                    }
                },
            }
        ),
        find_characters=lambda query: [],
    )
    fake_conversation_dao = types.SimpleNamespace(
        get_or_create_private_conversation=lambda **kwargs: ("conv_virtual", True),
        get_conversation_by_id=lambda conversation_id: {"_id": conversation_id},
    )
    fake_lock_manager = types.SimpleNamespace(
        acquire_lock=lambda *args, **kwargs: "lock_1",
    )

    monkeypatch.setattr(mp, "UserDAO", lambda *args, **kwargs: fake_user_dao)
    monkeypatch.setattr(
        mp, "ConversationDAO", lambda *args, **kwargs: fake_conversation_dao
    )
    monkeypatch.setattr(
        mp, "MongoDBLockManager", lambda *args, **kwargs: fake_lock_manager
    )
    monkeypatch.setattr(
        mp,
        "read_all_inputmessages",
        lambda from_user, to_user, platform, status=None: [{"_id": "msg_1"}],
    )

    captured = {}

    def fake_get_or_create_private_conversation(**kwargs):
        captured.update(kwargs)
        return "conv_virtual", True

    fake_conversation_dao.get_or_create_private_conversation = (
        fake_get_or_create_private_conversation
    )

    acquirer = mp.MessageAcquirer("[W1]")
    top_message = {
        "_id": "msg_top",
        "from_user": "69d3db920cb4b1810d8e5fca",
        "to_user": "65f000000000000000000002",
        "platform": "wechat",
        "status": "pending",
        "message_type": "text",
        "message": "早上好",
        "metadata": {
            "source": "clawscale",
            "delivery_mode": "request_response",
            "clawscale": {
                "conversation_id": "conv_CcVG9pPu-QPtsKmaYgTPu",
                "external_id": "o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat",
            },
        },
    }

    ctx = acquirer._try_acquire_message(top_message, set())

    assert ctx is not None
    assert captured["platform"] == "wechat"
    assert captured["user_id1"] == "clawscale:conv_CcVG9pPu-QPtsKmaYgTPu"
    assert captured["nickname1"] == "ydyk"
    assert captured["user_id2"] == "wxid_character"
    assert top_message.get("status") == "pending"


def test_message_acquirer_uses_virtual_character_identity_when_character_has_no_wechat_platform(
    monkeypatch,
):
    from agent.runner import message_processor as mp

    fake_user_dao = types.SimpleNamespace(
        get_user_by_id=lambda user_id: (
            {
                "_id": "69d3db920cb4b1810d8e5fca",
                "display_name": "ydyk",
                "email": "yidianyiko@foxmail.com",
                "platforms": {},
            }
            if user_id == "69d3db920cb4b1810d8e5fca"
            else {
                "_id": "65f000000000000000000002",
                "name": "qiaoyun",
                "platforms": {},
            }
        ),
        find_characters=lambda query: [],
    )
    fake_conversation_dao = types.SimpleNamespace(
        get_or_create_private_conversation=lambda **kwargs: ("conv_virtual", True),
        get_conversation_by_id=lambda conversation_id: {"_id": conversation_id},
    )
    fake_lock_manager = types.SimpleNamespace(
        acquire_lock=lambda *args, **kwargs: "lock_1",
    )

    monkeypatch.setattr(mp, "UserDAO", lambda *args, **kwargs: fake_user_dao)
    monkeypatch.setattr(
        mp, "ConversationDAO", lambda *args, **kwargs: fake_conversation_dao
    )
    monkeypatch.setattr(
        mp, "MongoDBLockManager", lambda *args, **kwargs: fake_lock_manager
    )
    monkeypatch.setattr(
        mp,
        "read_all_inputmessages",
        lambda from_user, to_user, platform, status=None: [{"_id": "msg_1"}],
    )

    captured = {}

    def fake_get_or_create_private_conversation(**kwargs):
        captured.update(kwargs)
        return "conv_virtual", True

    fake_conversation_dao.get_or_create_private_conversation = (
        fake_get_or_create_private_conversation
    )

    acquirer = mp.MessageAcquirer("[W1]")
    top_message = {
        "_id": "msg_top",
        "from_user": "69d3db920cb4b1810d8e5fca",
        "to_user": "65f000000000000000000002",
        "platform": "wechat",
        "status": "pending",
        "message_type": "text",
        "message": "早上好",
        "metadata": {
            "source": "clawscale",
            "delivery_mode": "request_response",
            "clawscale": {
                "conversation_id": "conv_CcVG9pPu-QPtsKmaYgTPu",
                "external_id": "o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat",
            },
        },
    }

    ctx = acquirer._try_acquire_message(top_message, set())

    assert ctx is not None
    assert captured["platform"] == "wechat"
    assert captured["user_id1"] == "clawscale:conv_CcVG9pPu-QPtsKmaYgTPu"
    assert captured["nickname1"] == "ydyk"
    assert captured["user_id2"] == "clawscale-character:65f000000000000000000002"
    assert captured["nickname2"] == "qiaoyun"
    assert top_message.get("status") == "pending"
