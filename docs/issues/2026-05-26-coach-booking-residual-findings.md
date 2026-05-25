---
kind: active_issue
status: open
surface:
  - agent-runtime
  - gateway-scheduling
created_at: 2026-05-26
updated_at: 2026-05-26
---

# 2026-05-26 Coach-booking residual findings after Bug X+Y+B fixes

## What Happened

True-baseline coach-booking hunt (batch 20260525t182719Z, after pm2
restart of coke-agent loading Bug X / Y / B fixes) shows 6 PASSED / 7
FINDING. Remaining findings need their own fix iterations.

### Passed

- **C1 happy-path**: student `约教练 Alex 明天 10:00 上一节课` →
  shared_reminder_request created, coach accept lands reminders for
  both sides. shared added=1, reminders added=2.
- **C3 outside-window**: agent creates 03:00 request, no invented
  availability constraint.
- **C4 vague-time**: agent asks clarification.
- **C9 coach-declines**: shared request → declined, rejected=True.
- **C11 past-time**: refused=True, no request created.
- **C13 coach-overview**: routes correctly, says_none when no
  shared reminders today.

### Remaining findings

| Case | Pattern | Symptom |
| ---- | ------- | ------- |
| C5 fuzzy-name | NEW | 4 name aliases tried; only 2 shared_requests created. Some fuzzy matches missed (`约 alex`, `约 Coach`, etc.). One non-existent name (`约张教练`) appears correctly refused. |
| C2 slot-collision | NEW | shared added=1 instead of 2 (back-to-back same-slot requests; second one silently dropped). |
| C12 concurrent-burst | NEW | shared added=1 of 3 (parallel turns lose 2 of 3 requests). |
| C6 cancel | NEW | shared_changed=1 but cancelled=False. Cancel turn modifies state but doesn't reach `cancelled` lifecycle. |
| C7 modify | C | shared_changed=0, has_11=False. Modify turn doesn't update the request. |
| C8 coach-initiated | C | coach_to_mei=False. Coach's `提醒明天 14:00 给 Student Mei 上一节课` creates personal reminder for coach, not shared request to Mei. |
| C10 calendar-facts | NEW | claims_busy=True but expected_tomorrow_accepted=0. Agent invents "busy" status without DB backing. (Was PASSED in earlier evidence with stale code; need to confirm if regression or LLM variability.) |

## Why It Matters

C5/C2/C12 are concurrency/lookup-quality bugs — silent data loss
when users issue multiple or fuzzy-named requests.

C6/C7 are core lifecycle bugs — cancel and modify don't reach the
gateway correctly. Suggests scheduling_domain inner worker or
gateway service mapping for these operations is broken.

C8 is intent-routing — coach-initiated turns should route to
create_shared_reminder with invitee=Mei, not personal reminder.

C10 invented-busy is a Bug C honesty regression worth confirming.

## Affected Surfaces

- `agent/agno_agent/runtime/agent_runtime.py` (preselector, intent
  routing)
- `agent/agno_agent/capabilities/scheduling.py` (modify/cancel arg
  shape)
- `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
  (modify, cancel operations)
- Concurrency: bridge `/bridge/inbound` parallel handling, worker
  pool lock contention

## Evidence

- `artifacts/evidence/shared-reminder-agent-smoke/coach-booking-20260525t182719Z.json`
  (gitignored locally; reference path).

## Current Status

Open. Each finding needs scope decision (D2 doc only / D3 product fix)
and either separate design+fix codex or bundled. Suggested grouping:

1. **C2/C12 concurrency** — investigate bridge inbound serialization
   + worker pool behavior.
2. **C6/C7 lifecycle mutations** — likely shared finding in
   scheduling_domain operation arg shape.
3. **C5 fuzzy-name** — friend-resolver quality improvement.
4. **C8 coach-initiated** — preselector / intent inference for
   coach's initiating direction.
5. **C10 invented-busy** — re-verify before deciding (may be LLM
   variability vs deterministic).

## Resolution

(unfilled)
