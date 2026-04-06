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
        "status": "pending",
        "connect_url": "https://wx.example.com/entry?bind_token=ctx_123",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "pending"
    assert result["connect_url"].startswith("https://wx.example.com/entry")
    assert "bind_token" not in result
    assert "account_id" not in result


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
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
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
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.get_status(account_id="user_1", now_ts=1775472000)

    assert result == {"status": "expired"}
