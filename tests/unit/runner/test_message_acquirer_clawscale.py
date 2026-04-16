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
                "nickname": "Coke",
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
    assert captured["db_user_id1"] == "69d3db920cb4b1810d8e5fca"
    assert captured["nickname1"] == "ydyk"
    assert captured["user_id2"] == "clawscale-character:65f000000000000000000002"
    assert captured["db_user_id2"] == "65f000000000000000000002"
    assert captured["nickname2"] == "Coke"
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
    assert captured["db_user_id1"] == "69d3db920cb4b1810d8e5fca"
    assert captured["nickname1"] == "ydyk"
    assert captured["user_id2"] == "clawscale-character:65f000000000000000000002"
    assert captured["db_user_id2"] == "65f000000000000000000002"
    assert captured["nickname2"] == "qiaoyun"
    assert top_message.get("status") == "pending"


def test_message_acquirer_mints_and_persists_business_key_for_first_turn(
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
                "platforms": {},
            }
        ),
        find_characters=lambda query: [],
    )
    persisted_updates = []

    fake_conversation_dao = types.SimpleNamespace(
        get_or_create_private_conversation=lambda **kwargs: ("conv_virtual", True),
        get_conversation_by_id=lambda conversation_id: {
            "_id": conversation_id,
            "conversation_info": {},
        },
        update_conversation=lambda conversation_id, update_data: (
            persisted_updates.append((conversation_id, update_data)) or True
        ),
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

    acquirer = mp.MessageAcquirer("[W1]")
    top_message = {
        "_id": "msg_top",
        "from_user": "69d3db920cb4b1810d8e5fca",
        "to_user": "65f000000000000000000002",
        "platform": "business",
        "status": "pending",
        "message_type": "text",
        "message": "第一条业务消息",
        "metadata": {
            "source": "clawscale",
            "business_protocol": {
                "delivery_mode": "request_response",
                "gateway_conversation_id": "gw_conv_1",
                "causal_inbound_event_id": "in_evt_1",
            },
        },
    }

    ctx = acquirer._try_acquire_message(top_message, set())

    assert ctx is not None
    assert ctx.conversation["business_conversation_key"] == "bc_conv_virtual"
    assert ctx.conversation["conversation_info"]["business_conversation_key"] == "bc_conv_virtual"
    assert persisted_updates == [
        (
            "conv_virtual",
            {
                "business_conversation_key": "bc_conv_virtual",
                "conversation_info.business_conversation_key": "bc_conv_virtual",
            },
        )
    ]


def test_message_acquirer_keeps_follow_up_virtual_identity_stable_when_business_key_appears(
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
                "platforms": {},
            }
        ),
        find_characters=lambda query: [],
    )
    fake_conversation_dao = types.SimpleNamespace(
        get_or_create_private_conversation=lambda **kwargs: ("conv_virtual", True),
        get_conversation_by_id=lambda conversation_id: {
            "_id": conversation_id,
            "conversation_info": {},
        },
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
        "message": "继续聊",
        "metadata": {
            "source": "clawscale",
            "delivery_mode": "request_response",
            "business_protocol": {
                "gateway_conversation_id": "gw_conv_1",
                "business_conversation_key": "bc_conv_1",
                "causal_inbound_event_id": "in_evt_2",
            },
        },
    }

    ctx = acquirer._try_acquire_message(top_message, set())

    assert ctx is not None
    assert captured["user_id1"] == "clawscale:bc_conv_1"
    assert captured["nickname1"] == "ydyk"
    assert captured["user_id2"] == "clawscale-character:65f000000000000000000002"
    assert top_message.get("status") == "pending"


def test_message_acquirer_falls_back_to_business_key_when_gateway_conversation_id_missing(
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
                "platforms": {},
            }
        ),
        find_characters=lambda query: [],
    )
    fake_conversation_dao = types.SimpleNamespace(
        get_or_create_private_conversation=lambda **kwargs: ("conv_virtual", True),
        get_conversation_by_id=lambda conversation_id: {
            "_id": conversation_id,
            "conversation_info": {},
        },
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
        "message": "继续聊",
        "metadata": {
            "source": "clawscale",
            "delivery_mode": "request_response",
            "business_protocol": {
                "business_conversation_key": "bc_conv_1",
                "causal_inbound_event_id": "in_evt_2",
            },
        },
    }

    ctx = acquirer._try_acquire_message(top_message, set())

    assert ctx is not None
    assert captured["user_id1"] == "clawscale:bc_conv_1"
    assert captured["nickname1"] == "ydyk"
    assert captured["user_id2"] == "clawscale-character:65f000000000000000000002"
    assert top_message.get("status") == "pending"
