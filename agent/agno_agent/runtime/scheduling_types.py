from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class SharedReminderSchedulingArgs(BaseModel):
    target_account_id: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    receiver_account_id: str | None = None
    receiver_name: str | None = None
    friend_account_id: str | None = None
    title: str | None = None
    fire_at: str | None = None
    duration_minutes: int | None = None
    timezone: str | None = None
    shared_reminder_id: str | None = None
    status: str | None = None
    friend_name: str | None = None
    requester_name: str | None = None
    friendship_id: str | None = None
    user_link_code: str | None = None
    message: str | None = None
    idempotency_key: str | None = None


def _compact_scheduling_args(args: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in args.items():
        if value is None or value == "":
            continue
        out[key] = value.model_dump() if isinstance(value, BaseModel) else value
    return out
