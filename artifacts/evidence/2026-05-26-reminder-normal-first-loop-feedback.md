# Reminder Normal First Trace Feedback Loop

Date: 2026-05-26

Scope:

- `scripts/reminder_eval/runner.py`
- `agent/runner/agent_handler.py`
- `agent/agno_agent/runtime/agent_runtime.py`
- `agent/agno_agent/adapters/reminder_command_executor.py`
- `scripts/analyze_agent_turn_traces.py`
- `tests/evals/test_reminder_eval_runner.py`
- `tests/unit/agent/test_agent_handler.py`
- `tests/unit/agent/test_agent_runtime_construction.py`
- `tests/unit/agent/test_reminder_command_executor.py`
- `tests/unit/test_agent_turn_trace_analyzer.py`

## Loop Summary

The first full `reminder-normal` eval attempt was stopped after it produced no
output and no trace artifact within the expected time window. A smaller
three-case run was used to close the first feedback loop.

Initial small run:

- Command: `COKE_AGENT_TURN_TRACE_PROFILE=eval COKE_AGENT_TURN_TRACE_CONTENT=full COKE_AGENT_TURN_TRACE_SUITE=reminder-normal COKE_AGENT_TURN_TRACE_RUN_ID=reminder-normal-first-loop-small .venv/bin/python scripts/run_reminder_eval.py --limit 3 --continue-on-failure --case-timeout-seconds 90 --output artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-eval.json`
- Result: `total=3`, `passed=0`, `failed=3`.
- The eval summary pointed at `artifacts/evidence/agent-turn-traces/reminder-normal/reminder-normal-420eab2b8d.jsonl`, but that trace file did not exist.

Root cause:

- The eval driver process had the trace environment, but the long-running PM2
  worker did not inherit it.
- The eval request metadata already carried evaluation identity, but the worker
  runtime metadata extractor did not forward `source_eval` or an agent trace
  sink.

Fixes made:

- Eval runner now adds `metadata.agent_turn_trace = {suite, run_id}` to each
  submitted turn.
- `agent_handler` now whitelists eval trace metadata into runtime metadata.
- Runtime trace emission now falls back to `runtime_metadata.agent_turn_trace`
  when no trace env var is present.
- Domain visible output now joins all successful operation summaries from a
  single executed domain result.
- Runtime trace `selected_tool_names` now maps domain names to exposed tool
  names such as `reminder_domain`.
- Recurring reminder create summaries now show a recurring label, for example
  `已创建提醒：锻炼（每天 17:58）`.
- Code review found that daily-only recurring formatting would leave weekly and
  hourly RRULEs looking like one-shot reminders. The recurring label helper now
  covers daily, weekly, hourly, minutely, monthly, and unknown recurring rules.

## Compare Runs

Second small run after trace metadata propagation:

- Command: `.venv/bin/python scripts/run_reminder_eval.py --limit 3 --batch-id reminder-normal-first-loop-small-2 --continue-on-failure --case-timeout-seconds 90 --output artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-2-eval.json`
- Result: `total=3`, `passed=0`, `failed=3`.
- Trace generated: `artifacts/evidence/agent-turn-traces/reminder-normal/reminder-normal-first-loop-small-2.jsonl`.
- Analyzer output: `artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-2-analysis.json`.
- Analyzer found `status_counts.ok=3`, `route_counts.reminder_domain=3`, and a trace naming mismatch where selected tools were recorded as `reminder`.
- Manual trace inspection showed the first two cases created two reminders but the visible output included only the first operation summary.

Third small run after joining multiple operation summaries and aligning selected tool names:

- Command: `.venv/bin/python scripts/run_reminder_eval.py --limit 3 --batch-id reminder-normal-first-loop-small-3 --continue-on-failure --case-timeout-seconds 90 --output artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-3-eval.json`
- Result: `total=3`, `passed=0`, `failed=3`.
- Errors improved from missing title to recurring-format mismatch for cases 0
  and 1, plus title normalization for case 2.
- Analyzer output: `artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-3-analysis.json`.
- Analyzer now reported `selected_tool_counts.reminder_domain=3`.

Fourth small run after recurring visible summary fix:

- Command: `.venv/bin/python scripts/run_reminder_eval.py --limit 3 --batch-id reminder-normal-first-loop-small-4 --continue-on-failure --case-timeout-seconds 90 --output artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-4-eval.json`
- Result: `total=3`, `passed=2`, `failed=1`, `pass_rate=0.6666666666666666`.
- Critical cases: `total=2`, `passed=2`, `failed=0`.
- Remaining failure: `missing_expected_reminder_title:学英语`; the created title is still `学英语么`.
- Trace generated: `artifacts/evidence/agent-turn-traces/reminder-normal/reminder-normal-first-loop-small-4.jsonl`.
- Analyzer output: `artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-4-analysis.json`.

Fifth small run after code-review fix for non-daily recurring labels:

- Command: `.venv/bin/python scripts/run_reminder_eval.py --limit 3 --batch-id reminder-normal-first-loop-small-5 --continue-on-failure --case-timeout-seconds 90 --output artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-5-eval.json`
- Result: `total=3`, `passed=2`, `failed=1`, `pass_rate=0.6666666666666666`.
- Critical cases: `total=2`, `passed=2`, `failed=0`.
- Remaining failure: `missing_expected_reminder_title:学英语`; the created title is still `学英语么`.
- Trace generated: `artifacts/evidence/agent-turn-traces/reminder-normal/reminder-normal-first-loop-small-5.jsonl`.
- Analyzer output: `artifacts/evidence/2026-05-26-reminder-normal-first-loop-small-5-analysis.json`.

Small-5 analyzer summary:

```json
{
  "record_count": 3,
  "invalid_record_count": 0,
  "route_counts": {"reminder_domain": 3},
  "status_counts": {"ok": 3},
  "output_source_counts": {"domain_summary": 3},
  "selected_tool_counts": {"reminder_domain": 3},
  "unused_exposed_tool_counts": {
    "calendar_import": 3,
    "scheduling_domain": 3,
    "timezone": 3,
    "url_context": 3
  }
}
```

## Verification

Focused regression:

```text
.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py::test_agent_handler_extracts_product_notification_metadata_for_runtime tests/unit/agent/test_agent_handler.py::test_agent_handler_extracts_eval_trace_metadata_for_runtime tests/evals/test_reminder_eval_runner.py::test_submit_cases_can_write_clawscale_request_response_envelope tests/evals/test_reminder_eval_runner.py::test_main_writes_default_evidence_and_uses_serial_batches tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_returns_agent_run_result_for_no_tool_run tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_emits_trace_from_runtime_metadata_without_env tests/unit/agent/test_agent_runtime_construction.py::test_resolve_domain_visible_text_joins_multiple_successful_operation_summaries tests/unit/agent/test_agent_runtime_construction.py::test_selected_tool_names_match_exposed_domain_tool_names tests/unit/agent/test_reminder_command_executor.py::test_recurring_create_visible_summary_uses_recurring_time_label tests/unit/test_agent_turn_trace_analyzer.py -q
12 passed in 2.16s
```

Focused regression after code-review fix:

```text
.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py::test_agent_handler_extracts_product_notification_metadata_for_runtime tests/unit/agent/test_agent_handler.py::test_agent_handler_extracts_eval_trace_metadata_for_runtime tests/evals/test_reminder_eval_runner.py::test_submit_cases_can_write_clawscale_request_response_envelope tests/evals/test_reminder_eval_runner.py::test_main_writes_default_evidence_and_uses_serial_batches tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_returns_agent_run_result_for_no_tool_run tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_emits_trace_from_runtime_metadata_without_env tests/unit/agent/test_agent_runtime_construction.py::test_resolve_domain_visible_text_joins_multiple_successful_operation_summaries tests/unit/agent/test_agent_runtime_construction.py::test_selected_tool_names_match_exposed_domain_tool_names tests/unit/agent/test_reminder_command_executor.py::test_recurring_create_visible_summary_uses_recurring_time_label tests/unit/agent/test_reminder_command_executor.py::test_weekly_recurring_create_visible_summary_uses_weekly_label tests/unit/agent/test_reminder_command_executor.py::test_hourly_recurring_create_visible_summary_keeps_recurring_label tests/unit/test_agent_turn_trace_analyzer.py -q
14 passed in 2.20s
```

Diff whitespace check:

```text
git diff --check
passed with no output
```

Diff-aware routing:

```text
zsh scripts/suggest-verification --base HEAD~1
changed_surfaces: repo-os-docs worker-runtime
suggested_command: zsh scripts/verify-surface repo-os-docs worker-runtime
```

Suggested surface verification:

```text
zsh scripts/verify-surface repo-os-docs worker-runtime
check passed
67 passed in 2.32s
505 passed in 5.00s
7 passed in 0.21s
```

Review trigger before this evidence file existed:

```text
zsh scripts/review-trigger --base HEAD~1
human_review_required: yes
- sensitive_repo_os_change
- oversized_change
- evidence_gap
```

The evidence gap was expected before this file was written. The sensitive
repo-OS and oversized-change findings are influenced by the dirty worktree and
the prior repo-OS trace analyzer commit included in `HEAD~1` comparison.

## Next Candidate

The next feedback-loop target is the remaining title-normalization failure:
`学英语么` should normalize to `学英语` for the relevant reminder-normal case.
