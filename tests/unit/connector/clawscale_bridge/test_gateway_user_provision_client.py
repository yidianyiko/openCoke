import requests
from unittest.mock import MagicMock, patch


def test_gateway_user_provision_client_posts_expected_request():
    from connector.clawscale_bridge.gateway_user_provision_client import (
        GatewayUserProvisionClient,
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "ok": True,
        "data": {
            "tenant_id": "ten_1",
            "clawscale_user_id": "csu_1",
        },
    }

    with patch(
        "connector.clawscale_bridge.gateway_user_provision_client.requests.post",
        return_value=response,
    ) as mock_post:
        client = GatewayUserProvisionClient(
            api_url="https://gateway.coke.local/api/internal/coke-users/provision",
            api_key="secret",
        )
        result = client.ensure_user(account_id="acct_1", display_name="Alice")

    assert result == {"tenant_id": "ten_1", "clawscale_user_id": "csu_1"}
    mock_post.assert_called_once_with(
        url="https://gateway.coke.local/api/internal/coke-users/provision",
        json={"coke_account_id": "acct_1", "display_name": "Alice"},
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )


def test_gateway_user_provision_client_wraps_request_failures():
    from connector.clawscale_bridge.gateway_user_provision_client import (
        GatewayUserProvisionClient,
        GatewayUserProvisionClientError,
    )

    with patch(
        "connector.clawscale_bridge.gateway_user_provision_client.requests.post",
        side_effect=requests.Timeout("timeout"),
    ):
        client = GatewayUserProvisionClient(
            api_url="https://gateway.coke.local/api/internal/coke-users/provision",
            api_key="secret",
        )

        try:
            client.ensure_user(account_id="acct_1")
        except GatewayUserProvisionClientError as exc:
            assert str(exc) == "gateway_user_provision_request_failed"
        else:
            raise AssertionError("expected GatewayUserProvisionClientError")
