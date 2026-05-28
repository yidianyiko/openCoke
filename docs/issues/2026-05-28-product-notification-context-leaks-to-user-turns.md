---
kind: active_issue
status: open
surface:
  - gateway-api
  - worker-runtime
created_at: 2026-05-28
updated_at: 2026-05-28
---

# 2026-05-28 Product Notification Context Leaks To User Turns

## What Happened

Production users intermittently received `系统刚才没能生成回复，请稍后再试一次。` for ordinary reminder list requests such as `我有几个提醒` and `我现在有几个待办项`.

## Why It Matters

Recent delivered product notifications were threaded into unrelated user turns. Worker runtime treated any `product_notification` metadata as a product-notification delivery turn, hid domain tools, and allowed the LLM to run without the reminder/scheduling tools required for the user request.

## Affected Surfaces

- `gateway-api`
- `worker-runtime`
- `clawscale-bridge`

## Evidence

- Production logs showed fallback sends for reminder-list turns while adjacent greetings/time queries succeeded.
- Agent logs for failed turns showed `tools=0`, `visible_messages=0`, and `status=empty`.
- Mongo input metadata for a failed `我现在有几个待办项` turn included stale `product_notification.ambiguity = "multi_notification"` from earlier delivered shared-reminder notifications.
- Local regression evidence: `artifacts/evidence/2026-05-28-product-notification-context-leak.md`.

## Current Status

- Fix implemented locally.
- Deployment and production smoke pending.

## Resolution

- Pending commit, deploy, and production verification.
