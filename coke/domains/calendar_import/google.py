from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
from dateutil.rrule import rrulestr
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from coke.domains.calendar_import.models import (
    CalendarImportError,
    CalendarOccurrence,
    CalendarSourceEvent,
)

GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GOOGLE_CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
)
GOOGLE_OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
SUPPORTED_RECURRENCE_FREQUENCIES = {
    "HOURLY": "hourly",
    "DAILY": "daily",
    "WEEKLY": "weekly",
    "MONTHLY": "monthly",
    "YEARLY": "yearly",
}

TokenInfo = Mapping[str, Any] | str
TokenResolver = Callable[[str], TokenInfo]


class GoogleCalendarClientPort(Protocol):
    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]: ...

    def revoke_authorization(self, auth_handle: str) -> None: ...


class GoogleCalendarClientAdapter:
    def __init__(
        self,
        *,
        token_resolver: TokenResolver | None = None,
        http_client: Any | None = None,
        now: Callable[[], datetime] | None = None,
        calendar_id: str = "primary",
    ) -> None:
        self.token_resolver = token_resolver or resolve_google_calendar_token
        self.http_client = http_client or httpx.Client(timeout=15.0)
        self._now = now or (lambda: datetime.now(UTC))
        self.calendar_id = calendar_id
        self._google_auth_request = Request()

    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]:
        self._require_aware(visible_start, "visible_start")
        self._require_aware(visible_end, "visible_end")
        time_min = max(visible_start, self._now())
        url = GOOGLE_CALENDAR_EVENTS_URL.format(calendar_id=self.calendar_id)
        headers = self._authorized_headers(auth_handle, "GET", url)
        params: dict[str, str] = {
            "calendarId": self.calendar_id,
            "timeMin": _google_timestamp(time_min),
            "timeMax": _google_timestamp(visible_end),
            "singleEvents": "false",
            "maxResults": "2500",
        }

        events: list[CalendarSourceEvent] = []
        page_token: str | None = None
        while True:
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token
            response = self.http_client.get(url, params=page_params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("items", []):
                event = self._source_event(item, visible_start, visible_end)
                if event is not None:
                    events.append(event)
            page_token = payload.get("nextPageToken")
            if not page_token:
                return events

    def revoke_authorization(self, auth_handle: str) -> None:
        credentials = self._credentials(auth_handle)
        if not credentials.token:
            credentials.refresh(self._google_auth_request)
        response = self.http_client.post(
            GOOGLE_OAUTH_REVOKE_URL,
            data={"token": credentials.token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

    def _source_event(
        self,
        item: Mapping[str, Any],
        visible_start: datetime,
        visible_end: datetime,
    ) -> CalendarSourceEvent | None:
        if item.get("status") == "cancelled":
            return None
        source_event_id = str(item.get("id") or "").strip()
        if not source_event_id:
            return None

        start, all_day = _parse_google_event_time(item.get("start") or {})
        end, _end_all_day = _parse_google_event_time(item.get("end") or {})
        recurrence_lines = [
            str(line)
            for line in item.get("recurrence", [])
            if str(line).startswith("RRULE:")
        ]
        recurrence_rule, expressible = _recurrence_rule(recurrence_lines)
        occurrences: list[CalendarOccurrence] = []
        if recurrence_rule and not expressible:
            occurrences = _expanded_occurrences(
                recurrence_lines=recurrence_lines,
                start=start,
                end=end,
                all_day=all_day,
                visible_start=visible_start,
                visible_end=visible_end,
            )

        return CalendarSourceEvent(
            provider_calendar_id=self.calendar_id,
            source_event_id=source_event_id,
            title=str(item.get("summary") or ""),
            description=str(item.get("description") or ""),
            start=start,
            end=end,
            all_day=all_day,
            recurrence_rule=recurrence_rule,
            recurrence_expressible=expressible,
            occurrences=occurrences,
            source_metadata=_source_metadata(item, self.calendar_id),
        )

    def _authorized_headers(
        self, auth_handle: str, method: str, url: str
    ) -> dict[str, str]:
        credentials = self._credentials(auth_handle)
        headers: dict[str, str] = {}
        credentials.before_request(self._google_auth_request, method, url, headers)
        if "authorization" in headers:
            headers["Authorization"] = headers.pop("authorization")
        return headers

    def _credentials(self, auth_handle: str) -> Credentials:
        return _credentials_from_token_info(self.token_resolver(auth_handle))

    def _require_aware(self, value: datetime, field: str) -> None:
        if value.tzinfo is None:
            raise CalendarImportError(
                "invalid_request",
                fact={"type": "invalid_request", "field": field},
            )


def resolve_google_calendar_token(auth_handle: str) -> TokenInfo:
    if auth_handle.startswith("env:"):
        return _env_json(auth_handle.removeprefix("env:"))

    token_map = os.environ.get("COKE_GOOGLE_CALENDAR_AUTH_TOKENS")
    if token_map:
        tokens = json.loads(token_map)
        if auth_handle not in tokens:
            raise CalendarImportError(
                "google_calendar_credentials_missing",
                fact={"type": "google_calendar_credentials_missing"},
            )
        return tokens[auth_handle]

    token_json = os.environ.get("COKE_GOOGLE_CALENDAR_TOKEN_JSON")
    if token_json:
        return token_json

    refresh_token = os.environ.get("COKE_GOOGLE_CALENDAR_REFRESH_TOKEN")
    if refresh_token:
        return {
            "refresh_token": refresh_token,
            "client_id": os.environ.get("COKE_GOOGLE_CALENDAR_CLIENT_ID"),
            "client_secret": os.environ.get("COKE_GOOGLE_CALENDAR_CLIENT_SECRET"),
            "token_uri": os.environ.get(
                "COKE_GOOGLE_CALENDAR_TOKEN_URI", GOOGLE_OAUTH_TOKEN_URI
            ),
        }

    raise CalendarImportError(
        "google_calendar_credentials_missing",
        fact={"type": "google_calendar_credentials_missing"},
    )


def _env_json(name: str) -> TokenInfo:
    value = os.environ.get(name)
    if value is None:
        raise CalendarImportError(
            "google_calendar_credentials_missing",
            fact={"type": "google_calendar_credentials_missing", "env": name},
        )
    return value


def _credentials_from_token_info(token_info: TokenInfo) -> Credentials:
    info = json.loads(token_info) if isinstance(token_info, str) else dict(token_info)
    if not info.get("client_id"):
        info["client_id"] = os.environ.get("COKE_GOOGLE_CALENDAR_CLIENT_ID")
    if not info.get("client_secret"):
        info["client_secret"] = os.environ.get("COKE_GOOGLE_CALENDAR_CLIENT_SECRET")
    info.setdefault(
        "token_uri",
        os.environ.get("COKE_GOOGLE_CALENDAR_TOKEN_URI", GOOGLE_OAUTH_TOKEN_URI),
    )

    return Credentials(
        token=info.get("token"),
        refresh_token=info.get("refresh_token"),
        token_uri=info.get("token_uri"),
        client_id=info.get("client_id"),
        client_secret=info.get("client_secret"),
        scopes=info.get("scopes") or [GOOGLE_CALENDAR_READONLY_SCOPE],
    )


def _parse_google_event_time(value: Mapping[str, Any]) -> tuple[datetime | date, bool]:
    if value.get("date"):
        return date.fromisoformat(str(value["date"])), True
    date_time = str(value.get("dateTime") or "")
    if not date_time:
        raise CalendarImportError(
            "invalid_calendar_event",
            fact={"type": "invalid_calendar_event", "field": "start"},
        )
    parsed = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        timezone_name = value.get("timeZone")
        if not timezone_name:
            raise CalendarImportError(
                "invalid_calendar_event",
                fact={"type": "invalid_calendar_event", "field": "dateTime"},
            )
        parsed = parsed.replace(tzinfo=ZoneInfo(str(timezone_name)))
    return parsed, False


def _recurrence_rule(recurrence_lines: list[str]) -> tuple[dict[str, Any], bool]:
    if len(recurrence_lines) != 1:
        return (
            ({}, False) if not recurrence_lines else ({"raw": recurrence_lines}, False)
        )
    raw = recurrence_lines[0]
    parts = _rrule_parts(raw)
    frequency = parts.get("FREQ")
    interval = int(parts.get("INTERVAL", "1"))
    allowed_keys = {"FREQ", "INTERVAL"}
    if (
        frequency in SUPPORTED_RECURRENCE_FREQUENCIES
        and interval >= 1
        and set(parts).issubset(allowed_keys)
    ):
        return (
            {
                "frequency": SUPPORTED_RECURRENCE_FREQUENCIES[frequency],
                "interval": interval,
            },
            True,
        )
    return ({"raw": raw}, False)


def _rrule_parts(raw: str) -> dict[str, str]:
    body = raw.removeprefix("RRULE:")
    parts: dict[str, str] = {}
    for chunk in body.split(";"):
        if not chunk:
            continue
        key, separator, value = chunk.partition("=")
        if separator:
            parts[key.upper()] = value.upper()
    return parts


def _expanded_occurrences(
    *,
    recurrence_lines: list[str],
    start: datetime | date,
    end: datetime | date | None,
    all_day: bool,
    visible_start: datetime,
    visible_end: datetime,
) -> list[CalendarOccurrence]:
    if not recurrence_lines:
        return []
    duration = _duration(start, end)
    dtstart = _as_datetime(start)
    rule = rrulestr(recurrence_lines[0], dtstart=dtstart)
    occurrences: list[CalendarOccurrence] = []
    for occurrence_start in rule.between(visible_start, visible_end, inc=True):
        if occurrence_start.tzinfo is None:
            occurrence_start = occurrence_start.replace(tzinfo=dtstart.tzinfo)
        occurrence_end = occurrence_start + duration if duration is not None else None
        normalized_start: datetime | date = (
            occurrence_start.date() if all_day else occurrence_start
        )
        normalized_end: datetime | date | None = (
            occurrence_end.date() if all_day and occurrence_end else occurrence_end
        )
        key = occurrence_start.isoformat()
        occurrences.append(
            CalendarOccurrence(
                recurrence_instance_key=key,
                start=normalized_start,
                end=normalized_end,
                all_day=all_day,
                source_metadata={"recurrence_instance_key": key},
            )
        )
    return occurrences


def _duration(start: datetime | date, end: datetime | date | None) -> timedelta | None:
    if end is None:
        return None
    return _as_datetime(end) - _as_datetime(start)


def _as_datetime(value: datetime | date) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time(0, 0), tzinfo=UTC)


def _source_metadata(item: Mapping[str, Any], calendar_id: str) -> dict[str, Any]:
    return {
        "provider": "google_calendar",
        "calendar_id": calendar_id,
        "etag": item.get("etag"),
        "htmlLink": item.get("htmlLink"),
        "status": item.get("status"),
        "recurrence": list(item.get("recurrence", [])),
        "recurringEventId": item.get("recurringEventId"),
        "originalStartTime": item.get("originalStartTime"),
        "google_start": item.get("start"),
        "google_end": item.get("end"),
    }


def _google_timestamp(value: datetime) -> str:
    timestamp = value.astimezone(UTC).isoformat()
    return timestamp.replace("+00:00", "Z")
