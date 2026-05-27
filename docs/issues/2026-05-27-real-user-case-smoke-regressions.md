---
kind: issue
status: resolved
title: Real-user corpus smoke found pending-message aggregation and false shared-reminder accept
created_at: 2026-05-27T05:17:37Z
updated_at: 2026-05-27T06:00:39Z
severity: high
surface:
  - agent-runtime
  - scheduling-domain
  - production-smoke
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-realcase-corpus-smoke.md
---

# Real-User Corpus Smoke Regressions

## Context

Production real-user smoke used the existing `olivers` and `李梓豪` accounts
against the GCP compose stack. Cases were selected from repository real-case
sources, including `scripts/reminder_test_cases.json` and the existing
`tools/agent_smoke` shared-reminder runners.

Two markers were used:

- Rapid multi-case batch: `realcase-20260527T050717Z`
- Single-message control: `realcase-single-20260527T051900Z`

All future reminders and marked shared-reminder rows created by the control
case were cleaned up after verification.

## Findings

### 1. Rapid same-conversation messages are re-aggregated and lose outputs

Five real cases were sent sequentially through production `/bridge/inbound` as
`olivers`:

1. Coach-booking style refusal case.
2. Batched personal reminders.
3. Typo/noisy personal reminder.
4. Friend availability query for `李梓豪`.
5. Shared reminder create for `李梓豪`.

Each bridge request returned the 25-second placeholder:

`正在处理中，稍后把结果发给你。`

Production logs then showed the worker repeatedly aggregating previous pending
messages into later turns for the same conversation:

- first turn: `count=1`
- later turn: `count=3`
- later turn: `count=4`
- final turn: `count=5`

Mongo confirmed all five inputs ended as `status=handled`, but only the final
shared-create input had an output message. The first four inputs had no
corresponding `outputmessages` rows. The input documents also had rollback
counts: first input `rollback_count=3`, second and third `2`, fourth `1`.

Postgres confirmed no marked shared reminder and no product notification were
created for the rapid marker. Mongo confirmed no active marked reminder
remained.

Initial code correlation:

- `agent/runner/message_processor.py:125` reads top messages with
  `status="pending"`.
- `agent/runner/message_processor.py:283` then reads all same-conversation
  pending messages and aggregates them.
- `agent/runner/message_processor.py:632` increments rollback counts without
  marking those messages as claimed/processing.
- `agent/runner/message_processor.py:740` marks aggregated inputs handled only
  after final success.

The likely failure mode is that slow request/response turns keep earlier inputs
visible as `pending` long enough for later workers to reselect and re-aggregate
them. This pollutes later intent resolution, triggers rollback compensation,
and can mark earlier user inputs handled without producing user-visible output.

### 2. Natural-language shared-reminder accept can falsely confirm success

The single-message control created a marked shared-reminder request
`cmpnm2asz000jpl1tnywoqyft` for `李梓豪`. Creation still missed the 25-second
sync window, but the async path successfully created the request and delivered
the invite notification.

`李梓豪` then sent a natural-language accept:

`接受 olivers 发来的「羽毛球-realcase-single-20260527T051900Z」共享提醒。`

The user-visible reply was a success confirmation:

`收到，你已经接受了 olivers 的「羽毛球-realcase-single-20260527T051900Z」共享提醒，记下了～`

But Postgres still showed:

- `shared_reminder_requests.status = pending_invitee_confirmation`
- `invitee_reminder_id` empty
- no requester-side `shared_reminder_accepted` notification

Mongo agent session showed the tool result was actually a failure:

- `outcome='failed'`
- `error.code='invalid_scheduling_intent'`
- `reply_contract.intent='report_failure'`
- `reply_contract.prohibited_claims=['appointment_confirmed']`

The final assistant response violated that domain result contract and claimed
the accept succeeded anyway.

Gateway isolation then called canonical
`accept_shared_reminder(request_id=cmpnm2asz000jpl1tnywoqyft)` directly. That
succeeded, changed the request to `accepted`, created both reminder projections,
and delivered `shared_reminder_accepted` to `olivers`. So the gateway and
notification chain are healthy; the bug is in agent intent shape and/or
post-tool failure reply enforcement.

Initial code correlation:

- `agent/agno_agent/runtime/agent_runtime.py:754` normalizes
  `scheduling_domain(intent=...)`; invalid shapes return a failed domain result.
- `agent/agno_agent/runtime/execution_agents.py:178` makes failed scheduling
  results use `reply_contract.intent='report_failure'` and prohibits
  appointment confirmation claims.

## Impact

- A real user can send multiple normal messages in sequence and get only
  placeholders or lose replies for earlier actions.
- A shared-reminder accept can tell the invitee it succeeded while the request
  stays pending and the requester never receives an accepted notification.
- The false accept is especially risky because the user-facing state diverges
  from durable state.

## Cleanup Evidence

- Marked Postgres shared requests and product notifications for both markers:
  `0`.
- Marked active Mongo reminders for both markers: none.
- The single-control request notifications were deleted after reminder
  cancellation.

## Next Repair Direction

Completed in this repair:

1. Added regression coverage for same-conversation ClawScale
   `request_response` turns. Direct sync turns now stay isolated per
   `causal_inbound_event_id`, then per `sync_reply_token`, then per input
   message id.
2. Updated rollback detection so an in-flight ClawScale sync turn is not
   interrupted by another ClawScale sync turn from the same business
   conversation. Non-request/response messages still interrupt as before.
3. Normalized the model-observed shared-reminder accept shape
   `{"inviter": "...", "shared_reminder_request_action": "accept"}` to the
   canonical `accept_shared_reminder` intent with `requester_name`.
4. Added action-specific final-text guardrails: a reply may not claim a shared
   reminder accept succeeded unless an `accept_shared_reminder` write actually
   succeeded.
5. Left the gateway canonical accept path unchanged.

## Fix Verification

Local verification before deploy:

- `zsh scripts/check`
- `.venv/bin/python -m pytest tests/unit/runner/ -v`
- `.venv/bin/python -m pytest tests/unit/agent/ -v`
- `.venv/bin/python -m pytest tests/unit/test_clawscale_only_topology.py -v`
- `zsh scripts/review-trigger --base HEAD~1`: `human_review_required: no`
- `git diff --check`

Deployment:

- `./scripts/deploy-compose-to-gcp.sh --restart`
- Remote health and public site checks passed.

Production real-user verification after deploy:

- Rapid marker `fix-rapid-20260527T055333Z`: three concurrent real messages
  from `olivers` each logged `count=1`, all three inputs became `handled`, and
  three outputs were produced, each bound to its own causal event. No earlier
  input was swallowed by a later turn.
- Shared marker `fix-shared-20260527T055525Z`: `olivers` created a shared
  reminder for `李梓豪`; invite notification was delivered. `李梓豪` then accepted
  via natural language, and the request changed to `accepted`, an invitee
  reminder was created, and the requester received a delivered
  `shared_reminder_accepted` notification.
- Cleanup completed: both future reminder projections were cancelled, the
  exact marked shared request was deleted, and final Postgres checks showed
  `0` shared rows and `0` product notifications for the marker.
