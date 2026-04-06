from unittest.mock import MagicMock


def test_external_identity_indexes_include_unique_gateway_identity():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.create_indexes()

    dao.collection.create_index.assert_any_call(
        [
            ("source", 1),
            ("tenant_id", 1),
            ("channel_id", 1),
            ("platform", 1),
            ("external_end_user_id", 1),
        ],
        unique=True,
    )
