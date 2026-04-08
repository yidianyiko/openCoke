from unittest.mock import MagicMock


def test_clawscale_push_route_indexes_support_upsert_and_lookup():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.create_indexes()

    dao.collection.create_index.assert_any_call(
        [
            ("source", 1),
            ("account_id", 1),
            ("platform", 1),
            ("conversation_id", 1),
        ],
        unique=True,
    )
    dao.collection.create_index.assert_any_call(
        [
            ("source", 1),
            ("account_id", 1),
            ("platform", 1),
            ("conversation_id", 1),
            ("status", 1),
            ("last_seen_at", 1),
        ]
    )


def test_upsert_route_stores_or_updates_a_conversation_route():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.upsert_route(
        account_id="acct_1",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        conversation_id="conv_1",
        clawscale_user_id="csu_1",
        now_ts=1775622666,
    )

    dao.collection.update_one.assert_called_once_with(
        {
            "source": "clawscale",
            "account_id": "acct_1",
            "platform": "wechat_personal",
            "conversation_id": "conv_1",
        },
        {
            "$set": {
                "tenant_id": "ten_1",
                "channel_id": "ch_1",
                "external_end_user_id": "wxid_123",
                "clawscale_user_id": "csu_1",
                "status": "active",
                "last_seen_at": 1775622666,
                "updated_at": 1775622666,
            },
            "$setOnInsert": {
                "source": "clawscale",
                "account_id": "acct_1",
                "platform": "wechat_personal",
                "conversation_id": "conv_1",
                "created_at": 1775622666,
            },
        },
        upsert=True,
    )


def test_upsert_route_clears_clawscale_user_id_when_none():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.upsert_route(
        account_id="acct_1",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        conversation_id="conv_1",
        clawscale_user_id=None,
        now_ts=1775622667,
    )

    dao.collection.update_one.assert_called_once_with(
        {
            "source": "clawscale",
            "account_id": "acct_1",
            "platform": "wechat_personal",
            "conversation_id": "conv_1",
        },
        {
            "$set": {
                "tenant_id": "ten_1",
                "channel_id": "ch_1",
                "external_end_user_id": "wxid_123",
                "status": "active",
                "last_seen_at": 1775622667,
                "updated_at": 1775622667,
            },
            "$setOnInsert": {
                "source": "clawscale",
                "account_id": "acct_1",
                "platform": "wechat_personal",
                "conversation_id": "conv_1",
                "created_at": 1775622667,
            },
            "$unset": {"clawscale_user_id": ""},
        },
        upsert=True,
    )


def test_find_route_for_conversation_returns_latest_active_match():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = {
        "account_id": "acct_1",
        "conversation_id": "conv_1",
        "status": "active",
        "last_seen_at": 1775622666,
    }

    result = dao.find_route_for_conversation(
        account_id="acct_1",
        conversation_id="conv_1",
        platform="wechat_personal",
    )

    dao.collection.find_one.assert_called_once_with(
        {
            "source": "clawscale",
            "account_id": "acct_1",
            "platform": "wechat_personal",
            "conversation_id": "conv_1",
            "status": "active",
        },
        sort=[("last_seen_at", -1), ("updated_at", -1)],
    )
    assert result["conversation_id"] == "conv_1"


def test_find_route_for_conversation_returns_none_when_missing():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = None

    result = dao.find_route_for_conversation(
        account_id="acct_1",
        conversation_id="conv_missing",
        platform="wechat_personal",
    )

    assert result is None


def test_find_latest_route_for_account_returns_latest_active_route_for_platform():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = {
        "account_id": "acct_1",
        "conversation_id": "conv_recent",
        "status": "active",
        "last_seen_at": 1775623000,
    }

    result = dao.find_latest_route_for_account(
        account_id="acct_1",
        platform="wechat_personal",
    )

    dao.collection.find_one.assert_called_once_with(
        {
            "source": "clawscale",
            "account_id": "acct_1",
            "platform": "wechat_personal",
            "status": "active",
        },
        sort=[("last_seen_at", -1), ("updated_at", -1)],
    )
    assert result["conversation_id"] == "conv_recent"


def test_find_latest_route_for_account_returns_none_when_missing():
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO

    dao = ClawscalePushRouteDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = None

    result = dao.find_latest_route_for_account(
        account_id="acct_1",
        platform="wechat_personal",
    )

    assert result is None
