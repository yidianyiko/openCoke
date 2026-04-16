import requests
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
            account_id="acct_1",
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
            "customer_id": "acct_1",
        },
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )


def test_gateway_identity_client_raises_on_non_ok_response_payload():
    from connector.clawscale_bridge.gateway_identity_client import (
        GatewayIdentityClientError,
        GatewayIdentityClient,
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": False, "error": "end_user_already_bound"}

    with patch(
        "connector.clawscale_bridge.gateway_identity_client.requests.post",
        return_value=response,
    ):
        client = GatewayIdentityClient(
            api_url="https://gateway.coke.local/api/internal/coke-bindings",
            api_key="secret",
        )

        try:
            client.bind_identity(
                tenant_id="ten_1",
                channel_id="ch_1",
                external_id="ext_1",
                account_id="acct_1",
            )
        except GatewayIdentityClientError as exc:
            assert str(exc) == "end_user_already_bound"
        else:
            raise AssertionError("expected GatewayIdentityClientError")


def test_gateway_identity_client_wraps_request_timeout_as_explicit_failure():
    from connector.clawscale_bridge.gateway_identity_client import (
        GatewayIdentityClient,
        GatewayIdentityClientError,
    )

    with patch(
        "connector.clawscale_bridge.gateway_identity_client.requests.post",
        side_effect=requests.Timeout("timeout"),
    ):
        client = GatewayIdentityClient(
            api_url="https://gateway.coke.local/api/internal/coke-bindings",
            api_key="secret",
        )

        try:
            client.bind_identity(
                tenant_id="ten_1",
                channel_id="ch_1",
                external_id="ext_1",
                account_id="acct_1",
            )
        except GatewayIdentityClientError as exc:
            assert str(exc) == "gateway_identity_request_failed"
        else:
            raise AssertionError("expected GatewayIdentityClientError")


def test_gateway_identity_client_wraps_malformed_json_payload_as_explicit_failure():
    from connector.clawscale_bridge.gateway_identity_client import (
        GatewayIdentityClient,
        GatewayIdentityClientError,
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("bad json")

    with patch(
        "connector.clawscale_bridge.gateway_identity_client.requests.post",
        return_value=response,
    ):
        client = GatewayIdentityClient(
            api_url="https://gateway.coke.local/api/internal/coke-bindings",
            api_key="secret",
        )

        try:
            client.bind_identity(
                tenant_id="ten_1",
                channel_id="ch_1",
                external_id="ext_1",
                account_id="acct_1",
            )
        except GatewayIdentityClientError as exc:
            assert str(exc) == "invalid_gateway_identity_response"
        else:
            raise AssertionError("expected GatewayIdentityClientError")
