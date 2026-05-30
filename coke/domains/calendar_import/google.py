from __future__ import annotations

from datetime import datetime
from typing import Protocol

from coke.domains.calendar_import.models import CalendarSourceEvent


class GoogleCalendarClientPort(Protocol):
    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]: ...

    def revoke_authorization(self, auth_handle: str) -> None: ...


class GoogleCalendarClientAdapter:
    """Thin adapter shape for a future Google API client wiring."""

    def __init__(self, api_client) -> None:
        self.api_client = api_client

    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]:
        raise NotImplementedError("google_calendar_api_wiring_required")

    def revoke_authorization(self, auth_handle: str) -> None:
        revoke = getattr(self.api_client, "revoke_authorization", None)
        if revoke is not None:
            revoke(auth_handle)
