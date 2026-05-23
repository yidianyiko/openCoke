# Reminder Calendar Friend Booking Design

## Plain-Language Product Story

A fitness coach uses Coke as their agent and calendar. The coach's reminders
are the source of truth for their schedule. When the coach shares a friend link
with a student, the student can become the coach's friend and then ask the
coach's agent questions such as:

- "What free time does Coach A have this week?"
- "Can I book a lesson with Coach A tomorrow morning?"
- "Let's do a class at 10 on Tuesday."

The agent answers from Coke reminders, not from Google Calendar or any other
third-party calendar. The agent may use product common sense from prompts, such
as treating "a class" in the fitness coach scenario as 60 minutes unless the
conversation says otherwise. The backend exposes facts and records outcomes;
the LLM owns the scheduling reasoning.

## Goal

Enable LLM-driven lesson booking between friends using Coke reminders as the
calendar system:

- reminders can represent occupied time intervals, not only point-in-time
  notifications
- a user can query an active friend's reminder-derived calendar facts
- the agent can use those facts to describe free time and propose or create a
  shared reminder for a lesson
- the system keeps friend-link and friend-state access boundaries intact
- backend code does not become a booking rule engine

## Non-Goals

- Do not integrate Google Calendar free/busy for this feature.
- Do not reintroduce the retired appointment-only models such as
  `BookableWindow`, `ServiceLink`, or `AppointmentRequest`.
- Do not add backend slot cutting, class-duration defaults, course-type
  selection, or conflict-decision logic.
- Do not require A to maintain separate "available windows" outside reminders.
- Do not expose A's reminder titles, prompts, locations, participants, or
  private metadata to B when B asks for free time.
- Do not add a web booking UI in this slice.

## Product Rules

### Reminder As Calendar Event

A visible reminder may optionally occupy a time interval. The reminder's
existing schedule remains the start of the event. A new duration field records
how long the reminder blocks the owner's calendar.

Rules:

- no duration means the reminder is a point reminder
- point reminders still appear in normal reminder lists
- point reminders do not block an interval unless the LLM chooses to treat them
  as context in conversation
- a positive duration means the reminder blocks
  `[schedule.anchor_at, schedule.anchor_at + duration]`
- recurring reminders block each occurrence in the requested date range

The durable field should be explicit, not inferred from title text. The
preferred shape is `schedule.duration_minutes` in MongoDB and
`durationMinutes` in JSON/API responses.

### Friend Availability

Only active friends may ask about each other's availability. If B asks about A
and A is not an active friend, the agent should explain that B needs to add A
as a friend first.

If the target friend is ambiguous, the agent asks B to choose the friend. It
does not pick a friend by guess.

The default query range is the next 7 days when B does not provide a range.
The user-visible agent response should expose free intervals only. It must not
reveal the names or contents of A's reminders.

### LLM Owns Booking Reasoning

The LLM decides how to interpret natural booking language:

- "a class" in the fitness-coach scenario defaults to 60 minutes through prompt
  policy
- explicit user wording overrides the prompt default, for example "30 minute
  trial" or "90 minute session"
- the LLM can decide whether a point reminder matters conversationally
- the LLM can ask follow-up questions when the requested time, friend, duration,
  or intent is unclear

The backend must not implement class-duration defaults, slot recommendations,
or conflict-decision policy. It may provide facts the LLM can reason over:
friend list, query ranges, busy intervals, and shared-reminder state.

### Shared Reminder Creation

After B chooses a time, the agent creates a shared reminder request between B
and A. The request should carry enough timing information for both users'
reminder calendars:

- start time
- duration or end time
- timezone
- title
- requester and invitee

A still confirms the shared reminder request before it becomes accepted. Until
accepted, it remains pending. The LLM owns the conversational explanation of
pending vs accepted state.

## Current System Fit

Already present:

- friend links, friend requests, active friendships, blocks
- scheduling tools for user link, friend requests, friends, and shared
  reminders
- Reminder Runtime as the visible reminder calendar store
- owner-scoped reminder listing by local date range
- shared reminder projections into each user's reminder runtime

Missing:

- reminder duration/occupied-time field
- API/service serialization for reminder duration
- a scheduling tool that returns a friend's reminder-derived busy intervals
- shared reminder request timing that can represent a lesson interval rather
  than only a single `fireAt`
- occurrence expansion for recurring reminders in bounded calendar-fact reads
- prompt policy for LLM-driven friend availability and lesson booking
- tests/evals for the agent behavior around friend ambiguity, default 7-day
  range, 60-minute fitness lesson default, and privacy-preserving availability
  answers

## Architecture

### Reminder Runtime

Reminder Runtime remains the calendar owner. It stores visible reminders in
MongoDB. The runtime gains optional occupied-duration support on reminder
schedules and serializes it through the existing bridge reminder management
service.

This is not a separate booking database.

### Gateway Scheduling

Gateway remains the owner of friend relationships and shared reminder request
state. It exposes an internal scheduling tool named
`list_friend_calendar_facts`.

The tool should:

- authenticate the caller as the current customer
- require an active friendship with the target account
- call the Reminder Runtime/bridge path to list the target friend's visible
  reminders for the requested local date range
- convert occupied reminders into busy intervals
- return busy intervals plus minimal range metadata needed by the LLM
- omit private reminder details

The conversion from reminders to busy intervals is fact extraction. It is not
booking policy. It should not decide whether a lesson is allowed, should not
cut slots, and should not return recommended free times. The LLM subtracts the
busy intervals from the requested range and decides how to describe free time
to the user.

### Agent Runtime

The Interaction Agent keeps using `scheduling_domain(intent=...)` for friend
and shared-reminder work. Scheduling execution gains a tool for friend
availability. Prompt policy teaches the agent:

- reminders are Coke's calendar
- do not use Google Calendar for friend availability
- when no range is given, use the next 7 local calendar days as the query range
- in a fitness-coach booking context, treat "a class/lesson/session" as 60
  minutes unless the user says another duration
- if the friend is ambiguous, ask the user to choose
- never reveal the friend's reminder details, only available time

The agent owns friend-name resolution before writes. It can call `list_friends`
to get the current user's active friends. If exactly one active friend matches
the user's wording, it can pass that friend's account id to
`list_friend_calendar_facts`. If more than one friend matches, it asks the user
to choose. If no friend matches, it explains that the person must be added as a
friend first.

## Data Shape

### Reminder Schedule

Add optional duration:

```json
{
  "schedule": {
    "anchorAt": "2026-05-25T01:00:00Z",
    "localDate": "2026-05-25",
    "localTime": "10:00:00",
    "timezone": "Asia/Tokyo",
    "rrule": null,
    "durationMinutes": 60
  }
}
```

Storage may use `schedule.duration_minutes`; API responses use
`durationMinutes`.

### Friend Calendar Facts Tool Request

The scheduling tool accepts explicit request fields. The agent should provide
them after resolving the target friend and query range:

```json
{
  "target_account_id": "acct_coach",
  "from_date": "2026-05-25",
  "to_date": "2026-05-31",
  "timezone": "Asia/Tokyo"
}
```

Field rules:

- `target_account_id` is required by the tool. The agent obtains it from active
  friend state; the tool does not perform natural-language friend matching.
- `from_date` and `to_date` are local dates. When the user gives no range, the
  agent supplies the next 7 local calendar days.
- `timezone` is the timezone used to interpret local date boundaries. The agent
  should use the target friend's timezone when available, otherwise the current
  conversation timezone.
- the query universe is the full local day range:
  `[from_date 00:00, day_after_to_date 00:00)`.

This default range is an access/query default, not a booking policy. It does
not decide lesson duration or whether any interval is suitable for a class.

### Friend Calendar Facts Tool Result

The tool returns calendar facts, not final booking decisions:

```json
{
  "target_account_id": "acct_coach",
  "range": {
    "from": "2026-05-25",
    "to": "2026-05-31",
    "timezone": "Asia/Tokyo"
  },
  "busy_intervals": [
    {
      "start_at": "2026-05-25T01:00:00Z",
      "end_at": "2026-05-25T03:00:00Z",
      "local_start": "2026-05-25 10:00",
      "local_end": "2026-05-25 12:00"
    }
  ],
  "privacy": {
    "event_details_included": false
  }
}
```

The result intentionally does not include reminder ids, titles, prompts,
metadata, or output targets. The LLM may calculate and present free intervals
from `range` minus `busy_intervals`.

### Shared Reminder Timing

Shared reminders should carry interval timing. The preferred durable extension
is to add `durationMinutes` to shared reminder requests and to write the same
duration into requester/invitee reminder projections.

The existing `fireAt` remains the start time.

The backend should persist the interval the LLM chose. It should keep existing
identity and friendship checks, but it must not reject the request because of
overlap, insufficient free time, or course suitability. Those are LLM-owned
conversation decisions for this product direction.

### Recurring Reminder Occurrences

Calendar-fact reads must not assume the current date-range reminder list already
expands recurrences. For this feature, the implementation needs a bounded
occurrence-expansion path for visible reminders with `rrule`.

Rules:

- expand only within the requested local date range
- preserve owner and visibility filtering before returning any facts
- return occupied intervals for each occurrence that has a positive duration
- do not expose the source recurring reminder's title or metadata
- keep the expansion bounded by the same maximum date-range limits as reminder
  listing

## Privacy And Access

The system may expose that A is free or busy during ranges. It must not expose
why A is busy.

Allowed to B:

- free intervals computed by the LLM from privacy-preserving busy facts
- the target friend's display name or account identifier already visible
  through friendship state
- whether the request is pending, accepted, rejected, cancelled, expired, or
  invalidated

Not allowed to B:

- A's reminder title
- A's reminder prompt
- A's reminder metadata
- A's reminder conversation target
- internal reminders
- reminder ids for A's reminders

## Error Handling

- No active friendship: return a structured `friendship_required` result.
- Ambiguous friend name: agent asks B to choose before calling an availability
  read or shared-reminder write tool.
- Missing duration in a booking request: agent uses prompt policy if the
  domain context is clear; otherwise it asks a follow-up question.
- No free intervals after LLM subtracts busy intervals from the query range:
  agent says no free time was found in that range and can offer to check
  another range.
- Reminder runtime unavailable: agent explains that the calendar cannot be
  checked right now and does not invent availability.

## Verification

Required coverage:

- reminder model/service serialization for `durationMinutes`
- date-range reminder listing keeps owner and visibility boundaries
- bounded occurrence expansion for recurring reminders with duration
- calendar-facts tool requires active friendship
- calendar-facts tool excludes private reminder details
- agent prompt/runtime behavior supplies the 7-day range when no range is
  given
- shared reminder creation can persist and project duration
- prompt or runtime tests prove the agent treats Coke reminders as the
  calendar source, not Google Calendar
- prompt or runtime tests prove the fitness lesson default of 60 minutes lives
  in LLM policy, not backend booking policy

Runtime/eval coverage should include:

- B asks "A 这周有什么空余时间"; the tool returns busy facts only, and the
  agent replies with free intervals only
- B asks "那周二 10 点上课" and the agent creates a 60-minute shared reminder
  request when context clearly indicates a fitness lesson
- B names an ambiguous friend and the agent asks for clarification
- B asks about a non-friend and the agent directs them to add the person first

## Open Decisions

None. This spec chooses Coke reminders as the calendar source, LLM-owned
scheduling reasoning, friend-gated availability reads, default 7-day query
range, prompt-owned 60-minute fitness lesson default, and explicit reminder
duration support.
