---
kind: active_issue
status: in_progress
surface:
  - agent-runtime
  - reminder-intent
  - production-smoke
created_at: 2026-05-27
updated_at: 2026-05-27
---

# 2026-05-27 Personal Reminder Fire Real-User Regression

## What Happened

Production real-user smoke used `olivers` through the live `/bridge/inbound`
path with marker `fire-real-20260527T073551Z`.

Input:

```text
2分钟后提醒我喝水-fire-real-20260527T073551Z。
```

The bridge returned the asynchronous placeholder. The late output message said:

```text
提醒已创建：喝水-fire-real-20260527T073551Z，今天下午3点39分提醒。
```

Mongo evidence contradicted that visible claim:

- `inputmessages` had one handled marked input.
- `outputmessages` had one handled marked output with the success text above.
- `reminders` had zero documents whose title contained the marker.
- `agent_sessions` recorded one `reminder_domain` tool call with a failed
  update operation and `reply_contract.prohibited_claims=['reminder_created']`.

The failed tool result was:

```text
AmbiguousReminderKeyword: 更新提醒失败：没有找到要更新的提醒，请告诉我提醒名称。
```

## Root Cause

There were two independent defects in the same turn:

1. ReminderDetect misrouted a clear create request as an update when the
   reminder title contained an id-like hyphenated suffix. The detector supplied
   `reminder_id='fire-real-20260527T073551Z'`, so the reminder runtime tried to
   update a nonexistent reminder instead of creating a new one.
2. `run_agent_runtime` did not enforce domain `reply_contract.prohibited_claims`
   against the final model text. The failed domain result explicitly prohibited
   `reminder_created`, but the model still emitted a create-success reply and
   the runtime delivered it.

## Fix Plan

- Add a runtime contract guard that checks domain result prohibited claims
  against the final visible text and fails closed on violations.
- Repair ReminderDetect update decisions back to create when the current user
  turn has create-style reminder wording, concrete schedule evidence, no update
  verb, and the detector already supplied a usable title plus trigger time.
- Keep referential update behavior intact for real update turns such as
  "再过 10 分钟提醒我" when the detector targets a recent active reminder.
- Deploy, rerun the same real-account production flow, verify the reminder row
  is actually created, wait for the fire path, and clean up only marked data if
  a future active reminder remains.

## Verification So Far

Focused regression tests:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_output_rules.py::test_failed_reminder_domain_result_blocks_created_claim \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_repairs_create_request_misrouted_as_update \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_referential_relative_delay_update_from_detector \
  -q
```

Result: passed.
