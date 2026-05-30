from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from coke.domains.calendar_import.google import GoogleCalendarClientAdapter

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
END = NOW + timedelta(days=14)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, list_pages: list[dict] | None = None) -> None:
        self.list_pages = list(list_pages or [])
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def get(self, url: str, *, params: dict, headers: dict) -> FakeResponse:
        self.get_calls.append(
            {"url": url, "params": dict(params), "headers": dict(headers)}
        )
        return FakeResponse(self.list_pages.pop(0))

    def post(self, url: str, *, data: dict, headers: dict) -> FakeResponse:
        self.post_calls.append(
            {"url": url, "data": dict(data), "headers": dict(headers)}
        )
        return FakeResponse({})


def client(fake_http: FakeHttpClient) -> GoogleCalendarClientAdapter:
    return GoogleCalendarClientAdapter(
        token_resolver=lambda auth_handle: {"token": f"token-for-{auth_handle}"},
        http_client=fake_http,
        now=lambda: NOW,
    )


def test_list_events_maps_timed_all_day_and_recurring_events_with_pagination():
    fake_http = FakeHttpClient(
        [
            {
                "nextPageToken": "page-2",
                "items": [
                    {
                        "id": "timed_1",
                        "summary": "Planning",
                        "description": "Discuss launch",
                        "etag": '"timed-etag"',
                        "htmlLink": "https://calendar.google/timed",
                        "start": {"dateTime": "2026-05-31T09:00:00Z"},
                        "end": {"dateTime": "2026-05-31T10:30:00Z"},
                    },
                    {
                        "id": "all_day_1",
                        "summary": "Holiday",
                        "start": {"date": "2026-06-01"},
                        "end": {"date": "2026-06-02"},
                    },
                ],
            },
            {
                "items": [
                    {
                        "id": "recurring_1",
                        "summary": "Weekly sync",
                        "start": {"dateTime": "2026-06-02T15:00:00+09:00"},
                        "end": {"dateTime": "2026-06-02T15:30:00+09:00"},
                        "recurrence": ["RRULE:FREQ=WEEKLY;INTERVAL=1"],
                    }
                ]
            },
        ]
    )

    events = client(fake_http).list_events("auth-handle", NOW, END)

    assert len(fake_http.get_calls) == 2
    first_params = fake_http.get_calls[0]["params"]
    second_params = fake_http.get_calls[1]["params"]
    assert fake_http.get_calls[0]["url"].endswith("/calendars/primary/events")
    assert first_params["calendarId"] == "primary"
    assert first_params["timeMin"] == "2026-05-30T12:00:00Z"
    assert first_params["timeMax"] == "2026-06-13T12:00:00Z"
    assert first_params["singleEvents"] == "false"
    assert "orderBy" not in first_params
    assert second_params["pageToken"] == "page-2"
    assert (
        fake_http.get_calls[0]["headers"]["Authorization"]
        == "Bearer token-for-auth-handle"
    )

    assert [event.source_event_id for event in events] == [
        "timed_1",
        "all_day_1",
        "recurring_1",
    ]
    assert events[0].provider_calendar_id == "primary"
    assert events[0].title == "Planning"
    assert events[0].description == "Discuss launch"
    assert events[0].start == datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    assert events[0].end == datetime(2026, 5, 31, 10, 30, tzinfo=UTC)
    assert events[0].all_day is False
    assert events[0].source_metadata["htmlLink"] == "https://calendar.google/timed"

    assert events[1].title == "Holiday"
    assert events[1].start == date(2026, 6, 1)
    assert events[1].end == date(2026, 6, 2)
    assert events[1].all_day is True

    assert events[2].recurrence_rule == {"frequency": "weekly", "interval": 1}
    assert events[2].recurrence_expressible is True
    assert events[2].occurrences == []


def test_unsupported_recurrence_expands_visible_future_occurrences_for_downgrade():
    fake_http = FakeHttpClient(
        [
            {
                "items": [
                    {
                        "id": "unsupported_recurrence",
                        "summary": "Gym",
                        "start": {"dateTime": "2026-06-01T09:00:00Z"},
                        "end": {"dateTime": "2026-06-01T10:00:00Z"},
                        "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"],
                    }
                ]
            }
        ]
    )

    events = client(fake_http).list_events("auth-handle", NOW, END)

    assert len(events) == 1
    event = events[0]
    assert event.recurrence_rule == {"raw": "RRULE:FREQ=WEEKLY;BYDAY=MO,WE"}
    assert event.recurrence_expressible is False
    assert [occurrence.recurrence_instance_key for occurrence in event.occurrences] == [
        "2026-06-01T09:00:00+00:00",
        "2026-06-03T09:00:00+00:00",
        "2026-06-08T09:00:00+00:00",
        "2026-06-10T09:00:00+00:00",
    ]
    assert event.occurrences[0].start == datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    assert event.occurrences[0].end == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


def test_revoke_authorization_posts_resolved_token_to_google_revoke_endpoint():
    fake_http = FakeHttpClient()

    client(fake_http).revoke_authorization("auth-handle")

    assert fake_http.post_calls == [
        {
            "url": "https://oauth2.googleapis.com/revoke",
            "data": {"token": "token-for-auth-handle"},
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        }
    ]
