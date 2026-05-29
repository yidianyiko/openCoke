from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from coke.domains.channel_reachability.models import (
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import freeze_json, optional_string_field, required_string_field


class WhatsAppEvolutionAdapter:
    provider_type = "whatsapp_evolution"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "sender"),
            text=optional_string_field(self.provider_type, payload, "text") or "",
            raw_event_id=required_string_field(self.provider_type, payload, "message_id"),
            received_at=self._now(),
            pairing_code=optional_string_field(self.provider_type, payload, "pairing_code"),
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
