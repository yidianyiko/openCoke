from unittest.mock import MagicMock, patch


def test_user_dao_can_lookup_phone_number():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()
        dao.collection.find_one.return_value = {
            "_id": "user_1",
            "phone_number": "13800138000",
        }

        user = dao.get_user_by_phone_number("13800138000")

        assert user["phone_number"] == "13800138000"
        dao.collection.find_one.assert_called_once_with(
            {"phone_number": "13800138000"}
        )
