from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import httpx

from coke.domains.channel_reachability.models import (
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import (
    configured_http_client,
    freeze_json,
    invalid_provider_payload,
    missing_provider_config,
    optional_string_field,
    post_json_send,
    required_string_field,
)


class WeChatPersonalAdapter:
    provider_type = "wechat_personal"

    def __init__(
        self,
        endpoint_url: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self._client = configured_http_client(http_client, timeout)
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "wxid"),
            text=optional_string_field(
                self.provider_type, payload, "text", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(
                self.provider_type, payload, "message_id"
            ),
            received_at=self._now(),
            account_id=optional_string_field(self.provider_type, payload, "account_id"),
            connector_session_id=optional_string_field(
                self.provider_type, payload, "session_id"
            ),
            context_token=optional_string_field(
                self.provider_type, payload, "context_token"
            ),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def start_login(self, *, account_id: str) -> dict[str, object]:
        if not self.endpoint_url:
            raise invalid_provider_payload(
                self.provider_type, "endpoint_url", "provider_not_configured"
            )
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        response = self._client.post(
            f"{self._connector_base_url()}/login/start",
            headers=headers,
            json={"account_id": account_id},
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    def poll_login_status(self, *, account_id: str, session_id: str) -> dict[str, object]:
        if not self.endpoint_url:
            raise invalid_provider_payload(
                self.provider_type, "endpoint_url", "provider_not_configured"
            )
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        try:
            response = self._client.get(
                f"{self._connector_base_url()}/login/status",
                headers=headers,
                params={"account_id": account_id, "session_id": session_id},
                timeout=5.0,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return {
                "account_id": account_id,
                "session_id": session_id,
                "status": "waiting_for_scan",
                "connector_status": "timeout",
                "retryable": True,
            }
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
        context_token: str | None = None,
    ) -> DeliveryAttemptResult:
        if not self.endpoint_url:
            return missing_provider_config()
        if not context_token:
            return DeliveryAttemptResult(
                status="failed",
                provider_message_id=None,
                error_code="context_token_required",
                delivered_at=None,
            )
        headers = {"Idempotency-Key": idempotency_key}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        return post_json_send(
            provider_type=self.provider_type,
            client=self._client,
            url=self.endpoint_url,
            headers=headers,
            body={
                "account_id": route.account_id,
                "to": route.provider_address,
                "context_token": context_token,
                "text": text,
            },
        )

    def _connector_base_url(self) -> str:
        endpoint_url = str(self.endpoint_url or "").rstrip("/")
        if endpoint_url.endswith("/send"):
            return endpoint_url[: -len("/send")]
        return endpoint_url
