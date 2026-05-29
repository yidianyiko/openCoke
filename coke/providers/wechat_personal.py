from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import freeze_json


class WeChatPersonalAdapter:
    provider_type = "wechat_personal"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=_required_string(self.provider_type, payload, "wxid"),
            text=_optional_string(payload.get("text")) or "",
            raw_event_id=_required_string(self.provider_type, payload, "message_id"),
            received_at=self._now(),
            pairing_code=_optional_string(payload.get("pairing_code")),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"{self.provider_type}:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _required_string(provider_type: str, payload: Mapping[str, object], field: str) -> str:
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "missing_required_field",
            },
        )
    value = _optional_string(payload[field])
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_required_field",
            },
        )
    return value
