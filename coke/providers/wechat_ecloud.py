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
    missing_provider_config,
    optional_string_field,
    post_json_send,
    required_string_field,
)


class WeChatECloudAdapter:
    provider_type = "wechat_ecloud"

    def __init__(
        self,
        endpoint_url: str | None = None,
        token: str | None = None,
        app_id: str | None = None,
        *,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.token = token
        self.app_id = app_id
        self._client = configured_http_client(http_client, timeout)
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(
                self.provider_type, payload, "sender_id"
            ),
            text=optional_string_field(
                self.provider_type, payload, "content", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(self.provider_type, payload, "msg_id"),
            received_at=self._now(),
            pairing_code=optional_string_field(
                self.provider_type, payload, "pairing_code"
            ),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        if not self.endpoint_url or not self.app_id:
            return missing_provider_config()
        headers = {"Idempotency-Key": idempotency_key}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Token"] = self.token
        return post_json_send(
            provider_type=self.provider_type,
            client=self._client,
            url=self.endpoint_url,
            headers=headers,
            body={
                "appId": self.app_id,
                "toWxid": route.provider_address,
                "content": text,
            },
        )
