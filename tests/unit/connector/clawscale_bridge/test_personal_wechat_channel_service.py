from unittest.mock import MagicMock


def test_start_connect_normalizes_pending_qr_url_to_connect_url():
    from connector.clawscale_bridge.personal_wechat_channel_service import (
        PersonalWechatChannelService,
    )

    gateway_client = MagicMock()
    gateway_client.connect_channel.return_value = {
        "channel_id": "ch_1",
        "status": "pending",
        "qr": "data:image/png;base64,abc",
        "qr_url": "https://liteapp.weixin.qq.com/q/demo",
    }

    service = PersonalWechatChannelService(gateway_client=gateway_client)

    result = service.start_connect(account_id="acct_1")

    assert result["status"] == "pending"
    assert result["connect_url"] == "https://liteapp.weixin.qq.com/q/demo"
    assert result["qr_code"] == "data:image/png;base64,abc"
    assert result["qr_code_url"] == "https://liteapp.weixin.qq.com/q/demo"


def test_get_status_normalizes_pending_qr_url_to_connect_url():
    from connector.clawscale_bridge.personal_wechat_channel_service import (
        PersonalWechatChannelService,
    )

    gateway_client = MagicMock()
    gateway_client.get_status.return_value = {
        "channel_id": "ch_1",
        "status": "pending",
        "qr": "data:image/png;base64,abc",
        "qr_url": "https://liteapp.weixin.qq.com/q/demo",
    }

    service = PersonalWechatChannelService(gateway_client=gateway_client)

    result = service.get_status(account_id="acct_1")

    assert result["status"] == "pending"
    assert result["connect_url"] == "https://liteapp.weixin.qq.com/q/demo"
    assert result["qr_code"] == "data:image/png;base64,abc"
    assert result["qr_code_url"] == "https://liteapp.weixin.qq.com/q/demo"


def test_disconnect_channel_preserves_disconnected_state():
    from connector.clawscale_bridge.personal_wechat_channel_service import (
        PersonalWechatChannelService,
    )

    gateway_client = MagicMock()
    gateway_client.disconnect_channel.return_value = {
        "channel_id": "ch_1",
        "status": "disconnected",
        "masked_identity": "wxid_***8e0a",
    }

    service = PersonalWechatChannelService(gateway_client=gateway_client)

    result = service.disconnect_channel(account_id="acct_1")

    assert result == {
        "channel_id": "ch_1",
        "status": "disconnected",
        "masked_identity": "wxid_***8e0a",
    }


def test_archive_channel_preserves_archived_status():
    from connector.clawscale_bridge.personal_wechat_channel_service import (
        PersonalWechatChannelService,
    )

    gateway_client = MagicMock()
    gateway_client.archive_channel.return_value = {
        "channel_id": "ch_1",
        "status": "archived",
    }

    service = PersonalWechatChannelService(gateway_client=gateway_client)

    result = service.archive_channel(account_id="acct_1")

    assert result == {"channel_id": "ch_1", "status": "archived"}


def test_personal_channel_service_emits_customer_id_to_gateway_client():
    from connector.clawscale_bridge.personal_wechat_channel_service import (
        PersonalWechatChannelService,
    )

    gateway_client = MagicMock()
    gateway_client.create_or_reuse_channel.return_value = {
        "channel_id": "ch_1",
        "status": "disconnected",
    }

    service = PersonalWechatChannelService(gateway_client=gateway_client)

    result = service.create_or_reuse_channel(account_id="acct_1")

    assert result == {
        "channel_id": "ch_1",
        "status": "disconnected",
    }
    gateway_client.create_or_reuse_channel.assert_called_once_with(
        customer_id="acct_1"
    )


def test_normalize_state_preserves_flat_fields_and_adds_compatibility_aliases():
    from connector.clawscale_bridge.personal_wechat_channel_service import (
        PersonalWechatChannelService,
    )

    service = PersonalWechatChannelService(gateway_client=MagicMock())

    result = service._normalize_state(
        {
            "channel_id": "ch_1",
            "status": "pending",
            "masked_identity": "wxid_***8e0a",
            "error": "qr_generation_failed",
            "message": "scan the QR code",
            "connect_url": "https://liteapp.weixin.qq.com/q/existing",
            "qr": "data:image/png;base64,abc",
            "qr_url": "https://liteapp.weixin.qq.com/q/demo",
        }
    )

    assert result["channel_id"] == "ch_1"
    assert result["status"] == "pending"
    assert result["masked_identity"] == "wxid_***8e0a"
    assert result["error"] == "qr_generation_failed"
    assert result["message"] == "scan the QR code"
    assert result["connect_url"] == "https://liteapp.weixin.qq.com/q/existing"
    assert result["qr_code"] == "data:image/png;base64,abc"
    assert result["qr_code_url"] == "https://liteapp.weixin.qq.com/q/demo"
