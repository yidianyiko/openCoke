from __future__ import annotations

import requests

from connector.clawscale_bridge.customer_ids import resolve_customer_id


class GatewayIdentityClientError(RuntimeError):
    pass


class GatewayIdentityClient:
    def __init__(self, api_url: str, api_key: str, timeout_seconds: float = 10.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def bind_identity(
        self,
        tenant_id: str,
        channel_id: str,
        external_id: str,
        customer_id: str | None = None,
        account_id: str | None = None,
        coke_account_id: str | None = None,
    ):
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
            coke_account_id=coke_account_id,
        )
        try:
            response = requests.post(
                url=self.api_url,
                json={
                    "tenant_id": tenant_id,
                    "channel_id": channel_id,
                    "external_id": external_id,
                    "customer_id": normalized_customer_id,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise GatewayIdentityClientError("gateway_identity_request_failed") from exc
        except ValueError as exc:
            raise GatewayIdentityClientError("invalid_gateway_identity_response") from exc

        if not isinstance(payload, dict):
            raise GatewayIdentityClientError("invalid_gateway_identity_response")
        if not payload.get("ok"):
            raise GatewayIdentityClientError(
                payload.get("error", "gateway_identity_bind_failed")
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GatewayIdentityClientError("invalid_gateway_identity_response")
        return data

    def bind(
        self,
        tenant_id: str,
        channel_id: str,
        external_id: str,
        customer_id: str | None = None,
        account_id: str | None = None,
        coke_account_id: str | None = None,
    ):
        return self.bind_identity(
            tenant_id=tenant_id,
            channel_id=channel_id,
            external_id=external_id,
            customer_id=customer_id,
            account_id=account_id,
            coke_account_id=coke_account_id,
        )
