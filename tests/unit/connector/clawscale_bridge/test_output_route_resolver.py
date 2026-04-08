from unittest.mock import MagicMock


def test_output_route_resolver_prefers_conversation_route_over_account_and_legacy():
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver

    route_dao = MagicMock()
    route_dao.find_route_for_conversation.return_value = {
        "tenant_id": "ten_conv",
        "channel_id": "ch_conv",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_conv",
        "conversation_id": "conv_1",
        "source": "clawscale",
    }
    route_dao.find_latest_route_for_account.return_value = {
        "tenant_id": "ten_account",
        "channel_id": "ch_account",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_account",
        "conversation_id": None,
        "source": "clawscale",
    }
    external_dao = MagicMock()
    external_dao.find_primary_push_target.return_value = {
        "tenant_id": "ten_legacy",
        "channel_id": "ch_legacy",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_legacy",
        "source": "clawscale",
    }

    resolver = OutputRouteResolver(
        external_identity_dao=external_dao,
        clawscale_push_route_dao=route_dao,
    )
    metadata = resolver.build_push_metadata(
        "acct_1",
        now_ts=1710000000,
        conversation_id="conv_1",
        platform="wechat_personal",
    )

    assert metadata["tenant_id"] == "ten_conv"
    assert metadata["channel_id"] == "ch_conv"
    route_dao.find_route_for_conversation.assert_called_once_with(
        account_id="acct_1",
        conversation_id="conv_1",
        platform="wechat_personal",
    )
    route_dao.find_latest_route_for_account.assert_not_called()
    external_dao.find_primary_push_target.assert_not_called()


def test_output_route_resolver_falls_back_to_account_level_route():
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver

    route_dao = MagicMock()
    route_dao.find_route_for_conversation.return_value = None
    route_dao.find_latest_route_for_account.return_value = {
        "tenant_id": "ten_account",
        "channel_id": "ch_account",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_account",
        "conversation_id": None,
        "source": "clawscale",
    }
    external_dao = MagicMock()
    external_dao.find_primary_push_target.return_value = None

    resolver = OutputRouteResolver(
        external_identity_dao=external_dao,
        clawscale_push_route_dao=route_dao,
    )
    metadata = resolver.build_push_metadata(
        "acct_1",
        now_ts=1710000000,
        conversation_id="conv_1",
        platform="wechat_personal",
    )

    assert metadata["tenant_id"] == "ten_account"
    assert metadata["channel_id"] == "ch_account"
    route_dao.find_route_for_conversation.assert_called_once_with(
        account_id="acct_1",
        conversation_id="conv_1",
        platform="wechat_personal",
    )
    route_dao.find_latest_route_for_account.assert_called_once_with(
        account_id="acct_1",
        platform="wechat_personal",
    )
    external_dao.find_primary_push_target.assert_not_called()


def test_output_route_resolver_keeps_legacy_external_identity_fallback():
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver

    route_dao = MagicMock()
    route_dao.find_route_for_conversation.return_value = None
    route_dao.find_latest_route_for_account.return_value = None
    external_dao = MagicMock()
    external_dao.find_primary_push_target.return_value = {
        "tenant_id": "ten_legacy",
        "channel_id": "ch_legacy",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_legacy",
        "source": "clawscale",
    }

    resolver = OutputRouteResolver(
        external_identity_dao=external_dao,
        clawscale_push_route_dao=route_dao,
    )
    metadata = resolver.build_push_metadata(
        "acct_1",
        now_ts=1710000000,
        conversation_id="conv_1",
        platform="wechat_personal",
    )

    assert metadata["tenant_id"] == "ten_legacy"
    assert metadata["channel_id"] == "ch_legacy"
    external_dao.find_primary_push_target.assert_called_once_with(
        account_id="acct_1",
        source="clawscale",
    )
