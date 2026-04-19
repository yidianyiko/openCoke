from __future__ import annotations

import requests


class GatewayDeliveryRouteClientError(RuntimeError):
    pass


class GatewayDeliveryRouteClient:
    def __init__(self, api_url: str, api_key: str, timeout_seconds: float = 10.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def bind(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        account_id: str,
        business_conversation_key: str,
        channel_id: str,
        end_user_id: str,
        external_end_user_id: str,
    ) -> dict:
        try:
            response = requests.post(
                url=self.api_url,
                json={
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "account_id": account_id,
                    "business_conversation_key": business_conversation_key,
                    "channel_id": channel_id,
                    "end_user_id": end_user_id,
                    "external_end_user_id": external_end_user_id,
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
            raise GatewayDeliveryRouteClientError(
                "gateway_delivery_route_request_failed"
            ) from exc
        except ValueError as exc:
            raise GatewayDeliveryRouteClientError(
                "invalid_gateway_delivery_route_response"
            ) from exc

        if not isinstance(payload, dict):
            raise GatewayDeliveryRouteClientError(
                "invalid_gateway_delivery_route_response"
            )
        if not payload.get("ok"):
            raise GatewayDeliveryRouteClientError(
                payload.get("error", "gateway_delivery_route_bind_failed")
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GatewayDeliveryRouteClientError(
                "invalid_gateway_delivery_route_response"
            )
        return data
