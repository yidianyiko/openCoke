from unittest.mock import MagicMock, patch


def test_upsert_user_merges_non_character_docs_without_erasing_existing_fields():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.profile_collection = MagicMock()
        dao.settings_collection = MagicMock()

        dao.upsert_user(
            {"account_id": "acct_123"},
            {
                "account_id": "acct_123",
                "name": "Alice",
                "display_name": "Alice",
                "timezone": "Asia/Tokyo",
            },
        )

        profile_call = dao.profile_collection.update_one.call_args
        settings_call = dao.settings_collection.update_one.call_args

        assert profile_call[0][0] == {"account_id": "acct_123"}
        assert profile_call[0][1]["$set"]["name"] == "Alice"
        assert profile_call[0][1]["$setOnInsert"] == {"account_id": "acct_123"}
        assert settings_call[0][0] == {"account_id": "acct_123"}
        assert settings_call[0][1]["$set"]["timezone"] == "Asia/Tokyo"
        assert settings_call[0][1]["$setOnInsert"] == {"account_id": "acct_123"}
        assert dao.profile_collection.replace_one.call_count == 0
        assert dao.settings_collection.replace_one.call_count == 0
