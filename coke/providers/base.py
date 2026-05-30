from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType
from typing import Protocol

import httpx

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    ImmutableJsonValue,
    NormalizedInbound,
)


class ProviderAdapter(Protocol):
    provider_type: str

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound: ...

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult: ...


def provider_registry(
    adapters: Iterable[ProviderAdapter],
) -> dict[str, ProviderAdapter]:
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
    allow_blank: bool = False,
) -> str | None:
    if field not in payload or payload[field] is None:
        return None
    value = _string_value(payload[field], allow_blank=allow_blank)
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
    value = _string_value(payload[field], allow_blank=False)
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


def required_bool_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
) -> bool:
    if field not in payload:
        raise invalid_provider_payload(provider_type, field, "missing_required_field")
    value = payload[field]
    if not isinstance(value, bool):
        raise invalid_provider_payload(provider_type, field, "invalid_required_field")
    return value


def required_number_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
) -> int | float:
    if field not in payload:
        raise invalid_provider_payload(provider_type, field, "missing_required_field")
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise invalid_provider_payload(provider_type, field, "invalid_required_field")
    if isinstance(value, float) and not isfinite(value):
        raise invalid_provider_payload(provider_type, field, "invalid_required_field")
    return value


def required_mapping_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
) -> Mapping[str, object]:
    if field not in payload:
        raise invalid_provider_payload(provider_type, field, "missing_required_field")
    value = payload[field]
    if not isinstance(value, Mapping):
        raise invalid_provider_payload(provider_type, field, "invalid_required_field")
    return value


def invalid_provider_payload(
    provider_type: str,
    field: str,
    reason: str,
) -> ChannelReachabilityError:
    return ChannelReachabilityError(
        "invalid_provider_payload",
        fact={
            "type": "invalid_provider_payload",
            "provider_type": provider_type,
            "field": field,
            "reason": reason,
        },
    )


def _string_value(value: object, allow_blank: bool) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    if text:
        return text
    if allow_blank:
        return ""
    return None


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


def configured_http_client(
    http_client: httpx.Client | None,
    timeout: float,
) -> httpx.Client:
    return http_client or httpx.Client(timeout=timeout)


def missing_provider_config() -> DeliveryAttemptResult:
    return DeliveryAttemptResult(
        status="failed",
        provider_message_id=None,
        error_code="provider_not_configured",
        delivered_at=None,
    )


def post_json_send(
    *,
    provider_type: str,
    client: httpx.Client,
    url: str,
    headers: Mapping[str, str],
    body: Mapping[str, object],
) -> DeliveryAttemptResult:
    try:
        response = client.post(url, headers=dict(headers), json=dict(body))
    except httpx.HTTPError:
        return DeliveryAttemptResult(
            status="failed",
            provider_message_id=None,
            error_code="provider_network_error",
            delivered_at=None,
        )
    if not 200 <= response.status_code < 300:
        return DeliveryAttemptResult(
            status="failed",
            provider_message_id=None,
            error_code=extract_provider_error_code(response),
            delivered_at=None,
        )
    return DeliveryAttemptResult(
        status="sent",
        provider_message_id=extract_provider_message_id(response),
        error_code=None,
        delivered_at=None,
    )


def extract_provider_message_id(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    value = _first_string_at_paths(
        payload,
        (
            ("key", "id"),
            ("message", "key", "id"),
            ("data", "key", "id"),
            ("id",),
            ("messageId",),
            ("message_id",),
            ("msgId",),
            ("msg_id",),
        ),
    )
    return value


def extract_provider_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"provider_http_{response.status_code}"
    if not isinstance(payload, Mapping):
        return f"provider_http_{response.status_code}"
    error = _string_value(payload.get("error"), allow_blank=False)
    if error is None:
        return f"provider_http_{response.status_code}"
    ilink = payload.get("ilink")
    if isinstance(ilink, Mapping):
        ret = ilink.get("ret")
        errcode = ilink.get("errcode")
        if _error_number(ret):
            return _error_code(f"{error}_ret_{ret}")
        if _error_number(errcode):
            return _error_code(f"{error}_errcode_{errcode}")
    return _error_code(error)


def _error_number(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
    )


def _error_code(value: str) -> str:
    sanitized = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in value.strip()
    )
    return sanitized[:160] or "provider_error"


def _first_string_at_paths(
    payload: object, paths: Iterable[tuple[str, ...]]
) -> str | None:
    for path in paths:
        value: object = payload
        for part in path:
            if not isinstance(value, Mapping) or part not in value:
                value = None
                break
            value = value[part]
        if value is not None:
            text = _string_value(value, allow_blank=False)
            if text is not None:
                return text
    return None


def epoch_seconds_to_utc(value: int | float) -> datetime:
    return datetime.fromtimestamp(value, UTC)
