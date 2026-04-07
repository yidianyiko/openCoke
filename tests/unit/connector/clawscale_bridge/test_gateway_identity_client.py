from unittest.mock import MagicMock, patch


def test_gateway_identity_client_posts_expected_payload_and_returns_binding_data():
    from connector.clawscale_bridge.gateway_identity_client import (
        GatewayIdentityClient,
    )

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "data": {
            "clawscale_user_id": "csu_1",
            "end_user_id": "eu_1",
            "coke_account_id": "acct_1",
        },
    }

    with patch(
        "connector.clawscale_bridge.gateway_identity_client.requests.post",
        return_value=response,
    ) as mock_post:
        client = GatewayIdentityClient(
            api_url="https://gateway.coke.local/api/internal/coke-bindings",
            api_key="secret",
        )
        result = client.bind_identity(
            tenant_id="ten_1",
            channel_id="ch_1",
            external_id="ext_1",
            coke_account_id="acct_1",
        )

    assert result == {
        "clawscale_user_id": "csu_1",
        "end_user_id": "eu_1",
        "coke_account_id": "acct_1",
    }
    mock_post.assert_called_once_with(
        url="https://gateway.coke.local/api/internal/coke-bindings",
        json={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "external_id": "ext_1",
            "coke_account_id": "acct_1",
        },
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
    )
