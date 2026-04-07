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


def test_set_clawscale_user_id_updates_matching_identity_record():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.set_clawscale_user_id(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        clawscale_user_id="csu_1",
    )

    dao.collection.update_one.assert_called_once_with(
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
        },
        {"$set": {"clawscale_user_id": "csu_1"}},
    )


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


def test_activate_identity_clears_existing_primary_push_target_for_account_source():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.find_active_identity = MagicMock(
        return_value={
            "account_id": "user_1",
            "source": "clawscale",
            "external_end_user_id": "wxid_new",
            "status": "active",
            "is_primary_push_target": True,
        }
    )

    result = dao.activate_identity(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_new",
        account_id="user_1",
        now_ts=1775472000,
    )

    dao.collection.update_many.assert_called_once()
    first_call = dao.collection.update_many.call_args
    assert first_call.args[0] == {
        "account_id": "user_1",
        "source": "clawscale",
        "is_primary_push_target": True,
    }
    assert first_call.args[1] == {"$set": {"is_primary_push_target": False}}
    dao.collection.update_one.assert_called_once()
    second_call = dao.collection.update_one.call_args
    assert second_call.kwargs["upsert"] is True
    assert result["external_end_user_id"] == "wxid_new"
