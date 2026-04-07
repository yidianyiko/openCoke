from unittest.mock import MagicMock


def test_handle_inbound_consumes_matching_bind_session_before_reply():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "绑定成功后的第一条回复"
    bind_session_service = MagicMock()
    bind_session_service.consume_matching_session.return_value = {"account_id": "user_1"}

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
                "contextToken": "ctx_bind_123",
            },
        }
    )

    assert result == {"status": "ok", "reply": "绑定成功后的第一条回复"}
    bind_session_service.consume_matching_session.assert_called_once()


def test_handle_inbound_uses_gateway_coke_account_id_without_bind_lookup():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
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
    bind_session_service.consume_matching_session.assert_not_called()
    bind_session_service.consume_matching_session_from_text.assert_not_called()
    message_gateway.enqueue.assert_called_once()


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


def test_handle_inbound_consumes_matching_bind_code_before_bind_required():
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
    bind_session_service.consume_matching_session_from_text.return_value = {
        "account_id": "user_1"
    }

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

    assert result == {"status": "ok", "reply": "绑定码匹配后的回复"}
    bind_session_service.consume_matching_session_from_text.assert_called_once()
