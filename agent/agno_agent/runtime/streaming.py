from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def _event_name(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("event") or "")
    return str(getattr(event, "event", "") or "")


def _content(event: Any) -> str:
    if isinstance(event, dict):
        value = event.get("content")
    else:
        value = getattr(event, "content", None)
    return value if isinstance(value, str) else ""


def filter_user_visible_team_events(events: Iterable[Any]) -> Iterator[str]:
    for event in events:
        if _event_name(event) != "TeamRunContent":
            continue
        content = _content(event)
        if content:
            yield content
