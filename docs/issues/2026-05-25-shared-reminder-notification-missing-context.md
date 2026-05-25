---
kind: incident
status: resolved
surface:
  - gateway-api
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Shared Reminder Notification Missing Invitation Context

## What Happened

Invitees receive the shared-reminder push notification, but the delivered
message is the generic text `你有一个共享提醒请求，请确认或拒绝。`.
The persisted `product_notifications.payload.metadata` also contains only
`request_id`, `request_type`, and `allowed_actions`.

## Why It Matters

The invitee cannot tell who sent the request, what the reminder is for, when it
fires, or how long it lasts. That makes the accept/reject decision blind even
though the request row exists and delivery succeeds.

## Affected Surfaces

- `gateway-api`

## Root Cause

`gateway/packages/api/src/scheduling/shared-reminder-service.ts` enqueues the
shared-reminder product notification with hard-coded generic text and minimal
metadata. The request row already has the richer invitation facts, but the
notification builder does not project them into the outbound payload.

## Evidence

- `enqueueSharedReminderNotification(...)` takes a caller-supplied `text`
  string and forwards it unchanged into `enqueueProductNotification(...)`.
- `finalizeRequesterProjection(...)` passes the fixed text
  `你有一个共享提醒请求，请确认或拒绝。`.
- The request row already carries `title`, `fireAt`, `timezone`, and optional
  `durationMinutes`.

## Resolution

`gateway/packages/api/src/scheduling/shared-reminder-service.ts` now builds the
shared-reminder notification from the request row instead of a fixed string. The
gateway reads the requester display name, formats the reminder local date/time,
adds the optional duration to the message text, and persists the same invitation
facts in `payload.metadata`.

## Verification

- `pnpm --dir gateway/packages/api test -- src/scheduling/shared-reminder-service.test.ts -t "includes invitation context in shared reminder notification text and metadata"`
- `pnpm --dir gateway/packages/api build`
- `zsh scripts/check`
