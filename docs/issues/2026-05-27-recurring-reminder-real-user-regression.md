---
kind: progress_note
status: resolved
title: Recurring personal reminder real-user smoke exposed schedule authorization and inclusive deadline bugs
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - agent-runtime
  - reminder-runtime
  - production-smoke
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-personal-crud-happy-path-smoke.md
---

# Recurring Personal Reminder Real-User Regression

## Problem

Production real-user smoke with `olivers` found two recurring reminder issues.

1. `happy-recurring-20260527T103400Z`: create succeeded, but update did not
   execute. The model asked for confirmation instead of writing the update.
2. `happy-recurring-fix-20260527T105900Z`: update/cancel worked after the first
   fix, but create acknowledged `截止2029年1月28日` for a user request ending
   `2029年1月29日`.

## Root Cause

The first failure was a ReminderDetect structured-output contract gap. For a
recurring update, the detector emitted recurrence/deadline fields but omitted
`schedule_basis` and `schedule_evidence`, so the schema rejected the decision:
`multi-occurrence or bounded schedules require explicit schedule_basis`.

The second failure was a bounded-cadence semantics gap. The prompt did not state
that an end date is inclusive, so the detector could choose a deadline one
occurrence too early.

## Fix

- ReminderDetect instructions now state that for create, update, or batch, any
  `rrule` or `deadline_at` requires `schedule_basis` and `schedule_evidence`.
- The schema field descriptions repeat the same general contract.
- ReminderDetect instructions now state that bounded cadence end dates are
  inclusive and `deadline_at` should use the final occurrence clock.

No Python natural-language parser or case-specific rule was added.

## Verification

Local:

```bash
.venv/bin/python -m pytest \
  tests/unit/prompt/test_agent_instructions_prompt.py \
  tests/unit/prompt/test_prompt_token_budgets.py \
  tests/unit/agent/test_chat_response_instructions.py \
  tests/unit/agent/test_chat_response_scheduling_instructions.py \
  tests/unit/test_reminder_detect_structured_output.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_agent_runtime_construction.py \
  tests/unit/agent/test_agent_runtime_output_rules.py -q
```

Result: `307 passed`.

Production:

- Deployed with `./scripts/deploy-compose-to-gcp.sh --restart`.
- Final passing marker: `happy-recurring-fix2-20260527T111900Z`.
- Create reply and durable RRULE both ended on `2029-01-29`.
- Update reply and durable RRULE both ended on `2029-01-29`.
- Cancel left `lifecycle_state=cancelled`, `next_fire_at=null`, and
  `REMAINING_ACTIVE=0`.
