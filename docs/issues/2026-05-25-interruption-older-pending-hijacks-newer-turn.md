---
kind: active_issue
status: resolved
surface:
  - agent-runner
  - tools/agent_smoke
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Interruption Does Not Let Superseding Turn Dominate

## What Happened

The interruption smoke sent a long first request, then sent a superseding
second request within 500ms:

- `帮我把这周每天 9 点都设个喝水提醒，再给我推荐 5 个健康早餐`
- `等一下，先取消刚才说的，改成只设周一 9 点提醒`

In the first run, the second inputmessage was marked handled with
`rollback_count=4`, produced no assistant output, and did not create the
corrected Monday reminder. The older first turn later completed and wrote a
reminder plus breakfast reply.

After fixing the older-pending rollback check and rerunning with both messages
on the same `business_conversation_key`, the batch still failed. The worker
processed both user messages together, but the output was bound to the first
causal inbound event, not the superseding second event. The reply also failed to
create the corrected Monday 9am water reminder.

## Why It Matters

The interruption contract is that newer user input dominates older in-flight
work. Treating an older pending message as a new interrupt causes the newer
correction to starve, then lets the stale request commit durable reminder state.
Binding the combined-turn output to the first causal event also means the
request-response caller for the superseding message never receives the reply.

## Affected Surfaces

- `agent.runner.rollback_detection`
- `agent.runner.agent_handler`
- `tools/agent_smoke/_runner_phase_interruption.py`

## Evidence

- Failed smoke batch: `interruption-20260525t081003Z`.
- Mongo `inputmessages`:
  - first event `smoke_evt_66722bb36d844976af14cd9f570c1143`, status `handled`
  - second event `smoke_evt_e87066818edb44f38fd6cfd0110c6360`, status `handled`,
    `rollback_count=4`
- Mongo `outputmessages` had only the first event's breakfast/reminder reply.
- Mongo `reminders` had an active `喝水` reminder from the stale first request.
- Logs showed the second event repeatedly rolling back before agent runtime.
- Failed same-conversation smoke batch: `interruption-20260525t081535Z`.
- Same-conversation Mongo evidence:
  - both inputmessages used
    `business_conversation_key=smoke-interruption:ck_smoke_interruption20260525t081535z_alice`
  - one outputmessage was written with first causal event
    `smoke_evt_4fdebcf5b901489fa0068b2c92a370a3`
  - no outputmessage was written for second causal event
    `smoke_evt_f9c2c52f91f842878d83169e6677c370`
  - Mongo `reminders` count was `0`, so the corrected Monday 9am water reminder
    was not created

## Current Status

- Resolved. Rollback detection now ignores pending or handled
  messages older than the current message and only treats later user messages as
  interrupts.
- The smoke runner records late Mongo outputs, verifies the second event's
  causal binding, checks active reminders, and uses the correct Postgres
  customer id column.
- Batched request-response replies bind to the latest request-response inbound
  event.
- Superseding batched reminder creates now use the reminder domain's grounded
  visible summary, so stale free-form text from the interrupted first request is
  not echoed.
- Rolled-back visible reminder creates are compensated by cancelling the
  reminder written by the discarded older turn.

## Resolution

- Partial fix commit: included in the scenario commit `smoke(interruption): expose superseding turn gaps`.
- Resolution commit: `34892737`.
- Verified green at 2026-05-25:
  `.venv/bin/python -m pytest tests/unit/runner/test_agent_handler_inflight_interrupt.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_message_util_clawscale_routing.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_agent_runtime_construction.py -q`
  passed with `168 passed`.
- Verified green at 2026-05-25:
  `.venv/bin/python -m tools.agent_smoke._runner_phase_interruption` passed with
  `VERDICT=PASSED`; evidence:
  `artifacts/evidence/shared-reminder-agent-smoke/interruption-interruption-20260525t133035Z.json`.
  Mongo showed the stale 2026-05-26 reminder cancelled and the corrected
  2026-06-01 周一 09:00 reminder active. Postgres snapshot showed one smoke
  customer and no stray shared-reminder/block rows. Gateway/bridge logs showed
  the two inbound bridge calls returning 200 and the late ClawScale reply linked
  to second causal event `smoke_evt_9027cc20d1094c55ac2acd14d045a827`.
