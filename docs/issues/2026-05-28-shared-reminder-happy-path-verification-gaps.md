---
kind: active_issue
status: open
surface:
  - production-smoke
  - agent-runtime
  - reminder-runtime
  - scheduling-domain
  - product-notifications
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Shared Reminder Happy-Path Verification Gaps

## What Happened

The direct shared-reminder happy-path verification was too coarse. Earlier
evidence collapsed several independent obligations into one pass/fail claim:

- requester synchronous Interaction Agent reply;
- durable shared-reminder creation and projection state;
- structured product-notification payload shape;
- worker facts-to-text output;
- provider delivery and notification reconciliation;
- Scheduling cleanup and cancellation notification delivery.

After tightening the production smoke criteria and running more marked real
account cases on 2026-05-28, the path is not clean:

- `server-smoke-20260528T072443Z`: receiver create/cancel notifications
  delivered, but the requester sync reply was the system fallback.
- `zhsmoke073047`: requester reply and durable creation passed, but receiver
  delivery failed with `wechat_send_failed ret=-2` and notification rows stayed
  pending.
- `dirsmoke074102`: `olivers -> 李梓豪` created and cancelled the shared
  reminder, and product notifications reconciled to delivered, but requester
  reply was fallback, create notification visible text was generic onboarding
  instead of facts-derived reminder text, `duration_minutes` was null despite
  `持续5分钟`, and cancellation produced mixed output statuses for the same
  notification.
- `multismoke075200`: `李梓豪 -> eva` created a shared reminder with correct
  `duration_minutes=5` and cleanup cancellation succeeded, but requester reply
  was fallback and create/cancel receiver notifications stayed
  `pending_delivery`; create output failed and gateway logs showed
  `wechat_send_failed ret=-2`.

## Why It Matters

A durable row is not the user-visible happy path. The user experience requires
both sides of the conversation to be correct: the initiating user needs a good
LLM reply, and the counterparty needs a facts-grounded notification that
actually reaches the provider. Treating a single marker or a single layer as a
blanket pass hid production regressions.

## Affected Surfaces

- `production-smoke`
- `agent-runtime`
- `reminder-runtime`
- `scheduling-domain`
- `product-notifications`
- `wechat-personal`

## Evidence

- Production matrix:
  `docs/issues/2026-05-27-real-user-happy-path-matrix.md`
- Production smoke skill:
  `.agents/skills/production-real-user-flow-smoke/SKILL.md`
- Production markers:
  `server-smoke-20260528T072443Z`, `zhsmoke073047`,
  `dirsmoke074102`, `multismoke075200`
- Durable cleanup evidence:
  `sr_3ff9d3cf41a1c05ae354ceda8f5e3001052bd15c` and
  `sr_094f735558746f6aed1af28df14058a87b05481e` were cancelled through
  Scheduling on 2026-05-28.

## Current Status

Open. The verification method has been tightened, and additional production
smokes have found multiple layer-specific failures. The direct shared-reminder
path must remain `partial-production` until one fresh marker satisfies all
layers in the stricter evidence standard.

## Resolution

Pending.
