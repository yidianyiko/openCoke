from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import httpx

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import (
    configured_http_client,
    epoch_seconds_to_utc,
    freeze_json,
    invalid_provider_payload,
    missing_provider_config,
    optional_string_field,
    post_json_send,
    required_bool_field,
    required_mapping_field,
    required_number_field,
    required_string_field,
)


class WhatsAppEvolutionAdapter:
    provider_type = "whatsapp_evolution"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        instance: str | None = None,
        *,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.instance = instance
        self._client = configured_http_client(http_client, timeout)
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        event = required_string_field(self.provider_type, payload, "event")
        if event != "messages.upsert":
            raise invalid_provider_payload(
                self.provider_type, "event", "unsupported_event"
            )
        data = required_mapping_field(self.provider_type, payload, "data")
        key = required_mapping_field(self.provider_type, data, "key")
        message_id = _required_string_at_path(
            self.provider_type, key, "id", "data.key.id"
        )
        remote_jid = _required_string_at_path(
            self.provider_type, key, "remoteJid", "data.key.remoteJid"
        )
        from_me = required_bool_field(self.provider_type, key, "fromMe")
        if from_me:
            raise ChannelReachabilityError(
                "provider_outbound_echo",
                fact={
                    "type": "provider_outbound_echo",
                    "provider_type": self.provider_type,
                    "raw_event_id": message_id,
                },
            )
        message = required_mapping_field(self.provider_type, data, "message")
        timestamp = required_number_field(self.provider_type, data, "messageTimestamp")
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=_strip_evolution_jid(remote_jid),
            text=_message_text(self.provider_type, message),
            raw_event_id=message_id,
            received_at=epoch_seconds_to_utc(timestamp),
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
        if not self.base_url or not self.api_key or not self.instance:
            return missing_provider_config()
        return post_json_send(
            provider_type=self.provider_type,
            client=self._client,
            url=f"{self.base_url}/message/sendText/{self.instance}",
            headers={
                "apikey": self.api_key,
                "Idempotency-Key": idempotency_key,
            },
            body={
                "number": route.provider_address,
                "text": text,
            },
        )


def _strip_evolution_jid(remote_jid: str) -> str:
    for suffix in ("@s.whatsapp.net", "@g.us"):
        if remote_jid.endswith(suffix):
            return remote_jid[: -len(suffix)]
    return remote_jid


def _required_string_at_path(
    provider_type: str,
    payload: Mapping[str, object],
    key: str,
    path: str,
) -> str:
    try:
        return required_string_field(provider_type, payload, key)
    except ChannelReachabilityError as error:
        if error.code == "invalid_provider_payload" and error.fact is not None:
            raise invalid_provider_payload(
                provider_type,
                path,
                str(error.fact.get("reason", "invalid_required_field")),
            ) from error
        raise


def _message_text(provider_type: str, message: Mapping[str, object]) -> str:
    if "conversation" in message:
        value = optional_string_field(
            provider_type,
            message,
            "conversation",
            allow_blank=True,
        )
        if value is None:
            raise invalid_provider_payload(
                provider_type,
                "data.message.conversation",
                "invalid_optional_field",
            )
        return value
    extended = message.get("extendedTextMessage")
    if extended is not None:
        if not isinstance(extended, Mapping):
            raise invalid_provider_payload(
                provider_type,
                "data.message.extendedTextMessage",
                "invalid_optional_field",
            )
        value = optional_string_field(
            provider_type,
            extended,
            "text",
            allow_blank=True,
        )
        if value is None:
            raise invalid_provider_payload(
                provider_type,
                "data.message.extendedTextMessage.text",
                "invalid_optional_field",
            )
        return value
    return ""
