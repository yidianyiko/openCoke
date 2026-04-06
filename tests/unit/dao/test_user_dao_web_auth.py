from unittest.mock import MagicMock, patch


def test_user_dao_creates_unique_sparse_email_index():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()

        dao.create_indexes()

        dao.collection.create_index.assert_any_call(
            [("email", 1)],
            unique=True,
            sparse=True,
        )


def test_user_dao_can_lookup_email_case_insensitively():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()
        dao.collection.find_one.return_value = {
            "_id": "user_1",
            "email": "alice@example.com",
            "is_character": False,
        }

        user = dao.get_user_by_email("Alice@Example.com")

        assert user["email"] == "alice@example.com"
        dao.collection.find_one.assert_called_once_with(
            {"email": "alice@example.com", "is_character": {"$ne": True}}
        )
