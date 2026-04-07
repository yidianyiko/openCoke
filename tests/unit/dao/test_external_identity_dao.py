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
    dao.collection.create_index.assert_any_call([("clawscale_user_id", 1)])


def test_iter_active_clawscale_identities_returns_active_records_only():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find.return_value = [{"external_end_user_id": "wxid_123"}]

    result = list(dao.iter_active_clawscale_identities())

    dao.collection.find.assert_called_once_with(
        {"source": "clawscale", "status": "active"}
    )
    assert result == [{"external_end_user_id": "wxid_123"}]


def test_find_active_identity_for_account_in_tenant_filters_by_tenant():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = {
        "account_id": "acct_1",
        "tenant_id": "ten_1",
        "external_end_user_id": "wxid_tenant",
        "status": "active",
    }

    result = dao.find_active_identity_for_account_in_tenant(
        account_id="acct_1",
        tenant_id="ten_1",
    )

    dao.collection.find_one.assert_called_once_with(
        {
            "account_id": "acct_1",
            "tenant_id": "ten_1",
            "source": "clawscale",
            "status": "active",
        }
    )
    assert result["tenant_id"] == "ten_1"
