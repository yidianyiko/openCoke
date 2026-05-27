---
kind: active_issue
status: in_progress
surface:
  - agent-runtime
  - reminder-detect
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

- Keep the runtime contract guard that checks domain result prohibited claims
  against the final visible text and fails closed on violations.
- Do not repair ReminderDetect update decisions inside
  `ReminderIntentPort`. That is semantic routing code in the capability layer
  and violates the prompt-rule ownership contract.
- Move the remaining create-vs-update defect to the ReminderDetect owner:
  detector instructions clarify create wording and id-source policy, and the
  structured schema rejects create decisions that carry `reminder_id`.
- Keep referential update behavior intact for real update turns such as
  "再过 10 分钟提醒我" when the detector targets a recent active reminder.
- Deploy, rerun the same real-account production flow, verify the reminder row
  is actually created, wait for the fire path, and clean up only marked data if
  a future active reminder remains.

## Verification So Far

Initial fix `0c91e874` was deployed and verified to prevent the false success
claim: the repeated production marker `fire-fix-20260527T080904Z` returned the
safe fallback text instead of "提醒已创建" when the domain result was a failed
update. It did not fix reminder creation.

The first local follow-up added a rule-based repair in
`ReminderIntentPort`. Architecture review rejected that layer: natural-language
create/update routing belongs to ReminderDetect prompt/schema/eval, not a
runtime heuristic in the capability port. That repair and its tests were
removed.

Focused regression tests:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_output_rules.py::test_failed_reminder_domain_result_blocks_created_claim \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_repairs_create_request_misrouted_as_update \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_referential_relative_delay_update_from_detector \
  -q
```

Result: passed.

Architecture-aligned red/green tests added:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_schema_rejects_create_with_reminder_id \
  tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_schema_rejects_batch_create_operation_with_reminder_id \
  tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_reminder_id_schema_limits_ids_to_existing_context \
  tests/unit/prompt/test_agent_instructions_prompt.py::test_reminder_detect_instructions_own_create_routing_and_id_source \
  -q
```

Red result before the fix: all 4 failed because schema accepted
create+`reminder_id` and the prompt lacked the id-source/create-routing
contract.

Green result after the fix: all 4 passed.

Focused and surface verification after architecture-aligned repair:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_reminder_detect_structured_output.py \
  tests/unit/prompt/test_agent_instructions_prompt.py \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_referential_relative_delay_update_from_detector \
  tests/unit/agent/test_agent_runtime_output_rules.py::test_failed_reminder_domain_result_blocks_created_claim \
  -q
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -q
git diff --check
zsh scripts/verify-surface repo-os-docs worker-runtime
zsh scripts/review-trigger --base HEAD~1
```

Results:

- Focused tests: 47 passed.
- Full `test_reminder_intent_capability.py`: 105 passed.
- `git diff --check`: passed.
- Surface verification: passed (`scripts/check`, 69 runner tests, 536 agent
  tests, 7 topology tests).
- `review-trigger`: `human_review_required: no`.

Evidence file:

- `artifacts/evidence/shared-reminder-agent-smoke/personal-reminder-create-routing-20260527T082116Z.md`
