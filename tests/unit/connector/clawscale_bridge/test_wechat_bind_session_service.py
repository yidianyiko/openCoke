from unittest.mock import MagicMock


def test_create_or_reuse_session_returns_sanitized_pending_payload():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_for_account.return_value = None
    bind_session_dao.create_session.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_123",
        "bind_code": "COKE-123456",
        "status": "pending",
        "connect_url": "https://bridge.coke.local/user/wechat-bind/entry/ctx_123",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "pending"
    assert result["connect_url"] == "https://bridge.coke.local/user/wechat-bind/entry/ctx_123"
    assert "bind_token" not in result
    assert "account_id" not in result
    assert "bind_code" not in result


def test_create_or_reuse_session_returns_bound_when_account_already_linked():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = {
        "external_end_user_id": "wxid_9f2c8e0a",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "bound"
    assert result["masked_identity"].startswith("wxid_")


def test_get_status_returns_expired_when_latest_session_elapsed():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_latest_session_for_account.return_value = {
        "session_id": "bs_1",
        "status": "pending",
        "expires_at": 1775471999,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.get_status(account_id="user_1", now_ts=1775472000)

    assert result == {"status": "expired"}


def test_consume_matching_session_creates_external_identity_and_marks_session_bound():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None
    external_identity_dao.find_active_identity.return_value = None
    external_identity_dao.activate_identity.return_value = {
        "account_id": "user_1",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session(
        bind_token="ctx_bind_123",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        now_ts=1775472000,
    )

    assert identity["account_id"] == "user_1"
    external_identity_dao.activate_identity.assert_called_once()
    bind_session_dao.mark_bound.assert_called_once()


def test_consume_matching_session_creates_current_tuple_when_account_has_same_sender_elsewhere():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    external_identity_dao.find_active_identity_for_account.return_value = {
        "account_id": "user_1",
        "tenant_id": "ten_other",
        "channel_id": "ch_other",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }
    external_identity_dao.activate_identity.return_value = {
        "account_id": "user_1",
        "tenant_id": "ten_1",
        "channel_id": "ch_1",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session(
        bind_token="ctx_bind_123",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        now_ts=1775472000,
    )

    assert identity["tenant_id"] == "ten_1"
    external_identity_dao.activate_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        account_id="user_1",
        now_ts=1775472000,
    )
    bind_session_dao.mark_bound.assert_called_once()


def test_consume_matching_session_returns_none_for_different_active_identity():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    external_identity_dao.find_active_identity_for_account.return_value = {
        "account_id": "user_1",
        "external_end_user_id": "wxid_existing",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session(
        bind_token="ctx_bind_123",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_new_sender",
        now_ts=1775472000,
    )

    assert identity is None
    external_identity_dao.activate_identity.assert_not_called()
    bind_session_dao.mark_bound.assert_not_called()


def test_get_entry_page_context_omits_placeholder_public_entry():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "bind_code": "COKE-184263",
        "status": "pending",
        "connect_url": "https://bridge.coke.local/user/wechat-bind/entry/ctx_bind_123",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    context = service.get_entry_page_context("ctx_bind_123", now_ts=1775472000)

    assert context["status"] == "pending"
    assert context["bind_code"] == "COKE-184263"
    assert context["public_connect_url"] is None


def test_consume_matching_session_from_text_binds_with_one_time_code():
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_code.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "bind_code": "COKE-184263",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    external_identity_dao.find_active_identity_for_account.return_value = None
    external_identity_dao.activate_identity.return_value = {
        "account_id": "user_1",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session_from_text(
        text="COKE-184263",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        now_ts=1775472000,
    )

    assert identity["account_id"] == "user_1"
    bind_session_dao.find_active_session_by_bind_code.assert_called_once_with(
        "COKE-184263", 1775472000
    )
