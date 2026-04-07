import requests
from unittest.mock import MagicMock, patch


def test_gateway_personal_channel_client_posts_expected_disconnect_request():
    from connector.clawscale_bridge.gateway_personal_channel_client import (
        GatewayPersonalChannelClient,
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "ok": True,
        "data": {"channel_id": "ch_1", "status": "disconnected"},
    }

    with patch(
        "connector.clawscale_bridge.gateway_personal_channel_client.requests.post",
        return_value=response,
    ) as mock_post:
        client = GatewayPersonalChannelClient(
            api_base_url="https://gateway.coke.local/api/internal/user/wechat-channel",
            api_key="secret",
        )
        result = client.disconnect_channel(account_id="acct_1")

    assert result == {"channel_id": "ch_1", "status": "disconnected"}
    mock_post.assert_called_once_with(
        url="https://gateway.coke.local/api/internal/user/wechat-channel/disconnect",
        json={"account_id": "acct_1"},
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )


def test_gateway_personal_channel_client_deletes_expected_archive_request():
    from connector.clawscale_bridge.gateway_personal_channel_client import (
        GatewayPersonalChannelClient,
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "ok": True,
        "data": {"channel_id": "ch_1", "status": "archived"},
    }

    with patch(
        "connector.clawscale_bridge.gateway_personal_channel_client.requests.delete",
        return_value=response,
    ) as mock_delete:
        client = GatewayPersonalChannelClient(
            api_base_url="https://gateway.coke.local/api/internal/user/wechat-channel",
            api_key="secret",
        )
        result = client.archive_channel(account_id="acct_1")

    assert result == {"channel_id": "ch_1", "status": "archived"}
    mock_delete.assert_called_once_with(
        url="https://gateway.coke.local/api/internal/user/wechat-channel",
        json={"account_id": "acct_1"},
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )


def test_gateway_personal_channel_client_wraps_request_failures():
    from connector.clawscale_bridge.gateway_personal_channel_client import (
        GatewayPersonalChannelClient,
        GatewayPersonalChannelClientError,
    )

    with patch(
        "connector.clawscale_bridge.gateway_personal_channel_client.requests.post",
        side_effect=requests.Timeout("timeout"),
    ):
        client = GatewayPersonalChannelClient(
            api_base_url="https://gateway.coke.local/api/internal/user/wechat-channel",
            api_key="secret",
        )

        try:
            client.create_or_reuse_channel(account_id="acct_1")
        except GatewayPersonalChannelClientError as exc:
            assert str(exc) == "gateway_personal_channel_request_failed"
        else:
            raise AssertionError("expected GatewayPersonalChannelClientError")
