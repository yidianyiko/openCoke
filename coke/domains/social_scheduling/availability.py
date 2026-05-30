from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from coke.domains.social_scheduling.models import SocialSchedulingError


class ReminderAvailabilityPort(Protocol):
    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list["BusyInterval"]: ...


class ParticipantReachabilityPort(Protocol):
    def has_usable_channel(self, account_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class BusyInterval:
    account_id: str
    start: datetime
    end: datetime
    source: Literal["personal", "shared"]
    detail_id: str | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityQuery:
    friend_ids: tuple[str, ...]
    local_start: datetime
    local_end: datetime
    requester_timezone: str


@dataclass(frozen=True, slots=True)
class AvailabilityWindow:
    start: datetime
    end: datetime
    state: Literal["busy", "free"]

    def to_public_dict(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class FriendAvailability:
    friend_account_id: str
    windows: list[AvailabilityWindow]


def build_busy_free_windows(
    start: datetime,
    end: datetime,
    busy_intervals: list[BusyInterval],
) -> list[AvailabilityWindow]:
    if end <= start:
        raise SocialSchedulingError(
            "invalid_availability_range",
            fact={"type": "invalid_availability_range"},
        )
    clipped = sorted(
        (
            BusyInterval(
                account_id=interval.account_id,
                start=max(start, interval.start),
                end=min(end, interval.end),
                source=interval.source,
                detail_id=None,
            )
            for interval in busy_intervals
            if interval.start < end and interval.end > start
        ),
        key=lambda interval: (interval.start, interval.end),
    )
    merged: list[tuple[datetime, datetime]] = []
    for interval in clipped:
        if not merged or interval.start > merged[-1][1]:
            merged.append((interval.start, interval.end))
        elif interval.end > merged[-1][1]:
            merged[-1] = (merged[-1][0], interval.end)

    windows: list[AvailabilityWindow] = []
    cursor = start
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            windows.append(
                AvailabilityWindow(start=cursor, end=busy_start, state="free")
            )
        windows.append(AvailabilityWindow(start=busy_start, end=busy_end, state="busy"))
        cursor = max(cursor, busy_end)
    if cursor < end:
        windows.append(AvailabilityWindow(start=cursor, end=end, state="free"))
    return windows
