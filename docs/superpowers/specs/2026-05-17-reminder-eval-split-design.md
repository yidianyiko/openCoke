# Reminder Normal-Path Eval Split Design

## Goal

Decompose `scripts/user_path_normal_eval.py` (1970 lines, ~60 top-level
defs) and its 2715-line test file into four narrowly-scoped modules so
that runner orchestration, scoring strategy, LLM judges, and dataset
shapes can each be read, tested, and changed independently.

This is a structural split only. Semantics, fixtures, expectations,
and per-case behavior are preserved byte-for-byte. Scoring rule
changes, fixture schema, and grader/parser decoupling are explicitly
out of scope and tracked as known debt.

## Constraints

- Preserve every existing scoring verdict on every case in the corpus
  (376 cases in `scripts/reminder_normal_path_expectations.json`).
- Preserve all 105 existing tests; they may be moved between files but
  not rewritten.
- Update every in-repo caller in the same change. No re-export shim
  module, no compatibility wrappers, no renamed-away stubs. Per
  CLAUDE.md and the system "no backwards-compat hacks" guidance,
  shims are themselves debt.
- Keep `scripts/` as a Python namespace package (no top-level
  `scripts/__init__.py`) to avoid affecting unrelated scripts that
  rely on the current import resolution.

## Non-goals

- Do not touch `scripts/reminder_normal_path_expectations.json`.
- Do not introduce a `Dataset` / `Solver` / `Scorer` abstraction layer
  modeled on Inspect AI or DeepEval. That is a future B-tier change.
- Do not separate "ground-truth labels" from "scorer hints" inside
  `expectations.json`. That is a future B-tier change.
- Do not remove `expected_created_reminders(text)`, the function that
  re-parses Chinese clock phrases inside the scorer. That coupling is
  the root of the grader/parser-twin problem and is recorded under
  Known Debt below.
- Do not add named subsets (`smoke-30`, `regression-50`) to the
  dataset. A future B-tier change.

## Target Layout

```
scripts/reminder_eval/
  __init__.py        # empty; marks the directory as a real package
  dataset.py         # ~250 lines
  runner.py          # ~550 lines
  scoring.py         # ~750 lines
  judges.py          # ~280 lines
scripts/run_reminder_eval.py     # CLI entry under if __name__ == "__main__"
tests/evals/
  test_reminder_eval_dataset.py  # 2 tests
  test_reminder_eval_runner.py   # ~13 tests + Mongo recording helpers
  test_reminder_eval_scoring.py  # ~90 tests + disable_live_judges fixture
```

`scripts/user_path_normal_eval.py` and
`tests/evals/test_reminder_normal_path_eval.py` are deleted.

## Module Boundaries

### `dataset.py`

Carries every shared data shape so neither runner nor scoring needs to
import the other for typing purposes.

- Constants: `DEFAULT_CASES_PATH`, `DEFAULT_EXPECTATIONS_PATH`,
  `PENDING_WORKFLOW_TWO_TURN_CASE_NAME`,
  `PENDING_WORKFLOW_TWO_TURN_TURNS`,
  `PENDING_WORKFLOW_TWO_TURN_GUARD_MODES`.
- Dataclasses: `ReminderNormalPathCase`, `ReminderNormalPathResult`,
  `CaseBatch`, `ExpectedReminderCreate`.
- Loading and merging: `load_cases`, `load_case_expectations`,
  `merge_case_expectation_metadata`.
- Selection: `select_cases`, `select_expectation_cases`,
  `iter_case_batches`, `runtime_case_index`,
  `pending_workflow_two_turn_eval_manifest`.

`ReminderNormalPathResult` lives here despite being produced by the
runner. Putting it in `runner.py` would create a cycle with
`scoring.summarize`, which consumes a list of these results.

### `runner.py`

Live-Mongo orchestration plus CLI plumbing.

- Mongo identity: `mongo_client`, `seed_normal_path_identities`,
  `normal_path_user_seed`, `normal_path_relation_seed`,
  `normal_path_user_id`.
- Timestamps: `case_input_timestamp`, `fresh_case_input_timestamp`.
- Dispatch and collection: `submit_cases`, `build_input_metadata`,
  `case_conversation_key`, `collect_results`, `build_result`,
  `build_output_query`, `build_reminder_query`,
  `resolve_case_conversation_ids`.
- Orchestration: `run_batch`.
- CLI: `_parse_args`, `default_evidence_path`, `main`, `json_safe`.

`run_batch` calls `scoring.summarize`; `build_result` calls
`scoring.validate_observations`. Those are the only
`runner → scoring` edges. Runner does not import `judges.py`
directly. Scoring imports the judge runners for its default
fallbacks (see Dependency Graph below).

### `scoring.py`

Verdicts over `(case, outputs, reminders)`. Most functions are pure, but the
clarification and unconfirmed-reminder helpers keep their existing default LLM
judge fallbacks. Those fallbacks can start judge subprocesses when no test
callable is injected.

- Entry points: `validate_observations`, `summarize`.
- Constants: `SEVERITY_THRESHOLDS` (moves here because `summarize` is
  its only consumer).
- Case accessors: `case_expected_crud_operation`,
  `case_allows_crud_clarification`, `case_evaluation_expectation`,
  `reminder_case_requires_crud`.
- Expected creation extraction: `expected_created_reminders_for_case`,
  `expected_created_reminders`, `time_match_starts_range`,
  `apply_day_period_to_hour`.
- Create validation: `validate_expected_creates`,
  `local_time_matches_expected`, `find_matching_reminder`.
- Title matching: `output_mentions_expected_title`,
  `output_created_title_candidates`, `output_segment_for_expected`,
  `expected_title_variants`, `strip_common_title_leading_verb`,
  `compact_title_light_connectors`, `compact_title_structural_de`,
  `_normalized_expected_title_variants`,
  `title_matches_expected_variants`, `_string_tuple`.
- Text utilities: `normalize_text`, `previous_clause_boundary`,
  `segment_has_recurring_signal`, `extract_expected_title`,
  `normalize_expected_title`, `duplicate_reminder_keys`.
- Output recognition: `output_mentions_crud_ack`,
  `combined_output_text`, `output_mentions_clarification`,
  `deterministic_output_mentions_clarification`,
  `output_is_pure_reminder_clarification`,
  `output_mentions_crud_operation_clarification`,
  `output_mentions_delete_target_clarification`,
  `output_implies_unconfirmed_reminder`.

`output_implies_unconfirmed_reminder` and the two clarification
output helpers stay in scoring even though they end up calling a
judge: they own the "what counts as an implied unconfirmed reminder
/ what counts as a clarification" contract. Each accepts an injected
judge callable used by tests; absent that, they fall back to the
real `judges.run_*_judge` runners (see Dependency Graph below).

### `judges.py`

Agno-Agent + multiprocess-timeout wrappers for the two LLM judges.

- Constants: `UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS`,
  `CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS`,
  `LLM_JUDGE_PROCESS_START_METHOD`.
- Pydantic schemas and exceptions:
  `UnconfirmedReminderJudgeResponse`,
  `ClarificationOutputJudgeResponse`,
  `UnconfirmedReminderJudgeTimeout`,
  `ClarificationOutputJudgeTimeout`.
- Clarification judge: `run_clarification_output_judge`,
  `build_clarification_output_judge_prompt`,
  `_parse_clarification_output_judge_response`,
  `_run_clarification_output_judge_with_timeout`,
  `_clarification_output_judge_worker`,
  `_clarification_output_judge_agent`.
- Unconfirmed-reminder judge: `run_unconfirmed_reminder_judge`,
  `build_unconfirmed_reminder_judge_prompt`,
  `_parse_unconfirmed_reminder_judge_response`,
  `_run_unconfirmed_reminder_judge_with_timeout`,
  `_unconfirmed_reminder_judge_worker`,
  `_unconfirmed_reminder_judge_agent`,
  `_create_unconfirmed_reminder_judge_model`.

## Dependency Graph

```
    dataset.py                 judges.py
    (no intra-package deps)    (no intra-package deps)
       ^      ^                  ^
       |      |                  |
       |    scoring.py ----------+
       |      ^
       |      |
    runner.py ─┘
```

Edges (no cycles):

- `runner -> dataset` for case loading, batching, result construction.
- `runner -> scoring` for `summarize` and `validate_observations`.
- `scoring -> dataset` for dataclass types.
- `scoring -> judges` for the default fallback in
  `output_implies_unconfirmed_reminder`,
  `output_mentions_clarification`, and
  `output_is_pure_reminder_clarification`. Each call site uses the
  `(injected_judge or run_*_judge)` pattern, so tests can stub the
  judges by passing a callable, while production code calls the real
  judge runners directly.
- `judges -> dataset` does not exist; `judges.py` is self-contained
  apart from external libraries (agno, pydantic, multiprocessing).

Runner does not import `judges.py`. Existing call sites pass no
judge callable, so production wiring goes runner → scoring → judges
via the fallback. The injection seam exists for tests, not for
runtime wiring.

## Test Split

| File | Source range in old test file | Contents |
|------|-------------------------------|----------|
| `test_reminder_eval_dataset.py` | L92–117 | `test_iter_case_batches_preserves_json_order_in_fixed_chunks`, `test_iter_case_batches_applies_total_limit_before_chunking` |
| `test_reminder_eval_runner.py` | L16–465 (minus the scoring tests, plus the Mongo recording helpers at L263–365) | `test_normal_path_user_id_*`, `test_normal_path_relation_seed_*`, `test_normal_path_user_seed_*`, `test_default_evidence_path_*`, `test_main_writes_default_evidence_*`, `test_case_input_timestamp_*`, `test_submit_cases_*`, `test_build_result_*`; helper classes `RecordingCollection`, `RecordingDB`, `QueryResult`, `QueryCollection`, `QueryDB`; helpers `dotted_get`, `dotted_get_parts`, `document_matches_query` |
| `test_reminder_eval_scoring.py` | L488–2715 | All `test_validate_observations_*`, `test_expected_created_reminders_*`, `test_title_*`, `test_output_title_*` (~90 tests) plus the `disable_live_reminder_eval_judges` fixture from L16 |

The `disable_live_reminder_eval_judges` fixture moves into
`test_reminder_eval_scoring.py` only, not into a shared `conftest.py`.
Runner and dataset tests do not invoke the scoring helpers that can
fall back to live judges, so they do not need judge stubs. Keeping the
fixture local makes the scope honest.

The fixture-loader and manifest tests at old lines L1473-L1570 are
dataset/fixture tests, not scoring tests:

- `test_load_cases_applies_normal_path_expectation_fixture`
- `test_run_all_uses_pruned_expectation_cases_and_preserves_raw_indices`
- `test_expectation_fixture_cases_are_current_and_well_formed`
- `test_pending_workflow_two_turn_eval_manifest_records_open_runtime_evidence`

Move those into `test_reminder_eval_dataset.py`.

No dedicated `test_reminder_eval_judges.py` is created: the judge
layer has no dedicated unit tests today, only the scoring-side
stubbing. Creating an empty file would add noise without value.

## Caller Migration (Same PR)

1. `scripts/simulate_user_path.py` — replace
   `from scripts import user_path_normal_eval as normal_eval` with:
   ```python
   from conf.config import CONF
   from scripts.reminder_eval import dataset, runner
   ```
   and rewrite the 9 `normal_eval.X` references:
   - `ReminderNormalPathCase` (2 sites), `load_cases`,
     `select_expectation_cases`, `DEFAULT_CASES_PATH` → `dataset.X`
   - `mongo_client`, `run_batch` (2 sites) → `runner.X`
   - `CONF` → bare `CONF` from the new `conf.config` import
2. `tests/evals/test_reminder_normal_path_eval.py` — delete; contents
   migrated to the three new test files.
3. `tests/unit/agent/test_severity_thresholds.py` — replace the import
   with:
   ```python
   from scripts.reminder_eval.dataset import ReminderNormalPathResult
   from scripts.reminder_eval.scoring import summarize
   ```
4. `docs/fitness/coke-verification-matrix.md` — replace
   `scripts/user_path_normal_eval.py --run-all` with
   `scripts/run_reminder_eval.py --run-all`.
5. `.agents/skills/reminder-crud-case-testing/SKILL.md` — replace
   `scripts/user_path_normal_eval.py::output_implies_unconfirmed_reminder`
   with
   `scripts/reminder_eval/scoring.py::output_implies_unconfirmed_reminder`.
   Also replace its regression-test commands that point at the deleted
   `tests/evals/test_reminder_normal_path_eval.py` with the split test glob:
   `pytest tests/evals/test_reminder_eval_*.py -v`.
6. `docs/superpowers/plans/2026-05-12-reminder-detect-prompt-diet-followups.md`
   — left untouched. Dated execution plan; CLAUDE.md's
   "historical context, dated or superseded" exception applies.

## Verification

Behaviour-preservation is the only standard.

1. Unit and eval-scoped tests:
   ```
   .venv/bin/python -m pytest tests/evals/test_reminder_eval_*.py \
       tests/unit/agent/test_severity_thresholds.py -v
   ```
   Expected: all 105 prior tests pass; only file locations changed.
2. Smoke subset run (matches the user's standing 30–50 case
   preference recorded in memory):
   ```
   .venv/bin/python scripts/user_path_normal_eval.py --limit 30 \
       --output artifacts/evidence/reminder-normal/pre-split-eval-split-baseline.json
   .venv/bin/python scripts/run_reminder_eval.py --limit 30
   ```
   These are live-model smoke runs; separate executions can legitimately
   produce different user-visible outputs. Do not treat different live
   verdicts as split-regression proof unless the captured observations are the
   same.
3. Deterministic scorer preservation:
   ```
   git show HEAD:scripts/user_path_normal_eval.py > /tmp/user_path_normal_eval_pre_split.py
   .venv/bin/python - <<'PY'
   import importlib.util, json, sys
   from pathlib import Path
   from scripts.reminder_eval import scoring as new_scoring
   from scripts.reminder_eval.dataset import ReminderNormalPathCase

   spec = importlib.util.spec_from_file_location("pre_split_eval", "/tmp/user_path_normal_eval_pre_split.py")
   old = importlib.util.module_from_spec(spec)
   sys.modules["pre_split_eval"] = old
   spec.loader.exec_module(old)

   payload = json.loads(Path("artifacts/evidence/reminder-normal/post-split-eval-split-baseline.json").read_text())
   old_cases = old.load_cases()
   new_cases = [
       ReminderNormalPathCase(case.input, case.expected_intent, case.matched_keywords, case.metadata)
       for case in old_cases
   ]
   clarification_judge = lambda _case_input, output_text: any(marker in output_text for marker in ("?", "？", "吗", "呢"))
   unconfirmed_judge = lambda _text: False
   for result in payload["results"]:
       index = result["index"]
       old_errors = old.validate_observations(old_cases[index], result["input_status"], result["outputs"], result["reminders"], clarification_judge=clarification_judge, unconfirmed_reminder_judge=unconfirmed_judge)
       new_errors = new_scoring.validate_observations(new_cases[index], result["input_status"], result["outputs"], result["reminders"], clarification_judge=clarification_judge, unconfirmed_reminder_judge=unconfirmed_judge)
       assert old_errors == new_errors, (index, old_errors, new_errors)
   print(f"matched old/new scorer verdicts for {len(payload['results'])} captured cases")
   PY
   ```
   Expected: the old monolith scorer and the new split scorer produce identical
   errors over the same captured observations.
4. Import health:
   ```
   python -c "from scripts.reminder_eval import dataset, runner, scoring, judges"
   python scripts/run_reminder_eval.py --help
   python scripts/simulate_user_path.py --help
   ```
   `run_reminder_eval.py` guards its entry point with
   `if __name__ == "__main__": sys.exit(runner.main())`, so `--help`
   exercises the wiring without testing it as an importable module.
5. Repo-OS guardrails:
   ```
   zsh scripts/check
   zsh scripts/suggest-verification --base HEAD~1
   ```
   then run whatever surface the suggestion proposes.

## Known Debt (Not Addressed by This Split)

This section exists so a future reader does not mistake the
post-split layout for "good enough."

1. **Grader / parser twin.** `scoring.expected_created_reminders(text)`
   re-implements a slice of the runtime's Chinese clock parser. Every
   time the runtime parser learns a new form, the scorer must learn it
   too or it produces false negatives. The growing
   `expected_creates` fields in `expectations.json` (218 of 376 cases)
   are partly compensating for this. The narrower scorer-hint fields
   `title_variants`, `output_terms`, and `rrule_contains` currently
   appear in 25 cases. The clean fix is to forbid the scorer from
   re-deriving expectations from `case.input` and require all
   expectations to come from the dataset file. B-tier work.
2. **`expectations.json` mixes three roles.** It conflates ground
   truth labels (`evaluation_expectation`), triage metadata
   (`severity`, `evaluation_reason`), and per-case scorer hints
   (`expected_creates`, `title_variants`, `allow_clarification`,
   `expected_clarification_terms`, `rrule_contains`, `output_terms`).
   No schema, no provenance. B-tier work: split labels from hints,
   add a JSON schema, record why each hint exists.
3. **No named subsets.** Today only `--offset/--limit` exist; there
   is no first-class `smoke-30` / `regression-50` / `full` selector
   matching the user's standing preference for representative subsets
   over full-corpus runs. B-tier work in the dataset layer.
4. **No solver pluggability.** Every eval must boot Mongo and a real
   worker. Trace replay and head-to-head scorer comparison on a
   fixed set of outputs are not possible. C-tier work; only
   relevant if model-comparison or scorer-comparison becomes a
   regular workflow.
