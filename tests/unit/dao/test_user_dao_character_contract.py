from datetime import datetime
from unittest.mock import MagicMock, patch


def test_upsert_user_preserves_character_phase1_fields():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.characters_collection = MagicMock()
        dao.characters_collection.update_one.return_value = MagicMock(upserted_id="char_1")
        migrated_at = datetime.utcnow()

        user_id = dao.upsert_user(
            {"name": "qiaoyun", "is_character": True},
            {
                "_id": "507f1f77bcf86cd799439012",
                "is_character": True,
                "name": "qiaoyun",
                "nickname": "Qiaoyun",
                "platforms": {"wechat": {"nickname": "Qiaoyun"}},
                "user_info": {"description": "prompt"},
                "legacy_user_id": "507f1f77bcf86cd799439012",
                "migrated_at": migrated_at,
            },
        )

        assert user_id == "char_1"
        call_args = dao.characters_collection.update_one.call_args
        assert call_args[0][0] == {"name": "qiaoyun"}
        stored_fields = call_args[0][1]["$set"]
        assert stored_fields["_id"] == "507f1f77bcf86cd799439012"
        assert stored_fields["name"] == "qiaoyun"
        assert stored_fields["nickname"] == "Qiaoyun"
        assert stored_fields["platforms"] == {"wechat": {"nickname": "Qiaoyun"}}
        assert stored_fields["user_info"] == {"description": "prompt"}
        assert stored_fields["legacy_user_id"] == "507f1f77bcf86cd799439012"
        assert stored_fields["migrated_at"] is migrated_at
