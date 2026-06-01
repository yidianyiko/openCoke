---
kind: active_issue
status: open
surface:
  - conversation-runtime
  - worker-runtime
  - notification-delivery
created_at: 2026-06-01
updated_at: 2026-06-01
---

# Pending Async Reply Closed A Stateful Turn

## What Happened

In production conversation `7fed5c7c-08f9-4778-bdcc-c14b7f2cf346`, the user
answered a shared-reminder clarification with `晚上十点半`. The runtime wrote a
waiting message after 20 seconds, but that message failed provider delivery with
`provider_network_error`. The Interaction Agent then continued running for
several minutes and repeatedly attempted `social_scheduling_tool` and
`reminder_tool`, but every tool call failed with `turn_superseded`.

The turn eventually replied with a failure message instead of creating the
shared reminder.

## Why It Matters

The waiting reply path exists to make slow turns visible while the original
worker continues. It must not close the original input window or remove the
turn's authority to stage and materialize its own business command. At the same
time, a newer inbound message after the waiting text must still supersede the
old turn so stale background work cannot create the wrong reminder.

## Affected Surfaces

- `conversation-runtime`
- `worker-runtime`
- `notification-delivery`

## Evidence

- Production `message` rows:
  - `2026-06-01 03:17:08Z` inbound seq `121`: `晚上十点半`
  - `2026-06-01 03:17:28Z` outbound segment `0`: `我还在处理，稍等一下。`
  - `2026-06-01 03:23:21Z` outbound segment `1`: `抱歉，创建提醒遇到了问题，稍后再试一下?`
- Production `delivery_attempt` rows for turn
  `b9cb4979-6099-441c-b180-1983d8fca9c2`:
  - waiting attempt failed with `provider_network_error`
  - final failure reply was sent
- Production worker logs repeatedly showed `turn_superseded` from
  `ConversationRuntimeService.stage_command()` after the waiting dispatcher
  persisted `pending_async_reply`.
- No `staged_command` row and no new `shared_reminder` row were created for the
  affected turn.

## Current Status

- Open.
- The immediate product failure is understood.
- The fix must preserve real interruption safety and must not introduce blind
  WeChat retries that duplicate visible messages.

## Resolution

Record the fix commit and final verification when resolved.
