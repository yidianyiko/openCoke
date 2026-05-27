---
kind: progress_note
status: resolved
title: Shared reminder cancel did not notify invitee
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - production-smoke
  - scheduling-domain
  - gateway
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-shared-smoke-20260527T085644Z.md
---

# Shared Reminder Cancel Notification Regression

## Problem

Production real-user smoke for shared reminder cancel/list used marker
`happy-shared-cancel-20260527T115435Z`.

- Create succeeded and invite notification was delivered to `李梓豪`.
- List showed the pending shared reminder.
- Requester cancel moved the durable request to `cancelled`.
- Requester projection reminder `6a16dbfb43dbe3c071262a84` became
  `cancelled`, `nextFireAt=null`.
- No product notification told `李梓豪` that `olivers` cancelled the pending
  invite.

## Root Cause

`cancelSharedReminder` cancelled the requester projection and marked the request
`cancelled`, but it did not enqueue any invitee notification. The accept and
reject paths now both have idempotent requester notifications; cancel needed the
symmetric invitee notification.

## Fix

Gateway shared reminder service now enqueues idempotent
`shared_reminder_cancelled` to the invitee after a successful requester cancel,
and compensates the same notification when a cancel retry sees an already
`cancelled` request.

## Verification Plan

- Unit: cancel before fire time creates `shared_reminder_cancelled` for the
  invitee.
- Gateway related tests and TypeScript build.
- Production: deploy, rerun fresh create/list/cancel marker, verify durable
  `cancelled`, requester projection cancellation, invite notification, invitee
  cancellation notification, and cleanup.

## Verification Result

Local:

```bash
pnpm --filter @clawscale/api exec vitest run \
  src/scheduling/shared-reminder-service.test.ts \
  src/routes/internal-scheduling-routes.test.ts \
  src/scheduling/notification-service.test.ts
pnpm --filter @clawscale/api exec tsc -p tsconfig.json --noEmit
.venv/bin/python -m pytest \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_execution_agents.py \
  tests/unit/agent/test_agent_runtime_construction.py -q
```

Result:

- gateway related tests: `98 passed`
- TypeScript: passed
- Python scheduling tests: `115 passed`

Production:

- Deployed with `./scripts/deploy-compose-to-gcp.sh --restart`.
- Final passing marker: `happy-shared-cancel-fix-20260527T120556Z`.
- List reply showed the marked pending shared reminder.
- Cancel reply confirmed cancellation.
- Durable request `cmpo0sfxj0001nw1tcxyyay06` became `cancelled`.
- Requester reminder `6a16dea39cd5c9dd50be7f11` was `cancelled`,
  `nextFireAt=null`.
- Invite notification and invitee `shared_reminder_cancelled` notification were
  both delivered.
- Exact marked shared requests were deleted after verification.
