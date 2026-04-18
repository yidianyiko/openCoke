from unittest.mock import MagicMock, patch


def test_get_user_by_id_falls_back_to_characters_collection():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()
        dao.collection.find_one.return_value = None
        dao.characters_collection = MagicMock()
        dao.characters_collection.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439012",
            "name": "qiaoyun",
            "nickname": "Qiaoyun",
        }

        user = dao.get_user_by_id("507f1f77bcf86cd799439012")

        assert user["nickname"] == "Qiaoyun"
        dao.collection.find_one.assert_called_once()
        dao.characters_collection.find_one.assert_called_once()
