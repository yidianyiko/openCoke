from __future__ import annotations

import re
import secrets
import uuid
from collections.abc import Callable

from opentelemetry import trace


_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-"
    r"(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-"
    r"(?P<trace_flags>[0-9a-f]{2})$"
)


def is_valid_traceparent(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    match = _TRACEPARENT_RE.fullmatch(value)
    if match is None:
        return False
    if match.group("version") == "ff":
        return False
    if match.group("trace_id") == "0" * 32:
        return False
    if match.group("span_id") == "0" * 16:
        return False
    return True


def extract_trace_id(traceparent: str) -> str:
    match = _TRACEPARENT_RE.fullmatch(traceparent)
    if match is None or not is_valid_traceparent(traceparent):
        raise ValueError("Invalid W3C traceparent")
    return match.group("trace_id")


def _nonzero_hex(producer: Callable[[], str], zero_value: str) -> str:
    while True:
        value = producer()
        if value != zero_value:
            return value


def _new_trace_id() -> str:
    return _nonzero_hex(lambda: uuid.uuid4().hex, "0" * 32)


def _new_span_id() -> str:
    return _nonzero_hex(lambda: secrets.token_hex(8), "0" * 16)


def generate_traceparent(sampled: bool = True) -> str:
    trace_id = _new_trace_id()
    span_id = _new_span_id()
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def ensure_traceparent(traceparent: str | None) -> str:
    if traceparent is None:
        return generate_traceparent()
    if not is_valid_traceparent(traceparent):
        raise ValueError("Invalid W3C traceparent")
    return traceparent


def get_tracer(name: str = "coke"):
    return trace.get_tracer(name)
