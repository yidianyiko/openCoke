from unittest.mock import MagicMock


def test_backfill_active_identities_updates_missing_clawscale_user_id():
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

    assert summary == {"scanned": 2, "updated": 1, "skipped": 1}
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

    assert summary == {"scanned": 1, "updated": 0, "skipped": 1}
    gateway_identity_client.bind_identity.assert_not_called()
    external_identity_dao.set_clawscale_user_id.assert_not_called()
