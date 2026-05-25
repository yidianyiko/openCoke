---
kind: active_issue
status: open
surface:
  - agent-runtime
  - reminder-intent
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Reminder Create Without Duration Fails InvalidSchedule

## What Happened

Live smoke batch `reminder-complete-20260525t084602Z` tried to set up the
previously untested personal reminder complete path:

- `提醒我明天早上 8 点做平板支撑。`
- `标记平板支撑提醒完成。`

The first turn failed before the complete operation could be tested. The
assistant replied that reminders were temporarily unavailable, and Mongo had no
reminder owned by the smoke account.

`agent_sessions` showed the chat agent called `reminder_domain`. The reminder
domain result failed twice with:

```text
InvalidSchedule: 创建提醒失败：Reminder duration must be positive
```

The first failed attempt had no explicit duration. The second attempt tried to
recover with `duration_minutes=2`, but the domain still returned the same
`InvalidSchedule`.

## Why It Matters

One-shot personal reminders do not require a duration. The reminder service
schema allows `duration_minutes=None`, and existing CRUD smoke coverage creates
ordinary reminders successfully when the phrase includes an explicit duration
or when the detector produces a valid schedule.

A user asking "remind me tomorrow at 8 to do planks" should create a point
reminder or ask a targeted clarification. It should not fail with an internal
duration validation error.

## Evidence

- Failed artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-complete-20260525t084602Z.json`
- Smoke account:
  `ck_smoke_remindercomplete20260525t084602z_alice`
- Mongo `reminders` for that account: empty.
- `agent_sessions` tool result:
  `error.code=InvalidSchedule`, message `Reminder duration must be positive`.

Control run with explicit duration passed:

- Artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-complete-explicit-duration-20260525t084922Z.json`
- User said:
  `提醒我明天早上 8 点做平板支撑 5 分钟。`
- Mongo reminder:
  `title=做平板支撑`, `duration_minutes=5`,
  `lifecycle_state=completed`, `next_fire_at=None`, `completed_at` present.

## Current Status

Open. The complete operation itself passed when setup used an explicit duration,
but no-duration create remains unverified and currently fails in the live smoke.

## Resolution

(unfilled)
