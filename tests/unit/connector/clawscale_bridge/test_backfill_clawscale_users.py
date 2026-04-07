from unittest.mock import MagicMock, call


def test_require_personal_wechat_reset_confirmation_rejects_missing_gate(
    monkeypatch,
):
    from connector.clawscale_bridge.backfill_clawscale_users import (
        require_personal_wechat_reset_confirmation,
    )

    monkeypatch.delenv("ALLOW_WECHAT_PERSONAL_RESET", raising=False)

    try:
        require_personal_wechat_reset_confirmation()
    except RuntimeError as exc:
        assert str(exc) == "personal_wechat_reset_confirmation_required"
    else:
        raise AssertionError("expected RuntimeError")


def test_require_personal_wechat_reset_confirmation_accepts_explicit_gate(
    monkeypatch,
):
    from connector.clawscale_bridge.backfill_clawscale_users import (
        require_personal_wechat_reset_confirmation,
    )

    monkeypatch.setenv("ALLOW_WECHAT_PERSONAL_RESET", "yes")

    require_personal_wechat_reset_confirmation()


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
    external_identity_dao.collection.update_one.assert_has_calls(
        [
            call(
                {
                    "source": "clawscale",
                    "tenant_id": "ten_1",
                    "channel_id": "ch_1",
                    "platform": "wechat_personal",
                    "external_end_user_id": "wxid_missing",
                },
                {"$set": {"clawscale_user_id": "csu_1"}},
            ),
            call(
                {
                    "source": "clawscale",
                    "tenant_id": "ten_1",
                    "channel_id": "ch_1",
                    "platform": "wechat_personal",
                    "external_end_user_id": "wxid_missing",
                },
                {"$set": {"updated_at": 1775472000}},
            ),
        ]
    )


def test_backfill_active_identities_ignores_non_wechat_personal_identities():
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
            "platform": "telegram",
            "external_end_user_id": "tg_1",
            "account_id": "acct_1",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_missing",
            "account_id": "acct_2",
        },
    ]

    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_identity.return_value = {
        "clawscale_user_id": "csu_1",
        "end_user_id": "eu_1",
        "coke_account_id": "acct_2",
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
        coke_account_id="acct_2",
    )
    external_identity_dao.collection.update_one.assert_has_calls(
        [
            call(
                {
                    "source": "clawscale",
                    "tenant_id": "ten_1",
                    "channel_id": "ch_1",
                    "platform": "wechat_personal",
                    "external_end_user_id": "wxid_missing",
                },
                {"$set": {"clawscale_user_id": "csu_1"}},
            ),
            call(
                {
                    "source": "clawscale",
                    "tenant_id": "ten_1",
                    "channel_id": "ch_1",
                    "platform": "wechat_personal",
                    "external_end_user_id": "wxid_missing",
                },
                {"$set": {"updated_at": 1775472000}},
            ),
        ]
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
    external_identity_dao.collection.update_one.assert_not_called()


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

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 3, "updated": 2, "skipped": 0, "failed": 1}
    assert gateway_identity_client.bind_identity.call_count == 3
    assert external_identity_dao.collection.update_one.call_count == 4


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

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 2, "updated": 1, "skipped": 0, "failed": 1}
    assert gateway_identity_client.bind_identity.call_count == 2
    assert external_identity_dao.collection.update_one.call_count == 2
    external_identity_dao.collection.update_one.assert_any_call(
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_valid",
        },
        {"$set": {"clawscale_user_id": "csu_2"}},
    )


def test_main_exits_non_zero_when_backfill_has_failures(monkeypatch, capsys):
    from connector.clawscale_bridge import backfill_clawscale_users

    monkeypatch.setenv("ALLOW_WECHAT_PERSONAL_RESET", "yes")
    monkeypatch.setattr(
        backfill_clawscale_users,
        "_mongo_uri",
        lambda: "mongodb://example",
    )

    class DummyExternalIdentityDAO:
        def __init__(self, mongo_uri, db_name):
            self.mongo_uri = mongo_uri
            self.db_name = db_name

    class DummyGatewayIdentityClient:
        def __init__(self, api_url, api_key):
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr(
        backfill_clawscale_users,
        "ExternalIdentityDAO",
        DummyExternalIdentityDAO,
    )
    monkeypatch.setattr(
        backfill_clawscale_users,
        "GatewayIdentityClient",
        DummyGatewayIdentityClient,
    )
    monkeypatch.setattr(
        backfill_clawscale_users,
        "backfill_active_identities",
        lambda external_identity_dao, gateway_identity_client, now_ts: {
            "scanned": 2,
            "updated": 1,
            "skipped": 0,
            "failed": 1,
        },
    )
    monkeypatch.setattr(
        backfill_clawscale_users,
        "CONF",
        {
            "mongodb": {
                "mongodb_ip": "127.0.0.1",
                "mongodb_port": "27017",
                "mongodb_name": "coke",
            },
            "clawscale_bridge": {
                "identity_api_url": "https://gateway.example/api",
                "identity_api_key": "secret",
            },
        },
    )

    try:
        backfill_clawscale_users.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")

    output = capsys.readouterr().out.strip()
    assert output == '{"scanned": 2, "updated": 1, "skipped": 0, "failed": 1}'
