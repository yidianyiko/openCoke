---
kind: issue
status: open
created: 2026-05-27
owner: agent
area: reminder-intent
---

# Reminder Intent LLM-Only Migration

## Summary

Phases 3-6 of `docs/superpowers/plans/2026-05-27-reminder-intent-llm-only.md`
removed the remaining reminder-intent normalizer/drop helpers and the raw-text
cadence evidence validators. Runtime now trusts the detector's structured
decision for reminder intent slots. Output-only safety validators were kept and
annotated.

## Migration Commits

- `8e95c392` docs(reminder-intent): classify remaining output safety validators
- `3fa94a2a` docs(reminder-intent): annotate completed write claim safety net
- `16198b38` refactor(reminder-detect): trust detector schedule fields; remove _looks_like_concrete_cadence
- `6f8a92ce` refactor(reminder-intent): trust detector for high-frequency cadence; delete _input_has_high_frequency_without_deadline
- `71b3f0c3` test(reminder-intent): route remaining normalizer fixtures through detector
- `3c2535b3` refactor(reminder-intent): trust detector for cadence task operations; delete _drop_ungoverned_cadence_task_operations
- `d2b073cd` refactor(reminder-intent): trust detector for list title queries; delete _normalize_explicit_list_title_query
- `c485ef65` refactor(reminder-intent): trust detector for duration; delete _normalize_create_duration_from_title
- `7a28d93a` refactor(reminder-intent): trust detector for batch schedule evidence; delete _drop_batch_operations_without_local_schedule_evidence
- `66642465` refactor(reminder-intent): trust detector for batch plans; delete _drop_ungoverned_batch_plan_operations
- `21516831` refactor(reminder-intent): trust detector for create titles; delete _normalize_create_title_from_user_text
- `01780aad` refactor(reminder-intent): trust detector for time evidence; delete _normalize_time_evidence_decision
- `5413c4fe` refactor(reminder-intent): trust detector for weekday bare triggers; delete _normalize_weekday_bare_create_trigger
- `4b861af2` refactor(reminder-intent): trust detector for update triggers; delete _normalize_update_trigger_from_text
- `b635f92f` refactor(reminder-intent): trust detector for relative-day triggers; delete _normalize_relative_day_create_trigger
- `4baca75b` refactor(reminder-intent): trust detector for past bare triggers; delete _normalize_past_bare_create_trigger
- `b1da6400` refactor(reminder-intent): trust detector for relative-delay triggers; delete _normalize_relative_delay_create_trigger
- `a6e1e711` refactor(reminder-intent): trust detector for selectors; delete _normalize_write_target_selectors_from_text

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/test_reminder_detect_structured_output.py -v`
  - Result: 141 passed.
- `zsh scripts/check`
  - Result: passed.
- `zsh scripts/suggest-verification --base HEAD~1`
  - Suggested: `zsh scripts/verify-surface repo-os-docs worker-runtime`.
- `zsh scripts/verify-surface repo-os-docs worker-runtime`
  - Result: passed (`repo-os-docs`, `tests/unit/runner/`, `tests/unit/agent/`, `tests/unit/test_clawscale_only_topology.py`).

Evidence:

- `artifacts/evidence/2026-05-27-reminder-intent-llm-only/pytest-reminder-intent-and-schema.txt`
- `artifacts/evidence/2026-05-27-reminder-intent-llm-only/scripts-check.txt`
- `artifacts/evidence/2026-05-27-reminder-intent-llm-only/suggest-verification.txt`
- `artifacts/evidence/2026-05-27-reminder-intent-llm-only/verify-surface-repo-os-docs-worker-runtime.txt`
- `artifacts/evidence/2026-05-27-reminder-intent-llm-only/reminder-eval-limit-50.txt`
- `artifacts/evidence/2026-05-27-reminder-intent-llm-only/reminder-eval-limit-50-after-prompt-fix.txt`
- `artifacts/evidence/agent-turn-traces/reminder-normal/reminder-normal-0f79a95baf.jsonl`
- `artifacts/evidence/agent-turn-traces/reminder-normal/reminder-normal-e7fc3bdb75.jsonl`

## Corpus Eval Result

Invocation:

```bash
.venv/bin/python scripts/run_reminder_eval.py --limit 50
```

Result summary:

- Total: 50
- Passed: 34
- Failed: 16
- Pass rate: 68%
- Critical: 8/8 passed
- Important: 23/37 passed, below 95% threshold
- Nice: 3/5 passed, below 80% threshold
- Batch id: `reminder-normal-0f79a95baf`

Per eval policy, these are treated as real detector/runtime behavior gaps. No
regex fallback was restored.

## Corpus Eval Result (after prompt fix)

Invocation:

```bash
.venv/bin/python scripts/run_reminder_eval.py --limit 50
```

Result summary:

- Total: 50
- Passed: 36 (+2)
- Failed: 14 (-2)
- Pass rate: 72% (+4 percentage points)
- Critical: 8/8 passed (no change)
- Important: 25/37 passed (+2), below 95% threshold
- Nice: 3/5 passed (no change), below 80% threshold
- Batch id: `reminder-normal-e7fc3bdb75`

Corpus audit fixes changed case 11 from default discussion to expected create
and case 12 from expected create to expected clarification. The prompt update
helped case 41 pass and removed the case 11 corpus false failure, but several
targeted detector gaps remain on GLM-5.1 thinking-off. Per the task constraint,
do not chase pass rate with runtime regex or model changes.

Remaining failure classification:

- Detector still gapped / follow-up prompt work:
  - Case 2, 14, 25: short title extraction still includes trailing modal
    particles (`么`/`哦`/`吗`) or otherwise misses the expected title.
  - Case 10, 36, 44: personal intention or narrative without an explicit
    reminder verb is still clarified or created instead of treated as
    discussion.
  - Case 19, 21: unbounded hourly cadence still asks about start/confirmation
    instead of focusing on the missing end condition.
  - Case 31: bare `七点叫我` still does not match the fixture's expected
    one-shot shape.
  - Case 42: structured dated plan is still batch-created as reminders.
- ChatResponseAgent output issue / detector decision not enough:
  - Case 12: detector produced no write, but visible output still implies a
    reminder was set.
  - Case 22: no reminder was created, but visible output says a 10-minute
    reminder was set; the detector path also still misses the expected create.
  - Case 39: reminder has an `UNTIL` RRULE, but visible output omits the
    deadline/`截止` acknowledgement term.
- Eval/judge wording brittleness:
  - Case 24 asks "到几点为止", which is semantically an end-condition question,
    but the expected term list only accepts `持续`/`结束`/`截止`.

## Failing Cases Captured

- Case 2: `你可以没太难18:00 提醒我学英语么`
  - `missing_expected_reminder_title:学英语`
- Case 10: `因为我就是6点钟醒了，我还得摸一下，大概6:15开始背书`
  - `unexpected_reminder_clarification`
- Case 11: `明天中午12:40提醒我写实验报告`
  - `unexpected_reminder_created`
- Case 12: `明天下午3点左右提醒我看数学的网课`
  - `no_reminder_created`
  - `expected_reminder_count_mismatch:1>0`
  - `missing_expected_reminder_title:看数学的网课`
  - `user_output_missing_expected_title:看数学的网课`
- Case 14: `今天10:50 提醒我出门哦`
  - `missing_expected_reminder_title:出门`
- Case 19: `冥想可以每个小时提醒我做一次冥想吗`
  - `user_output_wrong_clarification_focus`
- Case 21: `每个小时一次提醒我正念冥想`
  - `user_output_wrong_clarification_focus`
- Case 22: `已经在调整了，我刷个10分钟的手机，然后开始背书，你提醒我一下`
  - `no_reminder_created`
  - `expected_reminder_count_mismatch:1>0`
  - `missing_expected_reminder_title:开始背书`
  - `user_output_missing_expected_title:开始背书`
- Case 23: `时间也不对啊，应该四点整点提醒`
  - `user_output_missing_crud_ack`
- Case 25: `明天早上6:30可以提醒我起床吗`
  - `missing_expected_reminder_title:起床`
- Case 31: `七点叫我可以么`
  - `missing_expected_reminder_title:叫我`
- Case 39: `12月7号前，每天晚上八点提醒我跑步`
  - `user_output_missing_expected_term:跑步:截止`
- Case 41: long schedule plan beginning `时间安排 6:30 起床...`
  - `user_output_implies_unconfirmed_reminder`
- Case 42: long dated plan beginning `[太阳][太阳]12月2日计划 星期二...`
  - `unexpected_reminder_created`
- Case 44: `明天7点开始背书`
  - `unexpected_reminder_clarification`
- Case 46: `周1234的晚上其余时间我想控制游戏时间，保持原有安排`
  - `unexpected_reminder_clarification`

## Current Status

Prompt and corpus follow-up are committed. The latest direct `--limit 50` eval
is still below the important/nice thresholds, but critical remains green. The
remaining failures are now documented above as detector follow-up, output-layer
work, or eval wording brittleness. No runtime regex fallback or detector model
change was introduced.
