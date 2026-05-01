from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

RuntimeVersion = Literal["legacy", "team"]

_VALID_RUNTIME_VERSIONS: set[str] = {"legacy", "team"}


@dataclass(frozen=True)
class RuntimeSelectionInput:
    explicit_override: str | None = None
    conversation_override: str | None = None
    customer_override: str | None = None
    env_value: str | None = None


def _normalize_runtime_version(value: str | None) -> RuntimeVersion | None:
    if value in _VALID_RUNTIME_VERSIONS:
        return value  # type: ignore[return-value]
    return None


def select_runtime(selection: RuntimeSelectionInput | None = None) -> RuntimeVersion:
    selection = selection or RuntimeSelectionInput()
    env_value = selection.env_value
    if env_value is None:
        env_value = os.environ.get("AGENT_RUNTIME_VERSION")

    for candidate in (
        selection.explicit_override,
        selection.conversation_override,
        selection.customer_override,
        env_value,
    ):
        runtime_version = _normalize_runtime_version(candidate)
        if runtime_version is not None:
            return runtime_version

    return "legacy"
