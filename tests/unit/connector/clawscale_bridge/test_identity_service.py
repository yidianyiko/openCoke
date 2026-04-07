from unittest.mock import ANY, MagicMock


def test_handle_inbound_returns_bind_required_when_frozen_personal_session_has_no_legacy_identity():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "绑定成功后的第一条回复"
    bind_session_service = MagicMock()
    bind_session_service.consume_matching_session.return_value = None
    bind_session_service.consume_matching_session_from_text.return_value = None

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )
    service.issue_or_reuse_binding_ticket = MagicMock(
        return_value={"bind_url": "https://coke.local/bind/bt_1"}
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "contextToken": "ctx_bind_123",
            },
        }
    )

    assert result == {
        "status": "bind_required",
        "reply": "请先绑定账号: https://coke.local/bind/bt_1",
        "bind_url": "https://coke.local/bind/bt_1",
    }
    bind_session_service.consume_matching_session.assert_called_once()
    external_identity_dao.find_active_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
    )


def test_handle_inbound_uses_personal_channel_ownership_metadata_without_legacy_lookup():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "personal ownership reply"
    bind_session_service = MagicMock()

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acct_1",
            },
        }
    )

    assert result == {"status": "ok", "reply": "personal ownership reply"}
    external_identity_dao.find_active_identity.assert_not_called()
    external_identity_dao.find_active_identity_for_account.assert_not_called()
    bind_session_service.consume_matching_session.assert_not_called()
    bind_session_service.consume_matching_session_from_text.assert_not_called()
    message_gateway.enqueue.assert_called_once_with(
        account_id="acct_1",
        character_id="char_1",
        text="你好",
        inbound={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "conversation_id": "conv_1",
            "platform": "wechat_personal",
            "end_user_id": "eu_1",
            "external_id": "wxid_123",
            "external_message_id": "conv_1",
            "timestamp": ANY,
        },
    )


def test_handle_inbound_uses_gateway_coke_account_id_when_local_trust_check_passes():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account_in_tenant.return_value = {
        "account_id": "acct_1",
        "tenant_id": "ten_1",
        "external_end_user_id": "wxid_existing",
        "status": "active",
    }
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "gateway account reply"
    bind_session_service = MagicMock()

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "cokeAccountId": "acct_1",
            },
        }
    )

    assert result == {"status": "ok", "reply": "gateway account reply"}
    external_identity_dao.find_active_identity.assert_not_called()
    external_identity_dao.find_active_identity_for_account_in_tenant.assert_called_once_with(
        "acct_1",
        "ten_1",
    )
    bind_session_service.consume_matching_session.assert_not_called()
    bind_session_service.consume_matching_session_from_text.assert_not_called()
    message_gateway.enqueue.assert_called_once()


def test_handle_inbound_uses_tenant_scoped_identity_when_account_has_multiple_active_identities():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()

    def _find_active_identity_for_account_in_tenant(account_id, tenant_id):
        if account_id == "acct_1" and tenant_id == "ten_1":
            return {
                "account_id": "acct_1",
                "tenant_id": "ten_1",
                "channel_id": "ch_1",
                "platform": "wechat_personal",
                "external_end_user_id": "wxid_tenant_1",
                "status": "active",
            }
        if account_id == "acct_1" and tenant_id == "ten_2":
            return {
                "account_id": "acct_1",
                "tenant_id": "ten_2",
                "channel_id": "ch_2",
                "platform": "wechat_personal",
                "external_end_user_id": "wxid_tenant_2",
                "status": "active",
            }
        return None

    external_identity_dao.find_active_identity_for_account_in_tenant.side_effect = (
        _find_active_identity_for_account_in_tenant
    )
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "tenant-scoped reply"
    bind_session_service = MagicMock()

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "cokeAccountId": "acct_1",
            },
        }
    )

    assert result == {"status": "ok", "reply": "tenant-scoped reply"}
    external_identity_dao.find_active_identity_for_account_in_tenant.assert_called_once_with(
        "acct_1",
        "ten_1",
    )
    external_identity_dao.find_active_identity.assert_not_called()
    bind_session_service.consume_matching_session.assert_not_called()
    bind_session_service.consume_matching_session_from_text.assert_not_called()
    message_gateway.enqueue.assert_called_once_with(
        account_id="acct_1",
        character_id="char_1",
        text="你好",
        inbound={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "conversation_id": "conv_1",
            "platform": "wechat_personal",
            "end_user_id": "eu_1",
            "external_id": "wxid_123",
            "external_message_id": "conv_1",
            "timestamp": ANY,
        },
    )


def test_handle_inbound_falls_back_to_legacy_lookup_when_gateway_trust_check_fails():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account_in_tenant.return_value = None
    external_identity_dao.find_active_identity.return_value = {
        "account_id": "user_legacy",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_legacy"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "legacy reply"
    bind_session_service = MagicMock()

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "cokeAccountId": "acct_1",
            },
        }
    )

    assert result == {"status": "ok", "reply": "legacy reply"}
    external_identity_dao.find_active_identity_for_account_in_tenant.assert_called_once_with(
        "acct_1",
        "ten_1",
    )
    external_identity_dao.find_active_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
    )
    bind_session_service.consume_matching_session.assert_not_called()
    bind_session_service.consume_matching_session_from_text.assert_not_called()
    message_gateway.enqueue.assert_called_once_with(
        account_id="user_legacy",
        character_id="char_1",
        text="你好",
        inbound={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "conversation_id": "conv_1",
            "platform": "wechat_personal",
            "end_user_id": "eu_1",
            "external_id": "wxid_123",
            "external_message_id": "conv_1",
            "timestamp": ANY,
        },
    )


def test_handle_inbound_without_matching_bind_session_returns_bind_required():
    from connector.clawscale_bridge.identity_service import IdentityService

    service = IdentityService(
        external_identity_dao=MagicMock(find_active_identity=MagicMock(return_value=None)),
        binding_ticket_dao=MagicMock(),
        bind_session_service=MagicMock(
            consume_matching_session=MagicMock(return_value=None),
            consume_matching_session_from_text=MagicMock(return_value=None),
        ),
        message_gateway=MagicMock(),
        reply_waiter=MagicMock(),
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )
    service.issue_or_reuse_binding_ticket = MagicMock(
        return_value={"bind_url": "https://coke.local/bind/bt_1"}
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "contextToken": "ctx_missing",
            },
        }
    )

    assert result["status"] == "bind_required"
    assert result["bind_url"] == "https://coke.local/bind/bt_1"


def test_handle_inbound_returns_bind_required_when_frozen_personal_bind_code_has_no_legacy_identity():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "绑定码匹配后的回复"
    bind_session_service = MagicMock()
    bind_session_service.consume_matching_session.return_value = None
    bind_session_service.consume_matching_session_from_text.return_value = None

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )
    service.issue_or_reuse_binding_ticket = MagicMock(
        return_value={"bind_url": "https://coke.local/bind/bt_1"}
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "COKE-184263"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
            },
        }
    )

    assert result == {
        "status": "bind_required",
        "reply": "请先绑定账号: https://coke.local/bind/bt_1",
        "bind_url": "https://coke.local/bind/bt_1",
    }
    bind_session_service.consume_matching_session_from_text.assert_called_once()
    external_identity_dao.find_active_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
    )
