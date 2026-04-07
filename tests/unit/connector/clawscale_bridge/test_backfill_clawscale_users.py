from unittest.mock import MagicMock


def test_backfill_active_identities_updates_missing_clawscale_user_id():
    from connector.clawscale_bridge.backfill_clawscale_users import (
        backfill_active_identities,
    )

    external_identity_dao = MagicMock()
    external_identity_dao.collection = MagicMock()
    external_identity_dao.iter_active_clawscale_identities.return_value = [
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_missing",
            "account_id": "acct_1",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_existing",
            "account_id": "acct_2",
            "clawscale_user_id": "csu_2",
        },
    ]

    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_identity.return_value = {
        "clawscale_user_id": "csu_1",
        "end_user_id": "eu_1",
        "coke_account_id": "acct_1",
    }
    external_identity_dao.set_clawscale_user_id.return_value = {
        "clawscale_user_id": "csu_1"
    }

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 2, "updated": 1, "skipped": 1, "failed": 0}
    gateway_identity_client.bind_identity.assert_called_once_with(
        tenant_id="ten_1",
        channel_id="ch_1",
        external_id="wxid_missing",
        coke_account_id="acct_1",
    )
    external_identity_dao.set_clawscale_user_id.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_missing",
        clawscale_user_id="csu_1",
    )
    external_identity_dao.collection.update_one.assert_called_once_with(
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_missing",
        },
        {"$set": {"updated_at": 1775472000}},
    )


def test_backfill_active_identities_skips_records_that_are_already_bound():
    from connector.clawscale_bridge.backfill_clawscale_users import (
        backfill_active_identities,
    )

    external_identity_dao = MagicMock()
    external_identity_dao.iter_active_clawscale_identities.return_value = [
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_existing",
            "account_id": "acct_2",
            "clawscale_user_id": "csu_2",
        }
    ]
    gateway_identity_client = MagicMock()

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 1, "updated": 0, "skipped": 1, "failed": 0}
    gateway_identity_client.bind_identity.assert_not_called()
    external_identity_dao.set_clawscale_user_id.assert_not_called()


def test_backfill_active_identities_continues_after_gateway_failure():
    from connector.clawscale_bridge.backfill_clawscale_users import (
        backfill_active_identities,
    )
    from connector.clawscale_bridge.gateway_identity_client import (
        GatewayIdentityClientError,
    )

    external_identity_dao = MagicMock()
    external_identity_dao.collection = MagicMock()
    external_identity_dao.iter_active_clawscale_identities.return_value = [
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_first",
            "account_id": "acct_1",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_failed",
            "account_id": "acct_2",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_last",
            "account_id": "acct_3",
        },
    ]

    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_identity.side_effect = [
        {"clawscale_user_id": "csu_1"},
        GatewayIdentityClientError("gateway_identity_request_failed"),
        {"clawscale_user_id": "csu_3"},
    ]
    external_identity_dao.set_clawscale_user_id.return_value = {
        "clawscale_user_id": "csu_1"
    }

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 3, "updated": 2, "skipped": 0, "failed": 1}
    assert gateway_identity_client.bind_identity.call_count == 3
    assert external_identity_dao.set_clawscale_user_id.call_count == 2


def test_backfill_active_identities_skips_malformed_rows():
    from connector.clawscale_bridge.backfill_clawscale_users import (
        backfill_active_identities,
    )

    external_identity_dao = MagicMock()
    external_identity_dao.collection = MagicMock()
    external_identity_dao.iter_active_clawscale_identities.return_value = [
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "account_id": "acct_1",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_valid",
            "account_id": "acct_2",
        },
    ]

    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_identity.return_value = {
        "clawscale_user_id": "csu_2"
    }
    external_identity_dao.set_clawscale_user_id.return_value = {
        "clawscale_user_id": "csu_2"
    }

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 2, "updated": 1, "skipped": 1, "failed": 0}
    gateway_identity_client.bind_identity.assert_called_once_with(
        tenant_id="ten_1",
        channel_id="ch_1",
        external_id="wxid_valid",
        coke_account_id="acct_2",
    )


def test_backfill_active_identities_continues_after_invalid_bind_response():
    from connector.clawscale_bridge.backfill_clawscale_users import (
        backfill_active_identities,
    )

    external_identity_dao = MagicMock()
    external_identity_dao.collection = MagicMock()
    external_identity_dao.iter_active_clawscale_identities.return_value = [
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_invalid",
            "account_id": "acct_1",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_valid",
            "account_id": "acct_2",
        },
    ]

    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_identity.side_effect = [
        {},
        {"clawscale_user_id": "csu_2"},
    ]
    external_identity_dao.set_clawscale_user_id.return_value = {
        "clawscale_user_id": "csu_2"
    }

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 2, "updated": 1, "skipped": 0, "failed": 1}
    assert gateway_identity_client.bind_identity.call_count == 2
    external_identity_dao.set_clawscale_user_id.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_valid",
        clawscale_user_id="csu_2",
    )
