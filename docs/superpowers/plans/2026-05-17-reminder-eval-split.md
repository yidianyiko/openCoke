# Reminder Eval Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the reminder normal-path eval monolith into dataset, runner, scoring, and judge modules without changing corpus semantics.

**Architecture:** `scripts/reminder_eval/dataset.py` owns shared dataclasses, case loading, fixture merge, selection, and fixture manifest helpers. `runner.py` owns Mongo orchestration and CLI plumbing, `scoring.py` owns verdict/scoring policy and calls `judges.py` only through existing injectable judge seams, and `scripts/run_reminder_eval.py` is the executable entrypoint.

**Tech Stack:** Python 3, pytest, pymongo, pydantic, Agno LLM judge wrappers, repo-OS shell guardrails.

---

### Task 1: Capture Baseline And Fix Spec Review Gaps

**Files:**
- Modify: `docs/superpowers/specs/2026-05-17-reminder-eval-split-design.md`
- Create: `artifacts/evidence/reminder-normal/pre-split-eval-split-baseline.json`

- [x] **Step 1: Run focused baseline tests before moving code**

Run:
```bash
.venv/bin/python -m pytest tests/evals/test_reminder_normal_path_eval.py tests/unit/agent/test_severity_thresholds.py -q
```
Expected: existing tests pass before the structural split.

- [x] **Step 2: Capture the old CLI smoke baseline**

Run:
```bash
.venv/bin/python scripts/user_path_normal_eval.py --limit 30 --output artifacts/evidence/reminder-normal/pre-split-eval-split-baseline.json
```
Expected: command writes a JSON file with `results`. The command may exit 1
if the current live corpus slice has existing failures; that is acceptable
for smoke evidence as long as the JSON is written.

- [x] **Step 3: Confirm the reviewed spec closes the known issues**

Check:
```bash
rg -n "test_reminder_eval_\\*|pre-split|Most functions are pure|25 cases" docs/superpowers/specs/2026-05-17-reminder-eval-split-design.md
```
Expected: output shows the skill migration, explicit baseline compare, corrected scoring/judge language, and corrected scorer-hint count.

### Task 2: Split Production Modules

**Files:**
- Create: `scripts/reminder_eval/__init__.py`
- Create: `scripts/reminder_eval/dataset.py`
- Create: `scripts/reminder_eval/runner.py`
- Create: `scripts/reminder_eval/scoring.py`
- Create: `scripts/reminder_eval/judges.py`
- Create: `scripts/run_reminder_eval.py`
- Delete: `scripts/user_path_normal_eval.py`

- [x] **Step 1: Move shared imports and data shapes to `dataset.py`**

Move constants and definitions through `iter_case_batches` from the old file into `dataset.py`, keeping the exact function bodies and dataclass fields. Keep imports limited to `json`, `dataclasses`, `datetime`, `Path`, and `Any`.

- [x] **Step 2: Move LLM judge wrappers to `judges.py`**

Move timeout constants, pydantic response schemas, timeout exception classes, judge prompt builders, judge runners, worker functions, agent factories, and `_create_unconfirmed_reminder_judge_model` into `judges.py`. Preserve the existing multiprocessing start method and environment variable behavior.

- [x] **Step 3: Move scoring functions to `scoring.py`**

Move `validate_observations` through `summarize`, excluding the judge class/functions moved in Step 2 and runner functions moved in Step 4. Import dataclasses and `load_case_expectations` from `scripts.reminder_eval.dataset`; import `run_clarification_output_judge` and `run_unconfirmed_reminder_judge` from `scripts.reminder_eval.judges`.

- [x] **Step 4: Move Mongo orchestration and CLI code to `runner.py`**

Move Mongo helpers from `mongo_client` through `resolve_case_conversation_ids`, plus `run_batch`, `json_safe`, `_parse_args`, `default_evidence_path`, and `main`. Import dataset helpers from `scripts.reminder_eval.dataset` and scoring helpers from `scripts.reminder_eval.scoring`.

- [x] **Step 5: Add the new executable wrapper**

Create `scripts/run_reminder_eval.py`:
```python
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.reminder_eval import runner


if __name__ == "__main__":
    sys.exit(runner.main())
```

### Task 3: Split Tests Without Rewriting Assertions

**Files:**
- Create: `tests/evals/test_reminder_eval_dataset.py`
- Create: `tests/evals/test_reminder_eval_runner.py`
- Create: `tests/evals/test_reminder_eval_scoring.py`
- Delete: `tests/evals/test_reminder_normal_path_eval.py`

- [x] **Step 1: Create dataset tests**

Move the two batch iteration tests plus fixture-loader/selection/manifest tests from old lines `92-117` and `1473-1570` into `test_reminder_eval_dataset.py`. Import `scripts.reminder_eval.dataset as normal_eval`.

- [x] **Step 2: Create runner tests**

Move the runner tests and Mongo helper classes from old lines `28-487` into `test_reminder_eval_runner.py`. Import `scripts.reminder_eval.runner as normal_eval` and `ReminderNormalPathCase` from `scripts.reminder_eval.dataset`; replace dataclass references with the direct import.

- [x] **Step 3: Create scoring tests**

Move the autouse judge-stub fixture and all scoring/judge-policy tests from old lines `488-2715`, excluding dataset tests moved in Step 1, into `test_reminder_eval_scoring.py`. Import `scripts.reminder_eval.scoring as normal_eval` and `ReminderNormalPathCase`, `ExpectedReminderCreate`, and `DEFAULT_EXPECTATIONS_PATH` from `scripts.reminder_eval.dataset`.

### Task 4: Update In-Repo Callers And Docs

**Files:**
- Modify: `scripts/simulate_user_path.py`
- Modify: `tests/unit/agent/test_severity_thresholds.py`
- Modify: `docs/fitness/coke-verification-matrix.md`
- Modify: `.agents/skills/reminder-crud-case-testing/SKILL.md`

- [x] **Step 1: Update simulator imports**

Replace the old normal-eval module import with:
```python
from conf.config import CONF
from scripts.reminder_eval import dataset, runner
from scripts.reminder_eval.dataset import ReminderNormalPathCase
```
Route case loading and constants through `dataset`, Mongo and run orchestration through `runner`, and database config through `CONF`.

- [x] **Step 2: Update severity test imports**

Replace:
```python
from scripts.user_path_normal_eval import ReminderNormalPathResult, summarize
```
with:
```python
from scripts.reminder_eval.dataset import ReminderNormalPathResult
from scripts.reminder_eval.scoring import summarize
```

- [x] **Step 3: Update docs and skill commands**

Replace deleted runner/test paths with:
```bash
.venv/bin/python scripts/run_reminder_eval.py --run-all
pytest tests/evals/test_reminder_eval_*.py -v
scripts/reminder_eval/scoring.py::output_implies_unconfirmed_reminder
```

### Task 5: Verify Behavior Preservation

**Files:**
- Read: `artifacts/evidence/reminder-normal/pre-split-eval-split-baseline.json`
- Create: `artifacts/evidence/reminder-normal/post-split-eval-split-baseline.json`

- [x] **Step 1: Run split test set**

Run:
```bash
.venv/bin/python -m pytest tests/evals/test_reminder_eval_*.py tests/unit/agent/test_severity_thresholds.py -q
```
Expected: all migrated tests pass.

- [x] **Step 2: Run import health checks**

Run:
```bash
.venv/bin/python -c "from scripts.reminder_eval import dataset, runner, scoring, judges"
.venv/bin/python scripts/run_reminder_eval.py --help
.venv/bin/python scripts/simulate_user_path.py --help
```
Expected: all commands exit 0.

- [x] **Step 3: Capture post-split smoke output**

Run:
```bash
.venv/bin/python scripts/run_reminder_eval.py --limit 30 --output artifacts/evidence/reminder-normal/post-split-eval-split-baseline.json
```
Expected: command writes a JSON file with `results`. The command may exit 1
if the current live corpus slice has existing failures; compare scorer
semantics on the captured output in the next step.

- [x] **Step 4: Compare old/new scorer verdicts over identical captured observations**

Run:
```bash
git show HEAD:scripts/user_path_normal_eval.py > /tmp/user_path_normal_eval_pre_split.py
.venv/bin/python - <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

from scripts.reminder_eval import scoring as new_scoring
from scripts.reminder_eval.dataset import ReminderNormalPathCase

spec = importlib.util.spec_from_file_location(
    "pre_split_eval", "/tmp/user_path_normal_eval_pre_split.py"
)
old = importlib.util.module_from_spec(spec)
sys.modules["pre_split_eval"] = old
spec.loader.exec_module(old)

payload = json.loads(
    Path("artifacts/evidence/reminder-normal/post-split-eval-split-baseline.json").read_text()
)
old_cases = old.load_cases()
new_cases = [
    ReminderNormalPathCase(
        input=case.input,
        expected_intent=case.expected_intent,
        matched_keywords=case.matched_keywords,
        metadata=case.metadata,
    )
    for case in old_cases
]

def clarification_judge(_case_input, output_text):
    return any(marker in output_text for marker in ("?", "？", "吗", "呢"))

def unconfirmed_judge(_text):
    return False

for result in payload["results"]:
    index = result["index"]
    old_errors = old.validate_observations(
        old_cases[index],
        result["input_status"],
        result["outputs"],
        result["reminders"],
        clarification_judge=clarification_judge,
        unconfirmed_reminder_judge=unconfirmed_judge,
    )
    new_errors = new_scoring.validate_observations(
        new_cases[index],
        result["input_status"],
        result["outputs"],
        result["reminders"],
        clarification_judge=clarification_judge,
        unconfirmed_reminder_judge=unconfirmed_judge,
    )
    assert old_errors == new_errors, (index, old_errors, new_errors)
print(f"matched old/new scorer verdicts for {len(payload['results'])} captured cases")
PY
```
Expected: prints `matched old/new scorer verdicts for 30 captured cases`.

- [x] **Step 5: Run repo guardrails**

Run:
```bash
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```
Expected: commands complete; run any additional required surface command they identify.
