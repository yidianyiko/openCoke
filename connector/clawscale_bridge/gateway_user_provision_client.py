from __future__ import annotations

import requests


class GatewayUserProvisionClientError(RuntimeError):
    pass


class GatewayUserProvisionClient:
    def __init__(self, api_url: str, api_key: str, timeout_seconds: float = 10.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def ensure_user(self, account_id: str, display_name: str | None = None):
        payload = {"coke_account_id": account_id}
        if display_name and display_name.strip():
            payload["display_name"] = display_name.strip()

        try:
            response = requests.post(
                url=self.api_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise GatewayUserProvisionClientError(
                "gateway_user_provision_request_failed"
            ) from exc
        except ValueError as exc:
            raise GatewayUserProvisionClientError(
                "invalid_gateway_user_provision_response"
            ) from exc

        if not isinstance(body, dict):
            raise GatewayUserProvisionClientError(
                "invalid_gateway_user_provision_response"
            )
        if not body.get("ok"):
            raise GatewayUserProvisionClientError(
                body.get("error", "gateway_user_provision_failed")
            )
        data = body.get("data")
        if not isinstance(data, dict):
            raise GatewayUserProvisionClientError(
                "invalid_gateway_user_provision_response"
            )
        return data
