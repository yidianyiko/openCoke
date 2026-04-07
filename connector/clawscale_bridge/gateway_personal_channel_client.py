from __future__ import annotations

import requests


class GatewayPersonalChannelClientError(RuntimeError):
    pass


class GatewayPersonalChannelClient:
    def __init__(self, api_base_url: str, api_key: str, timeout_seconds: float = 10.0):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_response(self, response, failure_code: str) -> dict:
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise GatewayPersonalChannelClientError("gateway_personal_channel_request_failed") from exc
        except ValueError as exc:
            raise GatewayPersonalChannelClientError("invalid_gateway_personal_channel_response") from exc

        if not isinstance(payload, dict):
            raise GatewayPersonalChannelClientError(
                "invalid_gateway_personal_channel_response"
            )
        if not payload.get("ok"):
            raise GatewayPersonalChannelClientError(
                payload.get("error", failure_code)
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise GatewayPersonalChannelClientError(
                "invalid_gateway_personal_channel_response"
            )
        return data

    def _request(self, request_fn, *, url: str, failure_code: str, **kwargs) -> dict:
        try:
            response = request_fn(
                url=url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise GatewayPersonalChannelClientError(
                "gateway_personal_channel_request_failed"
            ) from exc
        return self._parse_response(response, failure_code)

    def create_or_reuse_channel(self, account_id: str):
        return self._request(
            requests.post,
            url=self.api_base_url,
            json={"account_id": account_id},
            failure_code="create_failed",
        )

    def connect_channel(self, account_id: str):
        return self._request(
            requests.post,
            url=f"{self.api_base_url}/connect",
            json={"account_id": account_id},
            failure_code="connect_failed",
        )

    def get_status(self, account_id: str):
        return self._request(
            requests.get,
            url=f"{self.api_base_url}/status",
            params={"account_id": account_id},
            failure_code="status_failed",
        )

    def disconnect_channel(self, account_id: str):
        return self._request(
            requests.post,
            url=f"{self.api_base_url}/disconnect",
            json={"account_id": account_id},
            failure_code="disconnect_failed",
        )

    def archive_channel(self, account_id: str):
        return self._request(
            requests.delete,
            url=self.api_base_url,
            json={"account_id": account_id},
            failure_code="archive_failed",
        )
