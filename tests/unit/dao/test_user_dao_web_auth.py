from unittest.mock import MagicMock, patch


def test_user_dao_creates_business_collection_indexes():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.profile_collection = MagicMock()
        dao.settings_collection = MagicMock()
        dao.characters_collection = MagicMock()

        dao.create_indexes()

        dao.profile_collection.create_index.assert_any_call(
            [("account_id", 1)],
            unique=True,
        )
        dao.settings_collection.create_index.assert_any_call(
            [("account_id", 1)],
            unique=True,
        )
        dao.characters_collection.create_index.assert_any_call([("name", 1)])


def test_user_dao_does_not_create_auth_indexes():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()
        dao.profile_collection = MagicMock()
        dao.settings_collection = MagicMock()
        dao.characters_collection = MagicMock()

        dao.create_indexes()

        forbidden_calls = [
            (([("phone_number", 1)],), {"sparse": True}),
            (([("email", 1)],), {"unique": True, "sparse": True}),
            (([("status", 1)],), {}),
            (([("is_character", 1)],), {}),
        ]
        actual_calls = [
            (call.args, call.kwargs)
            for call in dao.collection.create_index.call_args_list
        ]
        for forbidden_call in forbidden_calls:
            if forbidden_call in actual_calls:
                raise AssertionError(f"unexpected auth index call: {forbidden_call}")
