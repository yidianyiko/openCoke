from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, TypeVar, cast

_T = TypeVar("_T")


def freeze_value(value: _T) -> _T:
    if isinstance(value, Mapping):
        return cast(_T, freeze_mapping(value))
    if isinstance(value, tuple):
        return cast(_T, tuple(freeze_value(item) for item in value))
    if isinstance(value, list):
        return cast(_T, tuple(freeze_value(item) for item in value))
    if isinstance(value, set):
        return cast(_T, frozenset(freeze_value(item) for item in value))
    return value


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: freeze_value(item) for key, item in value.items()})


def freeze_sequence(value: Sequence[_T]) -> tuple[_T, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError(
            "freeze_sequence() rejects str, bytes, or bytearray inputs; "
            "pass a list or tuple instead"
        )
    return tuple(freeze_value(item) for item in value)
