from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class SchedulingBookableWindowRule(BaseModel):
    type: str
    days_of_week: list[int] | None = None
    time_start: str | None = None
    time_end: str | None = None
    timezone: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    date: str | None = None


class SchedulingBookableWindowPreviewItem(BaseModel):
    rule: SchedulingBookableWindowRule
    fingerprint: str


class SchedulingBookableWindowPreview(BaseModel):
    previewId: str
    windows: list[SchedulingBookableWindowPreviewItem]


def _compact_scheduling_args(args: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in args.items():
        if value is None or value == "":
            continue
        out[key] = value.model_dump() if isinstance(value, BaseModel) else value
    return out
