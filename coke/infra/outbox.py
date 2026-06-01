from __future__ import annotations

import math
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from coke.infra.tracing import is_valid_traceparent

JSONPrimitive = str | int | float | bool | None
JSONLike = JSONPrimitive | Mapping[str, Any] | list[Any]


def _freeze_payload(value: Any, path: str = "payload") -> Any:
    if isinstance(value, MappingABC):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            frozen[key] = _freeze_payload(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(
            _freeze_payload(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise TypeError(f"{path} must be JSON-like")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"{path} must be JSON-like")


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: str
    topic: str
    idempotency_key: str
    payload: Mapping[str, JSONLike]
    traceparent: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self._require_nonblank("id", self.id)
        self._require_nonblank("topic", self.topic)
        self._require_nonblank("idempotency_key", self.idempotency_key)

        if not is_valid_traceparent(self.traceparent):
            raise ValueError("traceparent must be a valid W3C traceparent")
        if self.created_at.tzinfo is None or self.created_at.strftime("%z") == "":
            raise ValueError("created_at must be timezone-aware")
        if not isinstance(self.payload, MappingABC):
            raise TypeError("payload must be a JSON object mapping")

        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "topic", self.topic.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        object.__setattr__(self, "payload", _freeze_payload(self.payload))

    @staticmethod
    def _require_nonblank(field_name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be blank")
