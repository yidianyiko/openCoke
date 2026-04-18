from unittest.mock import MagicMock, patch


def test_get_user_by_id_reads_characters_without_touching_retired_users_collection():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.characters_collection = MagicMock()
        dao.characters_collection.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439012",
            "name": "qiaoyun",
            "nickname": "Qiaoyun",
        }

        user = dao.get_user_by_id("507f1f77bcf86cd799439012")

        assert user["nickname"] == "Qiaoyun"
        dao.characters_collection.find_one.assert_called_once()


def test_get_user_by_account_id_merges_profile_and_settings_documents():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.profile_collection = MagicMock()
        dao.settings_collection = MagicMock()
        dao.profile_collection.find_one.return_value = {
            "account_id": "acct_123",
            "display_name": "Alice",
            "platforms": {"business": {"nickname": "Alice"}},
        }
        dao.settings_collection.find_one.return_value = {
            "account_id": "acct_123",
            "timezone": "Asia/Tokyo",
            "access": {"expire_time": "2026-05-01T00:00:00Z"},
        }

        user = dao.get_user_by_account_id("acct_123")

        assert user == {
            "account_id": "acct_123",
            "_id": "acct_123",
            "id": "acct_123",
            "display_name": "Alice",
            "platforms": {"business": {"nickname": "Alice"}},
            "timezone": "Asia/Tokyo",
            "access": {"expire_time": "2026-05-01T00:00:00Z"},
        }
        dao.profile_collection.find_one.assert_called_once_with({"account_id": "acct_123"})
        dao.settings_collection.find_one.assert_called_once_with({"account_id": "acct_123"})
