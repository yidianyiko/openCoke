from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

LOGGER = logging.getLogger(__name__)

SAFE_EXTRA_FIELDS = frozenset(
    {
        "account_id",
        "conversation_id",
        "duration_ms",
        "error_type",
        "event_name",
        "message_count",
        "mode",
        "model",
        "model_provider",
        "model_role",
        "phase",
        "retry_attempt",
        "action",
        "route",
        "status",
        "timeout",
        "tool_count",
        "trigger_type",
        "turn_id",
    }
)


@contextmanager
def turn_latency_span(
    phase: str,
    *,
    turn_id: str | None = None,
    trigger_type: str | None = None,
    mode: Any | None = None,
    account_id: str | None = None,
    conversation_id: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
    extra: Mapping[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    start = clock()
    base = {
        "phase": phase,
        "turn_id": turn_id,
        "trigger_type": trigger_type,
        "mode": str(mode) if mode is not None else None,
        "account_id": account_id,
        "conversation_id": conversation_id,
    }
    if extra:
        base.update(dict(extra))
    try:
        yield base
    except Exception as error:
        _log_event(
            base,
            clock() - start,
            status="error",
            error_type=type(error).__name__,
        )
        raise
    else:
        _log_event(base, clock() - start, status="ok")


def log_turn_latency_event(
    phase: str,
    *,
    duration_seconds: float,
    status: str,
    turn_id: str | None = None,
    trigger_type: str | None = None,
    mode: Any | None = None,
    account_id: str | None = None,
    conversation_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    base = {
        "phase": phase,
        "turn_id": turn_id,
        "trigger_type": trigger_type,
        "mode": str(mode) if mode is not None else None,
        "account_id": account_id,
        "conversation_id": conversation_id,
    }
    if extra:
        base.update(dict(extra))
    _log_event(base, duration_seconds, status=status)


def _log_event(
    fields: Mapping[str, Any],
    duration_seconds: float,
    *,
    status: str,
    error_type: str | None = None,
) -> None:
    payload = {
        key: value
        for key, value in fields.items()
        if key in SAFE_EXTRA_FIELDS and value is not None
    }
    payload["duration_ms"] = max(0, int(round(duration_seconds * 1000)))
    payload["status"] = status
    payload["event_name"] = "turn_latency_event"
    if error_type is not None:
        payload["error_type"] = error_type
    LOGGER.info(
        "turn_latency_event %s",
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
        extra=payload,
    )
