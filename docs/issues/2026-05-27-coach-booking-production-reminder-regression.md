---
kind: issue
status: resolved
title: Coach-booking production decline created a reminder
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - production-smoke
  - agent-runtime
  - reminder-runtime
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-shared-smoke-20260527T085644Z.md
---

# Coach-Booking Production Decline Created A Reminder

## What Happened

Production real-user happy-path smoke used `olivers` with marker
`happy-coach-decline-20260527T124703Z`.

Input:

`周日15:00帮我约一节羽毛球教练课，备注happy-coach-decline-20260527T124703Z。`

Expected behavior:

- Explain that Coke cannot directly book external coach/class appointments.
- Optionally offer to create a reminder if the user wants one.
- Do not create a reminder or shared-reminder request from the booking request
  itself.

Actual bridge reply:

`已帮你设置好提醒：周日（5月31日）15:00约羽毛球教练课。到时候提前提醒你～`

## Durable Side Effects

Mongo showed a visible reminder was created:

- id: `6a16e853bf17f1be4ee1b190`
- title: `约一节羽毛球教练课（备注happy-coach-decline-20260527T124703Z）`
- state before cleanup: `active`
- next fire: `2026-05-31 15:00 Asia/Shanghai`

PostAnalyze also created an internal follow-up:

- id: `6a16e85cbf17f1be4ee1b1a2`
- visibility: `internal`
- fire mode: `followup`
- state before cleanup: `active`
- next fire: `2026-05-31 14:30 Asia/Shanghai`

Postgres showed no shared reminder request or product notification with the
marker.

Cleanup completed:

- visible reminder `6a16e853bf17f1be4ee1b190`: `cancelled`,
  `next_fire_at=null`
- internal follow-up `6a16e85cbf17f1be4ee1b1a2`: `cancelled`,
  `next_fire_at=null`

## Root Cause

The outer chat agent called `reminder_domain`. The inner ReminderDetectAgent
then classified the external coach/class booking request as a `crud/create`
reminder and the reminder runtime executed it.

This is a product boundary issue in reminder intent detection. External
booking, reservation, appointment, or class/coach scheduling requests are not
reminder creation requests unless the user explicitly asks to be reminded or
notified to do that booking.

A prompt-only boundary was not sufficient in production:

- Retest marker: `happy-coach-decline-fix-20260527T125434Z`
- Reply still claimed a reminder was created.
- Visible reminder `6a16ea10c4835f0b27a70fa2` was created and then cleaned up.

A first structural rejection stopped the visible reminder but returned the
result as clarification:

- Retest marker: `happy-coach-decline-fix2-20260527T125930Z`
- Reply asked whether the user wanted a reminder or direct booking.
- No visible reminder was created.
- PostAnalyze created internal follow-up `6a16eb455f971985d9fccdce`, which was
  cleaned up.

## Fix

The final fix keeps the active product contract in the reminder domain boundary:

- ReminderDetect instructions state the general boundary: external booking,
  reservation, appointment, and class/coach scheduling are discussion unless
  the user explicitly asks to be reminded.
- Reminder intent rejects detector-generated reminder creates for external
  booking requests that do not contain an explicit reminder/notification verb.
- The rejection is a `DomainExecutionResult(outcome="rejected")` with
  `safety_boundary="external_booking_requires_reminder_request"`.
- Runtime treats rejected reminder-domain safety summaries as authoritative
  visible text, so the model cannot rewrite the boundary into an ambiguous
  clarification or completed reminder claim.
- The valid path remains supported: `提醒我约教练` can still create a reminder.

## Final Verification

Focused tests passed:

`19 passed` for reminder intent, reminder-detect prompt, and runtime output
rules covering the external booking boundary.

Deploy:

`./scripts/deploy-compose-to-gcp.sh --restart` completed with remote health
checks and public site verification.

Production retest:

- marker: `happy-coach-decline-fix3-20260527T130832Z`
- input:
  `周日15:00帮我约一节羽毛球教练课，备注happy-coach-decline-fix3-20260527T130832Z。`
- visible reply:
  `我不能直接帮你完成外部预约。需要提醒时，请告诉我具体提醒时间和内容。`
- Mongo: no marker-matched visible reminder was created.
- PostAnalyze: `[FollowupPlan] 未设置内部 proactive follow-up`
- Postgres: no marker-matched `shared_reminder_requests` or
  `product_notifications`.

Status: resolved and verified in production.
