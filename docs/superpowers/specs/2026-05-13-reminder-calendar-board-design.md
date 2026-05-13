# Reminder Calendar Board Design

**Status:** implemented
**Date:** 2026-05-13
**Owner:** Codex

## Summary

Add a customer-facing reminder calendar board at `/account/reminders`. The
first version is a weekly calendar board backed by the existing Reminder
System. It lets authenticated customers view, create, edit, complete, and
cancel their own visible reminders from the web.

The web page is not a separate task database. It is a calendar view over
MongoDB `reminders`, scoped by the authenticated Coke customer id. Web-created
reminders default to the customer's most recently active Kap conversation as
their delivery target.

## Goals

- Let a customer manage their own reminders from the account web UI.
- Use a familiar weekly calendar board as the default view.
- Support both reminders created in chat and reminders created from the web.
- Keep the existing Reminder System as the source of truth for reminder state,
  lifecycle, scheduling, and scheduler integration.
- Keep customer isolation at the API boundary and at the ReminderService
  boundary.
- Make the missing-conversation case explicit before creating a reminder.

## Non-Goals

- Full general-purpose task management.
- A separate task table or separate reminder projection owned by the web app.
- Drag-and-drop rescheduling.
- Full month/day calendar implementation in the first release.
- Multiple delivery target selection in the first release.
- Reminder sharing, collaboration, priorities, notes, labels, or subtasks.
- Browser push notifications or email delivery.
- Changing chat reminder semantics or reminder-detect behavior.

## Product Design

The customer account shell gains a `Reminders` navigation item pointing to
`/account/reminders`.

The first screen is a weekly calendar board:

- Header: current week label, previous week, next week, Today, and Create
  reminder.
- Seven day columns from Monday through Sunday.
- Each column lists reminders by local time.
- Active reminders are primary. Completed, cancelled, and failed reminders can
  be shown with subdued state styling when included by filter.
- Clicking a reminder opens an edit drawer.
- Create reminder opens the same drawer in create mode.

The drawer fields are:

- title
- date
- time
- repeat rule for the small first-version set: none, daily, weekly
- lifecycle action buttons: save, complete, cancel

The page does not ask the user to pick a conversation. Web-created reminders
are delivered to the most recently active Kap conversation for that customer.
The required delivery target is the conversation id plus Kap character id;
route key is a best-effort optional hint when the runtime context has one.
If no usable conversation exists, the create action returns
`conversation_required` and the page tells the user to start or resume a Kap
chat first.

## User Stories

1. As a logged-in customer, I can open `/account/reminders` and see my
   reminders arranged in the current week.
2. As a logged-in customer, I can move to previous and next weeks without
   seeing another user's reminders.
3. As a logged-in customer, I can create a reminder from the web and know it
   will be delivered to my latest Kap conversation.
4. As a logged-in customer without any active Kap conversation, I get a clear
   blocked state instead of creating an undeliverable reminder.
5. As a logged-in customer, I can edit the title or schedule of my own active
   reminder.
6. As a logged-in customer, I can complete or cancel my own active reminder.
7. As a logged-in customer, I cannot read or mutate another customer's
   reminder by guessing a reminder id.

## Architecture

The implementation keeps the Reminder System in Python as the behavioral owner:

```text
Web /account/reminders
  -> Gateway customer reminder routes
  -> Bridge internal reminder routes
  -> ReminderService + ReminderDAO
  -> MongoDB reminders
  -> ReminderScheduler
```

The TypeScript gateway owns customer authentication and public/customer API
shape. The Python bridge owns reminder command execution because it already
has the ReminderService, schedule handling, scheduler hooks, and runtime Mongo
configuration.

The gateway must not write `reminders` directly. The bridge internal API must
not accept unauthenticated public traffic; it uses the same bridge bearer auth
pattern as the Google Calendar import internal routes.

## API Design

### Customer API

All routes require the existing customer bearer token.

`GET /api/customer/reminders?from=YYYY-MM-DD&to=YYYY-MM-DD&states=active,completed`

List range semantics:

- `from` and `to` are local dates in the requested display timezone.
- `from` is inclusive and `to` is inclusive.
- The first release supports at most 31 days per request. The weekly board
  requests seven days.
- Default `states` is `active`.
- Allowed states are `active`, `completed`, `cancelled`, and `failed`.
- One-shot reminders are included when `schedule.local_date` falls inside the
  requested date range.
- Recurring reminders are included when their current `next_fire_at` maps to a
  local date inside the requested range. The first release does not expand all
  future recurrence occurrences across the week.
- Filtering happens in the Python Reminder System through an owner-scoped
  range query. The gateway and web UI must not fetch all customer reminders and
  apply unbounded client-side filtering.

Returns:

```json
{
  "ok": true,
  "data": {
    "reminders": [
      {
        "id": "65f...",
        "title": "Pay invoice",
        "lifecycleState": "active",
        "localDate": "2026-05-13",
        "localTime": "09:00",
        "timezone": "Asia/Tokyo",
        "rrule": null,
        "nextFireAt": "2026-05-13T00:00:00.000Z"
      }
    ]
  }
}
```

`POST /api/customer/reminders`

Request:

```json
{
  "title": "Pay invoice",
  "localDate": "2026-05-13",
  "localTime": "09:00",
  "timezone": "Asia/Tokyo",
  "rrule": null
}
```

The gateway forwards the request to the bridge. The bridge resolves the latest
usable Kap conversation for the customer and creates a Reminder with that
conversation as the `agent_output_target`.

The bridge converts `localDate + localTime + timezone` into a timezone-aware
local datetime, then uses the corresponding UTC instant as
`ReminderSchedule.anchor_at`. If the timezone is unknown, the wall time is
invalid, or the resulting one-shot reminder is not in the future,
ReminderService returns a validation error that the bridge maps to
`invalid_schedule`. Ambiguous DST wall times use Python `zoneinfo` default
fold behavior for the first release; explicit DST disambiguation is out of
scope until a real user need appears.

`PATCH /api/customer/reminders/:id`

Request supports:

```json
{
  "title": "Pay invoice",
  "localDate": "2026-05-14",
  "localTime": "10:30",
  "timezone": "Asia/Tokyo",
  "rrule": "FREQ=WEEKLY"
}
```

`POST /api/customer/reminders/:id/complete`

Completes an active reminder.

`POST /api/customer/reminders/:id/cancel`

Cancels an active reminder.

### Bridge Internal API

The bridge exposes matching internal endpoints under
`/bridge/internal/reminders`. The bridge API receives trusted customer ids from
the gateway and always passes them to ReminderService as `owner_user_id`.

The bridge returns stable error codes:

- `unauthorized`
- `invalid_body`
- `conversation_required`
- `reminder_not_found`
- `invalid_schedule`
- `invalid_reminder`
- `bridge_service_not_wired`

## Data Model

No new durable reminder model is introduced. Existing Reminder fields are used:

- `owner_user_id`: customer id such as `ck_...`
- `title`
- `schedule.anchor_at`
- `schedule.local_date`
- `schedule.local_time`
- `schedule.timezone`
- `schedule.rrule`
- `agent_output_target.conversation_id`
- `agent_output_target.character_id`
- `agent_output_target.route_key`
- `lifecycle_state`
- `next_fire_at`

The ReminderDAO gains an owner-scoped list contract for the weekly board:

```python
list_for_owner_in_local_date_range(
    owner_user_id: str,
    *,
    from_date: date,
    to_date: date,
    lifecycle_states: list[str],
) -> list[dict]
```

The selector must include `owner_user_id` and lifecycle state. It may use
`schedule.local_date` for one-shot reminders and `next_fire_at` for recurring
active reminders. The method must not expose cross-customer reminders.

For web-created reminders, `created_by_system` remains `agent` in the current
dataclass contract. If a future product requirement needs attribution, add a
separate field through a dedicated Reminder System schema change instead of
overloading first-version behavior.

## Latest Conversation Resolution

The bridge resolves the default delivery target for web-created reminders with
the same baseline as Google Calendar import preflight, but names the behavior
precisely:

1. Resolve the default Kap character id from the existing bridge character
   provider.
2. Find the latest private conversation whose talkers include
   `db_user_id=customer_id` and the Kap character id.
3. "Latest" means the same current DAO fallback: sort matching Mongo
   conversations by `_id` descending and take one. This is a practical proxy
   for most recently created/active in the existing data shape.
4. "Usable" means the conversation has a non-empty `_id`, includes the
   customer and Kap character as private talkers, and can be resolved by the
   existing conversation DAO. The first release does not require a delivery
   route row or business handoff context.
5. Prefer a conversation with business protocol route metadata when available,
   but do not require route metadata for creation.
6. Use the conversation `_id` as `conversation_id`, the Kap character id as
   `character_id`, and any stored route key as optional `route_key`.
7. If no conversation is found, return `conversation_required`.

This follows the same product rule used by Google Calendar import preflight:
web-originated reminder creation requires a deliverable Kap conversation.

## Validation

Customer API validation:

- title must be non-empty and at most 200 characters.
- local date must be `YYYY-MM-DD`.
- local time must be `HH:mm`.
- timezone must be a non-empty IANA timezone string.
- rrule is either absent/null or one of the first-version values:
  `FREQ=DAILY`, `FREQ=WEEKLY`.
- week query date range must be valid and bounded to 31 days.
- query state filters must be a subset of `active`, `completed`,
  `cancelled`, and `failed`.

ReminderService remains responsible for final schedule validity, future-time
checks, lifecycle mutation checks, and owner-scoped mutation.

The web customer API helper gains `patch` support so the page can call
`PATCH /api/customer/reminders/:id` consistently with the route design.

## Error Handling

Authentication errors redirect the web user to login, following existing
customer pages.

`conversation_required` shows a blocked create state with a link to the
customer channel/chat entry point.

`reminder_not_found` means either the reminder does not exist or does not
belong to the authenticated customer; the UI shows a generic stale reminder
message and refreshes the board.

Validation errors stay in the drawer and do not mutate the reminder.

Transport or bridge errors show a retryable inline error.

## Testing

Bridge tests:

- internal reminder routes require bearer auth.
- list calls ReminderService with the customer id.
- create resolves latest conversation and creates a reminder.
- create returns `conversation_required` when no conversation exists.
- update, complete, and cancel are owner-scoped.

Gateway tests:

- customer reminder routes require customer auth.
- list forwards only the authenticated customer id.
- create/update/complete/cancel forward to bridge client and map errors.
- another customer cannot be injected through request body.

Web tests:

- `/account/reminders` renders the week calendar board.
- reminders are grouped into day columns by local date.
- create drawer submits a web reminder.
- `conversation_required` shows the chat-first blocked state.
- edit, complete, and cancel actions call the customer API.
- customer shell navigation includes Reminders.

Verification:

- focused Python bridge tests.
- focused gateway API tests.
- focused web page tests.
- gateway package type/build checks if touched code requires it.
- diff-aware repo verification via `scripts/suggest-verification` and
  `scripts/review-trigger`.

## Rollout Notes

This is a customer-account web feature. It does not change the chat reminder
detector, fired reminder event handling, or scheduler semantics.

If deployed before web creation is enabled, the list/edit/complete/cancel path
still provides value for chat-created reminders. Web create should remain
blocked on `conversation_required` until a user has a deliverable Kap
conversation.
