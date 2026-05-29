from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from types import MappingProxyType
from typing import Protocol

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    ImmutableJsonValue,
    NormalizedInbound,
)


class ProviderAdapter(Protocol):
    provider_type: str

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        ...

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        ...


def provider_registry(adapters: Iterable[ProviderAdapter]) -> dict[str, ProviderAdapter]:
    registry: dict[str, ProviderAdapter] = {}
    for adapter in adapters:
        if adapter.provider_type in registry:
            raise ValueError(f"duplicate_provider_adapter:{adapter.provider_type}")
        registry[adapter.provider_type] = adapter
    return registry


def optional_string_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
) -> str | None:
    if field not in payload or payload[field] is None:
        return None
    value = _string_value(payload[field])
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_optional_field",
            },
        )
    return value


def required_string_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
) -> str:
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
    value = _string_value(payload[field])
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


def _string_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def freeze_json(
    value: object, provider_type: str, path: str = "payload"
) -> ImmutableJsonValue:
    if isinstance(value, Mapping):
        frozen: dict[str, ImmutableJsonValue] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ChannelReachabilityError(
                    "invalid_provider_payload",
                    fact={
                        "type": "invalid_provider_payload",
                        "provider_type": provider_type,
                        "field": path,
                        "reason": "non_json_payload_key",
                    },
                )
            frozen[key] = freeze_json(nested_value, provider_type, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(
            freeze_json(nested_value, provider_type, f"{path}[{index}]")
            for index, nested_value in enumerate(value)
        )
    if isinstance(value, float) and not isfinite(value):
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": path,
                "reason": "non_json_payload_value",
            },
        )
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ChannelReachabilityError(
        "invalid_provider_payload",
        fact={
            "type": "invalid_provider_payload",
            "provider_type": provider_type,
            "field": path,
            "reason": "non_json_payload_value",
        },
    )
