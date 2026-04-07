from unittest.mock import MagicMock


def _build_service(bind_session_dao, external_identity_dao, gateway_identity_client):
    from connector.clawscale_bridge.wechat_bind_session_service import (
        WechatBindSessionService,
    )

    return WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )


def test_create_or_reuse_session_returns_sanitized_pending_payload():
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
    gateway_identity_client = MagicMock()

    service = _build_service(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "pending"
    assert result["connect_url"] == "https://bridge.coke.local/user/wechat-bind/entry/ctx_123"
    assert "bind_token" not in result
    assert "account_id" not in result
    assert "bind_code" not in result


def test_create_or_reuse_session_returns_bound_when_account_already_linked():
    bind_session_dao = MagicMock()
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = {
        "external_end_user_id": "wxid_9f2c8e0a",
        "status": "active",
    }
    gateway_identity_client = MagicMock()

    service = _build_service(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "bound"
    assert result["masked_identity"].startswith("wxid_")


def test_get_status_returns_expired_when_latest_session_elapsed():
    bind_session_dao = MagicMock()
    bind_session_dao.find_latest_session_for_account.return_value = {
        "session_id": "bs_1",
        "status": "pending",
        "expires_at": 1775471999,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None
    gateway_identity_client = MagicMock()

    service = _build_service(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
    )

    result = service.get_status(account_id="user_1", now_ts=1775472000)

    assert result == {"status": "expired"}


def test_consume_matching_session_returns_none_for_frozen_personal_path_without_writes():
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
    external_identity_dao.find_active_identity_for_account.return_value = None
    gateway_identity_client = MagicMock()

    service = _build_service(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
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

    assert identity is None
    external_identity_dao.find_active_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
    )


def test_consume_matching_session_returns_existing_personal_identity_without_writes():
    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    existing_identity = {
        "account_id": "user_1",
        "tenant_id": "ten_other",
        "channel_id": "ch_other",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }
    external_identity_dao.find_active_identity.return_value = existing_identity
    external_identity_dao.find_active_identity_for_account.return_value = existing_identity
    gateway_identity_client = MagicMock()

    service = _build_service(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
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

    assert identity == existing_identity
    external_identity_dao.find_active_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
    )


def test_consume_matching_session_from_text_returns_none_for_frozen_personal_path_without_writes():
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
    gateway_identity_client = MagicMock()

    service = _build_service(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
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

    assert identity is None
    bind_session_dao.find_active_session_by_bind_code.assert_called_once_with(
        "COKE-184263", 1775472000
    )
    external_identity_dao.find_active_identity.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
    )
