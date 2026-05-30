# Runtime-Readiness RR6 Google Calendar Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Replace the placeholder CalendarImport Google port adapter with a real Google Calendar v3 REST client that normalizes events into the existing `CalendarSourceEvent` contract.

**Architecture:** The adapter is an edge component for CalendarImport only: it resolves OAuth credentials from environment-backed handles, calls Google Calendar over REST, and returns domain event objects. CalendarImport service logic remains the owner of dedupe, historical skipping, downgrade classification, reminder creation, and revoke state persistence.

**Tech Stack:** Python, `google-auth` OAuth2 credentials, `httpx` direct REST calls, `python-dateutil` RRULE parsing, pytest unit tests with fake transports and no live network.

---

## File Structure

- Modify `coke/domains/calendar_import/google.py`: implement credential resolution, authorized HTTP calls, Google event normalization, recurrence parsing, pagination, and token revocation behind the existing port.
- Create `tests/unit/coke/calendar_import/test_google_calendar_client.py`: adapter unit tests with fake token resolution and fake HTTP client.
- Modify `requirements.txt` only if the implementation needs a dependency that is not already declared.
- Modify this plan file as each step completes; set `Plan Status` to `complete` only after full requested verification passes.

### Task 1: Adapter Contract Tests

**Files:**
- Create: `tests/unit/coke/calendar_import/test_google_calendar_client.py`

- [x] **Step 1: Write failing tests for event mapping and pagination**

Create tests that instantiate `GoogleCalendarClientAdapter` with a fake credential resolver and fake HTTP client. The fake list response should include a timed event, an all-day event, and a second paginated response with a recurring event:

```python
client = GoogleCalendarClientAdapter(
    token_resolver=lambda auth_handle: {"token": "access-token"},
    http_client=fake_http,
    now=lambda: NOW,
)
events = client.list_events("auth-handle", visible_start=NOW, visible_end=END)
assert fake_http.get_calls[0]["params"]["timeMin"] == NOW.isoformat().replace("+00:00", "Z")
assert fake_http.get_calls[0]["params"]["calendarId"] == "primary"
assert [event.source_event_id for event in events] == ["timed_1", "all_day_1", "recurring_1"]
assert events[0].start == datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
assert events[0].end == datetime(2026, 5, 31, 10, 30, tzinfo=UTC)
assert events[1].all_day is True
assert events[1].start == date(2026, 6, 1)
assert events[2].recurrence_rule == {"frequency": "weekly", "interval": 1}
assert events[2].recurrence_expressible is True
```

- [x] **Step 2: Write failing tests for recurrence downgrade occurrences**

Create a test where Google returns `RRULE:FREQ=WEEKLY;BYDAY=MO,WE` and assert the event is marked non-expressible, retains the raw recurrence rule, and includes visible future `CalendarOccurrence` objects with `recurrence_instance_key` values matching occurrence start times.

- [x] **Step 3: Write failing tests for revoke**

Create a test that calls `revoke_authorization("auth-handle")` and asserts the fake HTTP client receives `POST https://oauth2.googleapis.com/revoke` with the resolved token.

- [x] **Step 4: Run adapter tests to verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/calendar_import/test_google_calendar_client.py -v
```

Expected: FAIL because `GoogleCalendarClientAdapter` still raises `NotImplementedError` and does not issue REST calls.

### Task 2: Real Google Calendar Adapter

**Files:**
- Modify: `coke/domains/calendar_import/google.py`
- Modify: `requirements.txt` only if needed.

- [x] **Step 1: Implement credential resolution and authorized request headers**

Add a small token resolver that reads OAuth token data from environment, builds `google.oauth2.credentials.Credentials`, refreshes when needed with `google.auth.transport.requests.Request`, and applies bearer authorization to `httpx` requests. Supported env inputs:

```text
COKE_GOOGLE_CALENDAR_AUTH_TOKENS
COKE_GOOGLE_CALENDAR_TOKEN_JSON
COKE_GOOGLE_CALENDAR_REFRESH_TOKEN
COKE_GOOGLE_CALENDAR_CLIENT_ID
COKE_GOOGLE_CALENDAR_CLIENT_SECRET
COKE_GOOGLE_CALENDAR_TOKEN_URI
```

- [x] **Step 2: Implement paginated list_events REST calls**

Call `GET https://www.googleapis.com/calendar/v3/calendars/primary/events` with `timeMin`, `timeMax`, `singleEvents=false`, and `pageToken` until no `nextPageToken` remains. Do not send `orderBy=startTime` with `singleEvents=false`; Google only allows that ordering for expanded single events.

- [x] **Step 3: Implement event normalization**

Map Google event JSON to `CalendarSourceEvent`: `summary`, `description`, `start.dateTime` or `start.date`, `end.dateTime` or `end.date`, `recurrence`, `recurringEventId`, `originalStartTime`, `htmlLink`, `etag`, and raw metadata needed for service item evidence. Use date objects for all-day events and timezone-aware datetimes for timed events.

- [x] **Step 4: Implement recurrence parsing**

Translate simple Google RRULE frequencies into Coke recurrence dictionaries when they can be represented by Reminder recurrence support: `hourly`, `daily`, `weekly`, `monthly`, or `yearly` with interval only. For unsupported RRULE parts, retain `{"raw": ...}` and expand visible future occurrences with `dateutil.rrule` so the service can downgrade them occurrence-by-occurrence.

- [x] **Step 5: Implement revoke_authorization**

Resolve the token for the auth handle and call `POST https://oauth2.googleapis.com/revoke` with the token. Treat non-2xx responses as errors via the HTTP client.

- [x] **Step 6: Run adapter tests to verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/calendar_import/test_google_calendar_client.py -v
```

Expected: PASS.

### Task 3: Full Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr6-google-calendar.md`

- [x] **Step 1: Run requested full unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 2: Update plan status**

After full verification passes, mark all checkboxes complete and change:

```markdown
**Plan Status:** complete
```

- [x] **Step 3: Commit on the current branch**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr6-google-calendar.md coke/domains/calendar_import/google.py tests/unit/coke/calendar_import/test_google_calendar_client.py requirements.txt
git commit -m "feat: implement google calendar client"
```

Expected: one coherent RR6 commit on the current branch.
