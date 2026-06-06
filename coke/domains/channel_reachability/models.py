from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeAlias

from coke.domains.conversation_runtime.models import InboundMediaInput

ChannelConnectionState = Literal[
    "not_connected",
    "connecting",
    "connected",
    "connection_failed",
    "reconnection_required",
    "removed",
]
ChannelLifecycle = Literal["active", "removed"]
DeliveryRouteLifecycle = Literal["active", "removed"]
DeliveryAttemptStatus = Literal["sent", "delivered", "failed"]

PRODUCT_CHANNEL_PROVIDER_TYPES = frozenset({"whatsapp_evolution", "wechat_personal"})
RETAINED_PROVIDER_TYPES = frozenset(
    {
        "whatsapp_evolution",
        "wechat_personal",
        "wechat_ecloud",
        "linq",
    }
)
ImmutableJsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | tuple["ImmutableJsonValue", ...]
    | Mapping[str, "ImmutableJsonValue"]
)


class ChannelReachabilityError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class Channel:
    id: str
    account_id: str
    channel_identity_id: str
    provider_type: str
    lifecycle: ChannelLifecycle
    connection_state: ChannelConnectionState
    removable: bool
    connected_at: datetime | None
    removed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryRoute:
    id: str
    account_id: str
    channel_id: str
    provider_type: str
    provider_address: str
    route_key: str
    lifecycle: DeliveryRouteLifecycle
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    id: str
    route_id: str
    provider_type: str
    provider_idempotency_key: str
    status: DeliveryAttemptStatus
    provider_message_id: str | None
    error_code: str | None
    attempted_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    turn_id: str | None = None
    message_id: str | None = None
    delivery_source: str | None = None
    delivery_intent: str | None = None
    retry_attempt: int | None = None
    traceparent: str | None = None
    container: str | None = None
    context_token_source: str | None = None
    context_token_age_seconds: int | None = None
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class DeliveryAttemptResult:
    status: DeliveryAttemptStatus
    provider_message_id: str | None
    error_code: str | None
    delivered_at: datetime | None


@dataclass(frozen=True, slots=True)
class NormalizedInbound:
    provider_type: str
    provider_subject: str
    text: str
    raw_event_id: str
    received_at: datetime
    pairing_code: str | None = None
    sender_display_name: str | None = None
    account_id: str | None = None
    connector_session_id: str | None = None
    context_token: str | None = None
    payload: Mapping[str, ImmutableJsonValue] | None = None
    media: tuple[InboundMediaInput, ...] = ()


@dataclass(frozen=True, slots=True)
class ChannelStatus:
    account_id: str
    channel_id: str | None
    provider_type: str | None
    connection_state: ChannelConnectionState
    reachable: bool
    pairing_code: str | None = None
    pairing_expires_at: float | None = None
    instructions: str | None = None
    session_id: str | None = None
    qrcode_id: str | None = None
    qrcode_image: str | None = None
    connector_status: str | None = None
    masked_identity: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderWebhookAcceptance:
    accepted: bool
    provider_type: str
    provider_subject: str
    account_id: str
    channel_identity_id: str
    channel_id: str
    created_account: bool
    raw_event_id: str
