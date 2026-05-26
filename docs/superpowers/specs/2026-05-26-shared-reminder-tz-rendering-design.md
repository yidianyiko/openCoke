# Shared Reminder Timezone Rendering Fix

Date: 2026-05-26
Status: Design
Scope: worker-runtime, gateway-api
Related CFL cluster: shared-reminder timezone rendering, L4 and L7; related
modification drift in L5 and L8.

## Reviewable Summary

Shared reminders currently persist a correct absolute instant but lose the
user/account timezone that gives that instant its wall-clock meaning. In CFL
L4 and L7, a user asked for local 10:00. The stored row became
`fireAt=2026-05-27T01:00:00.000Z` and `timezone=UTC`. That instant is
consistent with 10:00 in a UTC+9 account timezone, but `timezone=UTC` makes
all downstream list, notification, and projection rendering treat it as
01:00.

The minimal fix is to preserve the requester's account timezone on shared
reminder create and to render every shared-reminder display surface in the
viewer's account timezone. Do not auto-migrate existing rows: some old rows
may contain a correct instant with a wrong timezone, and others may already be
semantically UTC. Migrating them needs an explicit data decision.

## Evidence

- CFL L4 create turn: user asked for local 10:00. The scheduling result stored
  `fireAt=2026-05-27T01:00:00.000Z`, `timezone=UTC`, then Alice and Bob saw
  Beijing 09:00 for a 10:00 request.
- CFL L7 create turn: user asked for local 10:00. The final shared list
  rendered the same stored row as raw 01:00.
- `docs/superpowers/specs/2026-05-26-cfl-triage-design.md` classifies this as
  a real product bug and calls out the split between storage facts and reply
  rendering.
- `gateway/packages/api/src/routes/internal-scheduling-routes.ts` defaults
  missing shared-reminder create and list `timezone` fields to `UTC`.
- `gateway/packages/api/src/scheduling/shared-reminder-service.ts` stores the
  supplied `fireAt` instant and `timezone`, then derives runtime reminder
  `localDate` and `localTime` by formatting that instant in the supplied
  timezone.
- `agent/agno_agent/capabilities/scheduling.py` renders list summaries by
  converting `fireAt` with `item.timezone`; when the item says `UTC`, the
  summary must render 01:00.

## Current Storage Trace

### 1. User and Interaction Agent

The user says "tomorrow 10:00" in the conversation/account timezone. The
chat response instructions expose a default user timezone to the model, but
the shared-reminder tool contract does not guarantee that timezone is passed
with create requests.

The scheduling args type allows `timezone`, but it is optional:
`SharedReminderSchedulingArgs.timezone: str | None`.

### 2. Scheduling Execution Agent

The scheduling execution agent converts the relative local request into a
concrete create call. The CFL evidence shows the create operation ended with
`fireAt=2026-05-27T01:00:00.000Z`; this is the absolute instant for 10:00 in a
UTC+9 account timezone.

The same create result has `timezone=UTC`. That means the instant was
normalized, but the account timezone did not survive as companion metadata.
The evidence does not require the gateway to have performed this conversion;
it only proves the gateway received or stored an absolute instant and defaulted
timezone metadata to UTC.

### 3. Agent-Side Gateway Wrapper

`SchedulingCapabilityPort._trusted_tool_payload()` copies model args and adds
customer/conversation/platform/idempotency data. It does not add
`run_context.user.timezone` when timezone is absent.

Result: a create call can carry `fire_at` without `timezone`.

### 4. Internal Gateway Route

The internal scheduling route passes create input to `createSharedReminder()`.
For `create_shared_reminder`, it reads:

- `fireAt: stringField(body, 'fire_at')`
- `timezone: stringField(body, 'timezone', 'UTC')`

This is the concrete point where missing account timezone becomes `UTC`.

### 5. Shared Reminder Service

`createSharedReminder()` parses `fireAt` with `new Date(input.fireAt)`, stores
that Date in `shared_reminder_requests.fire_at`, and stores the supplied
`timezone` string in `shared_reminder_requests.timezone`.

Then `createProjection()` calls `splitInstant(input.fireAt, input.timezone)`.
Because timezone is already `UTC`, the requester/invitee runtime reminder is
created with `localDate=2026-05-27`, `localTime=01:00`, `timezone=UTC`. This
is correct behavior for the wrong metadata.

## Current Display Trace

### Shared Reminder List Facts

`listSharedReminders()` returns stored rows as-is. The internal route also
defaults list query timezone to `UTC` when absent, but that query timezone is
only used for date filtering and response metadata. It does not rewrite row
timezone.

The list facts therefore expose each row with:

- `fireAt=2026-05-27T01:00:00.000Z`
- `timezone=UTC`

### Agent Visible Summary Path

`agent/agno_agent/capabilities/scheduling.py` builds fallback list summaries
with `_shared_reminder_time_text()`:

1. Read `fireAt` or `fire_at`.
2. Read `timezone`.
3. Parse the instant.
4. If timezone exists, convert with `ZoneInfo(timezone)`.
5. Format `%Y-%m-%d %H:%M`.

With `timezone=UTC`, this path renders raw 01:00. This matches L7.

### Interaction Agent Reply Path

L4 did not use the fallback visible summary verbatim. The scheduling facts
available to the model contained `fireAt=01:00Z` and `timezone=UTC`, but the
final reply said Beijing 09:00. That is an inconsistent synthesis path: the
model appears to have taken the UTC instant and applied a Beijing/Shanghai
offset itself. Because the stored row had lost the account timezone, the model
had no durable way to render the requested 10:00.

So L4 and L7 differ by display path:

- L7: deterministic summary path trusts row timezone `UTC` and shows 01:00.
- L4: model synthesis path uses the instant plus its own timezone assumption
  and shows Beijing 09:00.

Both are downstream symptoms of the same lost timezone context.

## Root Cause

This is both a storage-context bug and a display-contract bug.

Storage normalization to UTC is not wrong by itself. Storing `fire_at` as an
absolute instant is appropriate for scheduling. The bug is storing that instant
with `timezone=UTC` when the user meant a local wall time in their account
timezone.

Display is also wrong because no display path should render shared reminders
from raw UTC or hard-coded Beijing/Shanghai assumptions. Every display path
must know which account is viewing the reminder and render `fire_at` in that
account's effective timezone.

## Proposed Fix

### A. Preserve Account Timezone On Create

At the agent wrapper boundary, ensure scheduling tool payloads carry
`timezone=run_context.user.timezone` for shared-reminder create when the model
did not provide one.

At the internal gateway route boundary, stop treating missing create timezone
as a valid UTC request. For `create_shared_reminder`, either:

1. require `timezone` and fail closed with `invalid_body` if absent, or
2. resolve the requester's account timezone server-side and use that value.

Preferred: resolve server-side if the gateway has a canonical customer
timezone field available on the request path; otherwise require the agent
wrapper to pass it and remove the `UTC` default for create. In either case,
`shared_reminder_requests.timezone` must preserve the original scheduling
timezone, not a fallback default.

Expected create result for a UTC+9 account request at local 10:00:

- `fireAt=2026-05-27T01:00:00.000Z`
- `timezone=Asia/Tokyo`
- requester projection `localTime=10:00`, `timezone=Asia/Tokyo`

For a UTC+8 account, the correct instant would instead be
`2026-05-27T02:00:00.000Z` with `timezone=Asia/Shanghai`.

### B. Render For The Viewer Account

List, pending, notification, and agent summary output should render using the
viewer's effective account timezone.

Minimal rule:

- Keep row `fireAt` as the canonical instant.
- Keep row `timezone` as the scheduling timezone from create.
- Add display fields in gateway responses and notification metadata:
  `viewer_timezone`, `viewer_local_date`, `viewer_local_time`.
- The agent summary should prefer those display fields. If absent, it may
  compute from `fireAt` plus a viewer timezone supplied by the route response.
  It should not use UTC unless the viewer account timezone is actually UTC.

For shared reminders with requester and invitee in different timezones, the
stored instant stays shared, but each viewer sees their own local wall time.
The original scheduling timezone can still be retained for audit and future
modify semantics.

### C. Remove Hard-Coded Display Assumptions

Do not render shared reminders by applying Beijing/Shanghai as a default. A
Chinese-language reply is not evidence that the user is in Beijing time.

The deterministic summary function should not infer timezone from language,
server locale, or row fallback. It should use only explicit viewer timezone
metadata.

### D. Modification Follow-Up

L5/L8 modification date drift is related but larger than this fix. The design
boundary here is to make create/list display timezone-correct first. The
implementation plan should separately check whether modify flows use the
original shared reminder date/timezone as context instead of parsing a new
same-day datetime.

## Minimal Blast Radius

Touch only:

- Agent scheduling payload construction, to pass account timezone when absent.
- Internal scheduling route create/list timezone handling.
- Shared-reminder service response/notification display fields if needed.
- Agent scheduling summary rendering to consume explicit viewer display fields.
- Focused tests around these paths.

Do not:

- Add compatibility shims for legacy timezone-less create calls.
- Change personal reminder timezone behavior.
- Change the shared-reminder status enum or pending/list status mapping in
  this fix, except as a separate listed dependency if L7 pending tests require
  it.
- Auto-migrate historical `shared_reminder_requests` rows.

## Data Risk

Existing rows with `timezone=UTC` are ambiguous:

- Some may be true UTC reminders.
- Some may be local reminders whose account timezone was lost.
- Some may have requester and invitee projections already created with wrong
  local schedule fields.

Do not auto-migrate. A later data repair decision needs evidence from account
timezone, creation trace, projection schedule, and user-visible history. The
safe near-term behavior is to fix new writes and render old rows according to
their stored facts unless a deliberate repair path is approved.

## Verification Plan

### Unit Tests

1. Agent scheduling wrapper:
   - Given `run_context.user.timezone=Asia/Tokyo` and create args without
     timezone, payload sent to the gateway includes `timezone=Asia/Tokyo`.
   - Given model args with an explicit valid timezone, preserve that value.

2. Internal gateway route:
   - `create_shared_reminder` no longer defaults missing timezone to `UTC`.
   - With timezone present, it forwards that exact timezone to
     `createSharedReminder()`.

3. Shared reminder service:
   - Creating with `fireAt=2026-05-27T01:00:00.000Z` and
     `timezone=Asia/Tokyo` stores both fields and creates runtime reminders
     with `localDate=2026-05-27`, `localTime=10:00`.
   - Notification metadata includes viewer display fields and does not render
     `01:00` for a UTC+9 viewer.

4. Agent summary rendering:
   - A list item with `fireAt=2026-05-27T01:00:00.000Z` and viewer timezone
     `Asia/Tokyo` renders `2026-05-27 10:00`.
   - The same item with viewer timezone `Asia/Shanghai` renders
     `2026-05-27 09:00`.
   - No path uses raw `01:00` unless viewer timezone is `UTC`.

### Smoke / Corpus

Re-run the CFL L4 and L7 shared-reminder slices with GLM-5.1 thinking-off.

Pass criteria:

- L4 create at local 10:00 stores an absolute instant plus the account
  timezone, and both Alice/Bob fact queries display local 10:00 for users in
  that timezone.
- L7 final shared list displays local 10:00, not raw 01:00.
- Product notification payload for the invitee carries display time in the
  invitee account timezone.
- Existing related failures, such as pending-list enum mismatch and
  modification routing, may remain separately failing but must be reported as
  distinct issues rather than timezone regressions.
