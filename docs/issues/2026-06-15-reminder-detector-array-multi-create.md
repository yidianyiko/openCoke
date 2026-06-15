---
title: Reminder detector array output blocks coalesced multi-create turn
kind: incident
status: resolved
area: reminders
created: 2026-06-15
updated: 2026-06-15
---

# Reminder Detector Array Output Blocks Coalesced Multi-Create Turn

## Problem

On deployed `1d279dca`, two consecutive personal reminder create messages in
one open input window were coalesced into a single turn. The detector returned
valid JSON with the wrong top-level shape for `detected_reminder_fields`, which
raised `LLMOutputError("invalid detected_reminder_fields shape")`.

The uncaught detector parse error escaped the reminder create path, so the whole
turn closed through grounded failure recovery and replied with the runtime-owned
"please send it again" message. Neither reminder was created.

Follow-up live verification against deployed `364c61b9` showed the first fix was
insufficient. The crash became a graceful `invalid_detector_output` reply, but
DeepSeek still returned a valid two-object JSON array for the coalesced create
turn. Because the detector/create path still expected one
`DetectedReminderFields`, both reminders were rejected instead of created.

## Impact

Users can lose a whole coalesced batch of reminder creates when the detector
returns a top-level array for multiple reminder items instead of the expected
single object.

## Evidence

- Live conversation `7fed5c7c`, inbound windows `110-111` and `112-113`, sent:
  - `下周一早上9点提醒我看openCoke的测试结果`
  - `7月3号下午2点提醒我续订服务`
- Runtime error:
  `coke.llm.json_completion.LLMOutputError: invalid detected_reminder_fields shape`
- The error text was `shape`, not `JSON`, confirming the model output parsed as
  valid JSON but was not an object.

## Resolution

Resolved. The fix is tracked by
`docs/superpowers/plans/2026-06-15-reminder-detector-array-multi-create.md`.

- Planner guidance and corpus coverage still prefer multiple personal reminder
  create requests in one open input window to become one
  `reminder.batch_create` action with one item per reminder, but execution no
  longer depends on the planner always splitting.
- The reminder handler preserves the action-level timezone for batch item
  detector calls, so coalesced items use the user's captured timezone instead
  of falling back to UTC.
- `AgnoJSONCompletionClient.complete_json()` still returns one mapping, while
  `complete_json_list()` accepts a non-empty list of mappings for callers that
  explicitly support batch detector output.
- `SiliconFlowReminderDetector.extract_many()` maps a detector array into
  multiple trusted `DetectedReminderFields`; `extract()` remains single-result
  and rejects multi-object arrays for legacy single-result callers.
- Reminder create, batch-create, and domain `detect_and_create` paths flatten a
  valid N-reminder detector result into N `ReminderBatchItem`s and execute them
  through the existing batch service.
- Reminder create, batch-create, and time-phrase update handlers convert
  detector `LLMOutputError` into a typed `invalid_detector_output` outcome
  rather than letting it escape to turn-level grounded recovery.

## Other Detector Scope

The shared `AgnoJSONCompletionClient` is currently used by the planner and the
reminder detector. This change therefore also tolerates single-object wrapped
arrays for planner JSON output. Express has a separate inbound parser and is not
a detector path. No other detector-specific array handling was added.

## Verification

Passing evidence for the original `364c61b9` fix:

- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/reminder tests/unit/coke/llm -q`
  passed 395 tests with 1 database-guard skip.
- `black .` completed; formatter-only churn outside this task was reverted.
- `isort .` completed; formatter-only churn outside this task was reverted.
- `git diff --check` passed.
- `zsh scripts/suggest-verification --base HEAD~1` routed to
  `clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base HEAD~1` reported no human review required;
  medium risk triggers were docs sensitivity, oversized diff, and evidence-gap
  heuristics.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  `tests/unit/coke -v` reported 1018 passed and 1 database-guard skip, and
  `zsh scripts/check` passed.

Follow-up verification for the multi-object array fix:

- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/reminder tests/unit/coke/llm -q`
  passed 397 tests with 1 database-guard skip.
- `black . && isort .` completed; formatter-only churn outside this task was
  reverted.
- `git diff --check` passed.
- `zsh scripts/suggest-verification --base HEAD~1` routed to
  `clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base HEAD~1` reported no human review required;
  medium risk triggers were docs sensitivity, oversized diff, and evidence-gap
  heuristics.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  `tests/unit/coke -v` reported 1020 passed and 1 database-guard skip, and
  `zsh scripts/check` passed.
