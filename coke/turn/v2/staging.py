from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any


def json_safe(value: Any) -> Any:
    """Convert a value tree to a JSON-serializable form for staged commands.

    Staged command payloads are JSON-serialized for storage and re-parsed by the
    shared materializer, which (matching the legacy path) expects datetimes as ISO
    strings. Raw datetime objects fail JSON serialization, so normalize them here.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
