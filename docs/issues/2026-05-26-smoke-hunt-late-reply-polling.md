---
kind: active_issue
status: open
surface:
  - tools/agent_smoke
created_at: 2026-05-26
updated_at: 2026-05-26
---

# 2026-05-26 Smoke hunts don't poll late replies → false negatives on slow turns

## What Happened

After Bug B cluster fix (commit `0d427c07`), coach-booking hunt re-run
showed 11 of 12 cases with reply text
`正在处理中，稍后把结果发给你。` (the Bug Y sync-timeout placeholder)
and `shared_added=0` etc. Initial read: "Bug B fix regressed
everything."

But the bridge sync window is 25s (`conf/config.json:reply_timeout_seconds`)
and scheduling_domain calls (preselector + inner worker) frequently
exceed it after the Bug B fix routes more requests there. The eventual
real reply lands via the Bug Y late-promotion path moments after the
hunt has already snapshot the state.

In production with a real `DeliveryRoute`, the late reply gets
delivered. In smoke (no route), the user-visible final text remains
the placeholder, and the late real output row reaches `status=failed`
with correct push metadata — exactly the `wont_fix`
`missing-delivery-route` gateway behavior.

Per-case observed reply pattern in
`artifacts/evidence/shared-reminder-agent-smoke/coach-booking-20260525t174903Z.json`:

- C3, C4, C7, C8, C9, C11, C13: only placeholder text in evidence.
- C1, C5, C6, C12: placeholder + partial real text.
- C10: PASSED (its assertions don't need the late reply).
- C2: placeholder twice.

## Why It Matters

The hunt is reading state too early for any case that exceeds the
bridge sync window. Findings classified as `NEW` or `B` may actually
be PASSED with a late real reply the hunt never sees. False negatives
make every smoke iteration look worse than it is.

Real product issues (e.g., the C5 fuzzy-name partial behavior or C3
outside-window invented constraints) are getting mixed with smoke
false negatives.

## Affected Surfaces

- `tools/agent_smoke/_runner_phase_coach_booking_hunt.py`
- All other phase runners that snapshot state immediately after
  `send_as` (`_runner_phase_class_booking_refusal.py`,
  `_runner_phase_interruption.py`, `_runner_phase_recurring_reminder.py`).

## Evidence

- `artifacts/evidence/shared-reminder-agent-smoke/coach-booking-20260525t174903Z.json`
- Bridge log shows multiple `late_clawscale_reply_missing_route_context_promoting_without_bind`
  entries during the same hunt run (Bug Y fix working).
- 11 of 12 cases reply text contains the placeholder string.

## Current Status

- Open. Hunt verdict is unreliable for slow turns until fixed.
- Bug B cluster fix unit tests pass (222 agent + 31+54 gateway), but
  smoke verification doesn't reflect that.

## Resolution

Update `_runner_phase_coach_booking_hunt.py` (and the other phase
runners later) so that after `send_as` returns the placeholder text,
it polls mongo `outputmessages` for the late real reply matching the
same `causal_inbound_event_id`, with a configurable timeout (suggest
45s). If the late real reply lands, use ITS text for assertions; if
not, classify the case as `BLOCKED-LATE-REPLY-TIMEOUT` separately
from real findings.

Also: extract the polling into `tools/agent_smoke/bridge_client.py`
so all runners can share it.
