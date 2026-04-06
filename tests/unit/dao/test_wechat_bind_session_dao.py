from unittest.mock import MagicMock


def test_bind_session_indexes_include_unique_session_and_bind_token():
    from dao.wechat_bind_session_dao import WechatBindSessionDAO

    dao = WechatBindSessionDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.create_indexes()

    dao.collection.create_index.assert_any_call([("session_id", 1)], unique=True)
    dao.collection.create_index.assert_any_call([("bind_token", 1)], unique=True)


def test_find_latest_session_for_account_keeps_expired_rows_visible_for_status_checks():
    from dao.wechat_bind_session_dao import WechatBindSessionDAO

    dao = WechatBindSessionDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.find_latest_session_for_account("user_1")

    dao.collection.find_one.assert_called_once_with(
        {"account_id": "user_1"},
        sort=[("created_at", -1)],
    )
