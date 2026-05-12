# Reminder Detect Prompt Diet — Follow-up Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the 6 follow-up items that came out of the 2026-05-12 reminder_detect prompt diet (commit `8d2a968`), each as an independent, testable change.

**Architecture:** Six independent follow-up tasks. A, B, C are P0 and can run in parallel. D depends on A and B. E and F are P2, independent of others. Each task ends in its own commit so a separate agent can own it.

**Tech Stack:** Python 3.12, pytest, GLM-5.1 via SiliconFlow API, MongoDB, APScheduler.

**Pre-reading for every task:**
- `docs/issues/2026-05-12-reminder-detect-model-bake-off.md` (verification report)
- `docs/adr/0004-per-agent-prompt-budget-discipline.md` (per-agent token budget rule)
- `AGENTS.md` §Validation (how to verify before claiming done)
- `docs/fitness/coke-verification-matrix.md` worker-runtime section (which tests to run)

**Convention:** every task ends with a `git commit` step. Push only when the user asks; the merge cadence is up to the human operator.

---

## Task A: Few-Shot Diet Validation [P0, ~1-2 days]

**Why:** v2 prod scored 83.3% exact on the time-accuracy Phase 0 subset; v2 standalone (without the few-shot block in `build_reminder_intent_input`) scored 86.7%. The 3.4 pp gap is the only known live regression vs the standalone experiment. We need a decisive answer: keep the few-shots, drop them, or compress them. Few-shots may also help intent classification on edge cases, so deletion is not automatic — measure both axes.

**Files:**
- Modify: `agent/agno_agent/prompts/reminder_intent.py:39-60` (input builder)
- Modify: `tests/unit/prompt/test_agent_instructions_prompt.py:108-121` (existing few-shot assertion)
- Modify: `tests/unit/agent/test_reminder_intent_capability.py:88-135` (input builder test)
- Create: `scripts/_phase0_intent_classification.py` (new measurement script)
- Reuse: `scripts/_phase0_time_accuracy.py` (existing time-accuracy script)

### Steps

- [ ] **A1: Read the current state**

Read these to know the baseline:
- `agent/prompt/reminder_few_shot.py` — what's in the few-shot data
- `agent/agno_agent/prompts/reminder_intent.py:23-60` — where few-shots are injected
- `artifacts/evidence/reminder-model-compare/2026-05-12-phase0-v2-streamlined-prompt.json` — v2 standalone result (86.7%)
- `artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy-v2-prod.json` — v2 prod result (83.3%)

- [ ] **A2: Write an intent-classification measurement script**

Create `scripts/_phase0_intent_classification.py`:

```python
"""Phase 0 intent: measure GLM-5.1 thinking-off intent_type accuracy.

Complements _phase0_time_accuracy.py (which only graded trigger_at).
This grades whether the LLM's decision.intent_type matches the
expectation's evaluation_expectation, across the full 4 classes
(crud/clarify/discussion/query).

Together the two scripts let us decide whether dropping few-shots
hurts intent classification while it helps time accuracy.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._phase0_time_accuracy import CANDIDATE, TIMEZONE
from scripts.compare_reminder_detect_models import (
    build_agent,
    build_context,
    decision_from_response,
)


def select_intent_cases(expectations, target_per_class=10):
    """Pick representative cases per intent class from the corpus."""
    buckets: dict[str, list[int]] = {"crud": [], "clarify": [], "discussion": [], "query": []}
    for idx in sorted(expectations.keys(), key=int):
        e = expectations[idx]
        cls = str(e.get("evaluation_expectation") or "").strip().lower()
        if cls in buckets and len(buckets[cls]) < target_per_class:
            buckets[cls].append(int(idx))
    return buckets


def grade_intent(decision, expected):
    if decision is None:
        return "fail_no_decision"
    got = str(decision.get("intent_type") or "").lower()
    if not got:
        return "fail_no_intent"
    return "pass" if got == expected else f"fail_got_{got}"


async def run_one(agent, case, expected_intent, tz):
    from datetime import datetime
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
    ts = str(case.get("metadata", {}).get("timestamp") or "")
    context = build_context(case.get("input", ""), ts, tz)
    prompt = build_reminder_intent_input(case.get("input", ""), context)
    started = datetime.now()
    error = None
    decision = None
    try:
        response = await asyncio.wait_for(agent.arun(input=prompt), timeout=120)
        decision = decision_from_response(response)
    except asyncio.TimeoutError:
        error = "timeout_120s"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = (datetime.now() - started).total_seconds()
    return {"elapsed_seconds": round(elapsed, 2), "error": error,
            "grade": grade_intent(decision, expected_intent),
            "got_intent": (decision.get("intent_type") if decision else None)}


async def main_async() -> int:
    from scripts._phase0_time_accuracy import load_cases_and_expectations
    cases, expectations = load_cases_and_expectations()
    buckets = select_intent_cases(expectations, target_per_class=10)
    selected = sorted({i for v in buckets.values() for i in v})
    print(f"Phase 0 intent: {len(selected)} cases across {len(buckets)} classes")
    agent = build_agent(CANDIDATE)
    rows = []
    for n, idx in enumerate(selected, start=1):
        case = cases[idx]
        expected = str(expectations[idx].get("evaluation_expectation") or "").lower()
        result = await run_one(agent, case, expected, TIMEZONE)
        rows.append({"case_index": idx, "expected": expected,
                     "input": case.get("input", "")[:80], **result})
        marker = "OK" if result["grade"] == "pass" else "X "
        print(f"  [{n:2d}/{len(selected)}] case={idx:4d} {marker} "
              f"exp={expected} got={result['got_intent']} ({result['elapsed_seconds']}s)")
    passes = sum(1 for r in rows if r["grade"] == "pass")
    per_class = {cls: {"total": 0, "pass": 0} for cls in buckets}
    for r in rows:
        per_class[r["expected"]]["total"] += 1
        if r["grade"] == "pass":
            per_class[r["expected"]]["pass"] += 1
    print(f"\n=== Intent Phase 0 summary ===")
    print(f"  total: {len(rows)}, pass: {passes} ({passes/len(rows)*100:.1f}%)")
    for cls, s in per_class.items():
        rate = s['pass']/s['total']*100 if s['total'] else 0
        print(f"  {cls:12s}: {s['pass']}/{s['total']} ({rate:.1f}%)")
    out = PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-phase0-intent-classification.json"
    out.write_text(json.dumps({"summary": {"total": len(rows), "pass": passes,
                                            "per_class": per_class},
                                "rows": rows}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
```

- [ ] **A3: Run the intent baseline (with few-shots, current state)**

Run: `.venv/bin/python scripts/_phase0_intent_classification.py 2>&1 | tee /tmp/intent_with_fewshots.log`

Expected: per-class pass rates with few-shots present. Note the per-class numbers.

Cost: ~40 cases × ~10 s = 7 min wall clock, ~¥4 API spend.

- [ ] **A4: Edit `build_reminder_intent_input` to drop few-shots**

Open `agent/agno_agent/prompts/reminder_intent.py`. Remove the `format_reminder_few_shots_for_prompt()` line and its section header:

```python
# BEFORE (lines 53-54):
            "### Reminder Few-Shot Decisions",
            format_reminder_few_shots_for_prompt(),

# AFTER: delete both lines. Also delete the import at line 8:
# from agent.prompt.reminder_few_shot import format_reminder_few_shots_for_prompt
```

The function body should now go: 当前时间 → 用户时区 → conversation_id → 最近对话上下文 → (workflow_lines if any) → 当前用户消息.

- [ ] **A5: Update tests for the dropped section**

In `tests/unit/prompt/test_agent_instructions_prompt.py` lines 108-121, replace the body of `test_reminder_few_shots_are_input_context_not_system_prompt`:

```python
def test_reminder_few_shots_are_no_longer_emitted_in_input():
    """ADR 0004 follow-up: per-turn input drops the few-shot decision block
    after Phase 0 verified it costs accuracy on GLM-5.1 thinking-off without
    measurable intent-classification gain.
    """
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    reminder_input = build_reminder_intent_input("18:00提醒我喝水", _run_context())
    instructions = get_reminder_detect_instructions("2026年04月30日12时00分")

    # No few-shot block anywhere.
    assert "### Reminder Few-Shot Decisions" not in reminder_input
    assert '"decision_class": "crud.create"' not in reminder_input
    assert "Reminder Few-Shot Decisions" not in instructions
    # Structural sections still present.
    assert "### 当前时间" in reminder_input
    assert "### 当前用户消息" in reminder_input
    assert "18:00提醒我喝水" in reminder_input
```

In `tests/unit/agent/test_reminder_intent_capability.py:88-135`, find the `legacy_phrases` tuple in `test_build_reminder_intent_input_carries_dynamic_context_only` and add the few-shot assertions:

```python
# Replace the two few-shot assertions:
#   assert '"schedule_basis": "explicit_occurrences"' in prompt
#   assert '"rrule": "FREQ=DAILY"' in prompt
# with:
    assert '"schedule_basis"' not in prompt
    assert '"decision_class"' not in prompt
# and ALSO replace
#   assert "### Reminder Few-Shot Decisions" in prompt
# with
    assert "### Reminder Few-Shot Decisions" not in prompt
```

- [ ] **A6: Verify tests pass**

Run: `.venv/bin/python -m pytest tests/unit/prompt/ tests/unit/agent/test_reminder_intent_capability.py -q`

Expected: All pass except the pre-existing xfail in `test_reminder_intent_capability.py`.

- [ ] **A7: Re-run intent measurement (without few-shots)**

Run: `.venv/bin/python scripts/_phase0_intent_classification.py 2>&1 | tee /tmp/intent_without_fewshots.log`

Compare to A3 baseline. The number to watch: per-class pass rates. If `crud` and `clarify` rates drop by more than 5 pp, the few-shots were doing real work for intent classification and dropping them is a trade. If they hold within ±2 pp, dropping is a clean win.

- [ ] **A8: Re-run time accuracy (without few-shots)**

Run: `.venv/bin/python scripts/_phase0_time_accuracy.py 2>&1 | tail -10`

Expected: exact-rate should rise toward 86.7% (the v2 standalone result). The script writes to `artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy.json`; rename to `…-no-fewshots.json` so you don't overwrite the prior v2-prod result.

Run: `cp artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy.json artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy-no-fewshots.json`

- [ ] **A9: Decide and document**

Pick one based on the data:
- **Drop few-shots permanently** (most likely if intent rates held): commit the changes from A4-A5, write a short note in `docs/issues/2026-05-12-reminder-detect-model-bake-off.md` summarizing the intent vs time tradeoff and the decision.
- **Restore few-shots** (if intent rates dropped >5 pp): revert A4-A5, document the constraint in the same issue file.
- **Compress few-shots** (intent rate dropped 2-5 pp): reduce `agent/prompt/reminder_few_shot.py` to 3-4 representative shots covering crud/clarify/discussion only, drop query and update/delete shots. Re-run A7-A8 to verify. This is a third commit.

Whichever option, write 1-2 paragraphs to the issue doc capturing the data and reasoning. No vague language — cite specific per-class numbers.

- [ ] **A10: Commit**

```bash
git add agent/agno_agent/prompts/reminder_intent.py \
        tests/unit/prompt/test_agent_instructions_prompt.py \
        tests/unit/agent/test_reminder_intent_capability.py \
        scripts/_phase0_intent_classification.py \
        artifacts/evidence/reminder-model-compare/2026-05-12-phase0-intent-classification.json \
        artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy-no-fewshots.json \
        docs/issues/2026-05-12-reminder-detect-model-bake-off.md
git commit -m "$(cat <<'COMMIT_EOF'
Resolve the few-shot tradeoff in build_reminder_intent_input

Phase 0 follow-up to commit 8d2a968. Measured intent-classification
pass rate with and without the few-shot block; <fill in decision and
numbers from A9>.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
COMMIT_EOF
)"
```

---

## Task B: Corpus Severity Tiering [P0, ~1-2 days]

**Why:** `scripts/reminder_normal_path_expectations.json` has 365 cases and the eval is currently all-or-nothing. A single edge case regression blocks merges. Adding `severity ∈ {critical, important, nice}` lets CI gate proportionally and lets future contributors decide where a new failure case belongs (often `nice`, not "fix the code").

**Files:**
- Modify: `scripts/reminder_normal_path_expectations.json` (add `severity` to every case)
- Modify: `scripts/user_path_normal_eval.py` (read severity, apply tiered thresholds)
- Modify: `docs/fitness/coke-verification-matrix.md` (document the new thresholds)
- Create: `docs/design-docs/reminder-corpus-severity.md` (labeling standard)

### Steps

- [ ] **B1: Write the labeling standard first**

Create `docs/design-docs/reminder-corpus-severity.md`:

```markdown
# Reminder Corpus Severity Tiers

This document defines how cases in
`scripts/reminder_normal_path_expectations.json` are graded for CI
enforcement. Severity is a property of the *case*, not of the *current
LLM*: a case is "critical" because a wrong answer breaks user trust,
regardless of whether the current model gets it right.

## Tiers

### `critical` (target: 100% pass)
A wrong answer creates user-visible damage:
- Wrong-time reminders fired at the wrong half of the day (12 h AM/PM
  inversion)
- Reminders silently dropped from a multi-clause request
- A delete/cancel intent treated as create (or vice versa)
- A clear date+time CRUD request answered with clarify (the user gave
  enough information and we asked them to repeat it)

### `important` (target: ≥95% pass)
The case is user-facing and matters, but a wrong answer is recoverable:
- An over-clarification on an ambiguous bare clock
- A wrong title where the time is still correct
- A wrong RRULE that still fires once on the right occurrence

### `nice` (target: ≥80% pass)
Edge-case language phenomena and corpus stability work:
- Specific Chinese phrasings (晚 X 点 vs 晚上 X 点)
- Noisy filler before time references
- Multi-clause inputs with redundant context

## Process for new failures

When a new corpus case fails:
1. Decide its severity using this standard.
2. If `critical` or `important`: file as an issue, plan the fix.
3. If `nice`: add to corpus at `severity: nice`, accept it as a known
   limitation unless three or more nice cases share a structural cause.
4. Never reclassify a failing case down just to make CI green.

## Migration

The initial labeling on 2026-05-12 is approximate. Re-label any case
whose severity is wrong when you next read it.
```

- [ ] **B2: Write a one-shot labeling helper script**

Create `scripts/_label_severity.py`:

```python
"""Bulk-label corpus cases with severity tiers.

Heuristic labels based on evaluation_reason text. Run once, then a
human reviews the JSON and adjusts. This script is not part of the
runtime; it lives in scripts/ for one-time use only.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "scripts/reminder_normal_path_expectations.json"

CRITICAL_PATTERNS = [
    re.compile(r"12[- ]hour|am/pm|next.morning|same.afternoon"),
    re.compile(r"dropped|missing|partial.execut"),
    re.compile(r"delete.*create|cancel.*create"),
    re.compile(r"date.*time.*clarify|concrete.*clarify"),
]
NICE_PATTERNS = [
    re.compile(r"chinese.*period|nightly|past.*\d|noisy filler|particle"),
    re.compile(r"specific.*phrasing|stale|fixture"),
    re.compile(r"redundant|reorder|merge"),
]


def classify(reason: str) -> str:
    r = reason.lower()
    for p in CRITICAL_PATTERNS:
        if p.search(r):
            return "critical"
    for p in NICE_PATTERNS:
        if p.search(r):
            return "nice"
    return "important"


def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    stats = {"critical": 0, "important": 0, "nice": 0}
    for idx, case in cases.items():
        if "severity" in case:
            stats[case["severity"]] += 1
            continue
        sev = classify(case.get("evaluation_reason", ""))
        case["severity"] = sev
        stats[sev] += 1
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"Labeled. Total: {sum(stats.values())} | {stats}")
    print("Now review scripts/reminder_normal_path_expectations.json by hand and")
    print("adjust labels. Critical and nice are easier to be wrong about than important.")


if __name__ == "__main__":
    main()
```

- [ ] **B3: Run the auto-labeler**

Run: `.venv/bin/python scripts/_label_severity.py`

Expected output: roughly the totals split across the three tiers.

- [ ] **B4: Hand-review the labels**

Open `scripts/reminder_normal_path_expectations.json` in an editor. Scan all cases marked `critical` — they should all involve wrong-direction or user-visible-damage failures per the standard. Move anything that's overzealous into `important`.

Then scan `nice` — these should be specific-phrasing or fixture-stability, not user-visible. Move anything that *would* damage trust into `important` or `critical`.

Aim for a final distribution roughly:
- critical: 30-50 cases
- important: 150-200 cases
- nice: 150-200 cases

Don't agonize. The standard says you can re-label later.

- [ ] **B5: Write a test that severity-tiered CI works**

Create `tests/unit/agent/test_severity_thresholds.py`:

```python
"""Verify the corpus uses the three-tier severity scheme and that the
eval runner enforces per-tier thresholds."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXP = ROOT / "scripts/reminder_normal_path_expectations.json"


def test_every_case_has_severity():
    data = json.loads(EXP.read_text(encoding="utf-8"))
    missing = [idx for idx, case in data["cases"].items()
               if case.get("severity") not in {"critical", "important", "nice"}]
    assert not missing, f"cases without severity: {missing[:10]}..."


def test_severity_distribution_is_roughly_balanced():
    """Sanity check the auto-labeled distribution — if any tier is empty,
    something went wrong with the labeling pass."""
    data = json.loads(EXP.read_text(encoding="utf-8"))
    counts = {"critical": 0, "important": 0, "nice": 0}
    for case in data["cases"].values():
        counts[case["severity"]] += 1
    assert all(n >= 10 for n in counts.values()), \
        f"each tier should have ≥10 cases: {counts}"


def test_severity_standard_doc_exists():
    standard = ROOT / "docs/design-docs/reminder-corpus-severity.md"
    assert standard.exists()
    text = standard.read_text(encoding="utf-8")
    assert "100% pass" in text
    assert "≥95% pass" in text
    assert "≥80% pass" in text
```

- [ ] **B6: Run the new tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_severity_thresholds.py -v`

Expected: all 3 pass.

- [ ] **B7: Wire the severity thresholds into the eval runner**

Open `scripts/user_path_normal_eval.py`. Find the `summarize` function (search for `def summarize`). Add a per-severity breakdown to its return value:

```python
def summarize(results: list[ReminderNormalPathResult]) -> dict[str, Any]:
    # ... existing aggregations ...
    expectations = load_case_expectations(DEFAULT_EXPECTATIONS_PATH)
    per_severity: dict[str, dict[str, int]] = {
        "critical": {"total": 0, "pass": 0},
        "important": {"total": 0, "pass": 0},
        "nice": {"total": 0, "pass": 0},
    }
    for r in results:
        severity = str(expectations.get(r.index, {}).get("severity") or "important")
        if severity not in per_severity:
            continue
        per_severity[severity]["total"] += 1
        if r.passed:
            per_severity[severity]["pass"] += 1
    thresholds = {"critical": 1.0, "important": 0.95, "nice": 0.80}
    violations = []
    for tier, stats in per_severity.items():
        if stats["total"] == 0:
            continue
        rate = stats["pass"] / stats["total"]
        if rate < thresholds[tier]:
            violations.append(f"{tier}: {rate*100:.1f}% < {thresholds[tier]*100:.0f}%")
    # ... existing return dict gains:
    return {
        # ...existing fields...
        "per_severity": per_severity,
        "severity_thresholds": thresholds,
        "severity_violations": violations,
    }
```

The exact integration point depends on the existing `summarize` body — read it first and graft this in. If `summarize` already returns a dict, add the three new keys; if it returns something else, refactor to dict.

Then update `main()` so a `severity_violations` non-empty list causes non-zero exit code, distinct from the current `summary["failed"] > 0` check.

- [ ] **B8: Update the verification matrix**

In `docs/fitness/coke-verification-matrix.md`, find the "Focused reminder-system command set" section. Replace it with:

```markdown
Focused reminder-system command set:

\`\`\`bash
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
pytest tests/unit/agent/test_severity_thresholds.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
\`\`\`

Severity-tiered corpus check (run before merging changes to the prompt or
guard helpers; see `docs/design-docs/reminder-corpus-severity.md`):

\`\`\`bash
.venv/bin/python scripts/user_path_normal_eval.py --run-all
# exit 0 requires critical=100%, important≥95%, nice≥80%.
\`\`\`
```

- [ ] **B9: Run repo-OS check**

Run: `zsh scripts/check`

Expected: `check passed`.

- [ ] **B10: Commit**

```bash
git add scripts/reminder_normal_path_expectations.json \
        scripts/user_path_normal_eval.py \
        scripts/_label_severity.py \
        docs/design-docs/reminder-corpus-severity.md \
        docs/fitness/coke-verification-matrix.md \
        tests/unit/agent/test_severity_thresholds.py
git commit -m "$(cat <<'COMMIT_EOF'
Add severity tiering to reminder corpus and CI thresholds

Every case in scripts/reminder_normal_path_expectations.json now
carries critical/important/nice; user_path_normal_eval.py enforces
per-tier thresholds (100/95/80). Labeling standard lives in
docs/design-docs/reminder-corpus-severity.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
COMMIT_EOF
)"
```

---

## Task C: Fix Pre-Existing xfail Guard-Cascade Bug [P0, ~1 day]

**Why:** `tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_retries_today_time_range_recurring_compression` is marked `xfail` because `_should_retry_for_missing_scheduled_clauses` fires after the `today_time_range` retry has already produced a valid batch decision. `_explicit_scheduled_clause_count` counts each clock in a range ("11:30-13:30" = 2 clocks) but the user wants one reminder per task (= 1 op), so the post-retry count is structurally less than the input count. This pre-dates the v2 swap.

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:716-741` (the post-decision guard chain) AND `agent/agno_agent/capabilities/reminder_intent.py:2141-2154` (`_explicit_scheduled_clause_count`)
- Modify: `tests/unit/agent/test_reminder_intent_capability.py` (remove the xfail marker, restore the original behavioral assertions)

### Steps

- [ ] **C1: Reproduce the bug**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_retries_today_time_range_recurring_compression -v`

Expected: `XFAIL` (passing-as-expected-failure).

Remove the `xfail` decorator temporarily (will restore at C5) to see the actual failure:

Open `tests/unit/agent/test_reminder_intent_capability.py` and find the `@pytest.mark.xfail(` block above `test_reminder_intent_port_retries_today_time_range_recurring_compression`. Comment it out.

Re-run the test. Expected: actual failure, with `assert result.ok is True` failing because the final result is a `clarify` instead of `crud`.

- [ ] **C2: Add a regression-fence unit test for the clause counter**

In `tests/unit/agent/test_reminder_intent_capability.py`, add a new test near the bottom that pins down the intended behavior of `_explicit_scheduled_clause_count` for today-task-range inputs:

```python
def test_explicit_scheduled_clause_count_treats_ranges_as_single_clauses():
    """Today-task-range inputs ('11:30-13:30 看法考网课；13:30-15:30 健身')
    should count as 2 reminder clauses (one per task), not 4. The user
    wants one reminder per task; the start-of-range clock is the trigger,
    the end-of-range is the deadline of the task, not a separate clock.
    """
    from agent.agno_agent.capabilities.reminder_intent import (
        _explicit_scheduled_clause_count,
    )

    text = (
        "这是我今天的任务 11：30-13：30 看法考网课；"
        "13：30-15：30 健身 请在这些时间点提醒我学习"
    )
    assert _explicit_scheduled_clause_count(text) == 2

    plain = "我8点喝水，9点锻炼"
    assert _explicit_scheduled_clause_count(plain) == 2

    single = "10点提醒我"
    assert _explicit_scheduled_clause_count(single) == 1
```

Run the new test alone:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py::test_explicit_scheduled_clause_count_treats_ranges_as_single_clauses -v
```

Expected: FAIL on the first assertion (current count returns 3, not 2).

- [ ] **C3: Fix the counter**

Open `agent/agno_agent/capabilities/reminder_intent.py:2141-2154`. The current implementation collects every bare clock match in a set and returns the cardinality. Change it to collapse ranges so a `HH:MM-HH:MM` range contributes one clause, not two:

```python
def _explicit_scheduled_clause_count(input_message: str) -> int:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return 0
    if not (
        _REMINDER_VERB_PATTERN.search(current_user_text)
        or re.search(r"询问我|告诉我|问问我|check in|report", current_user_text, re.I)
    ):
        return 0
    # Collapse clock ranges to the start clock so a "11:30-13:30" range
    # counts as one clause (the task) rather than two clocks. Both ascii
    # hyphen and the Chinese dash are valid range separators in the
    # corpus.
    normalized = re.sub(
        r"(\d{1,2}[:：]\d{2})\s*[-–—]\s*\d{1,2}[:：]\d{2}",
        r"\1",
        current_user_text,
    )
    matches = {
        re.sub(r"\s+", "", match.group(0))
        for match in _SINGLE_BARE_CLOCK_EXTRACTION_PATTERN.finditer(normalized)
    }
    return len(matches)
```

- [ ] **C4: Verify the counter test passes and the original test passes**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_reminder_intent_capability.py::test_explicit_scheduled_clause_count_treats_ranges_as_single_clauses \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_retries_today_time_range_recurring_compression \
  -v
```

Expected: both PASS. The second test passes because `_should_retry_for_missing_scheduled_clauses` now returns False on the retry decision (op count 2 = clause count 2).

- [ ] **C5: Remove the xfail marker for good**

Open `tests/unit/agent/test_reminder_intent_capability.py`. Delete the entire `@pytest.mark.xfail(...)` block above `test_reminder_intent_port_retries_today_time_range_recurring_compression` (you commented it out in C1 — now remove it fully). The test should be a plain `@pytest.mark.asyncio` test.

- [ ] **C6: Broader regression test**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -q`

Expected: all pass, no xfail. (If any other test now fails, it's a real regression — investigate before continuing.)

- [ ] **C7: Update the issue follow-up note**

Open `docs/issues/2026-05-12-reminder-detect-model-bake-off.md`. Find the bullet about the xfail test. Replace it with a short note indicating it was resolved in this commit:

```markdown
5. `test_reminder_intent_port_retries_today_time_range_recurring_compression`
   was xfail at the time of commit 8d2a968; fixed in a follow-up commit
   by making `_explicit_scheduled_clause_count` collapse `HH:MM-HH:MM`
   ranges to the start clock, so today-task-range retries no longer
   cascade into `_should_retry_for_missing_scheduled_clauses`.
```

- [ ] **C8: Commit**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py \
        tests/unit/agent/test_reminder_intent_capability.py \
        docs/issues/2026-05-12-reminder-detect-model-bake-off.md
git commit -m "$(cat <<'COMMIT_EOF'
Fix today-task-range guard cascade in reminder_detect

_explicit_scheduled_clause_count now collapses HH:MM-HH:MM ranges to
the start clock, so a "11:30-13:30 看法考网课" range counts as one
clause (the task), not two. The today_time_range retry's batch result
no longer trips _should_retry_for_missing_scheduled_clauses, and the
final decision is the correct batch crud instead of a clarify
fallback. Removes the xfail marker from
test_reminder_intent_port_retries_today_time_range_recurring_compression.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
COMMIT_EOF
)"
```

---

## Task D: Guard Helper Audit and Pruning [P1, ~3-5 days, depends on A and B]

**Why:** `agent/agno_agent/capabilities/reminder_intent.py` is 2918 lines, ~40 `_should_*` / `_normalize_*` / `_drop_*` / `_input_is_*` helpers. v2 prompt diet dropped raw model accuracy from "needs guards" to "guards rarely fire". Many guards almost certainly run on zero or one current corpus case. After A (few-shot decision) and B (severity tiering), audit each guard.

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py` (delete dead guards, consolidate near-duplicates)
- Create: `scripts/_audit_reminder_guards.py` (one-shot hit-count measurement)
- Create: `artifacts/evidence/reminder-model-compare/2026-05-12-guard-coverage.json`

### Steps

- [ ] **D1: Write the hit-count harness**

Create `scripts/_audit_reminder_guards.py`:

```python
"""Measure which reminder_intent guards actually fire on the corpus.

For each _should_retry_for_* / _should_clarify_* / _drop_* / _input_is_*
helper, count the corpus cases where the helper returns True. Helpers
with hit_count == 0 are dead code and can be deleted.
"""
import inspect
import json
from pathlib import Path

import agent.agno_agent.capabilities.reminder_intent as rim
from scripts._phase0_time_accuracy import load_cases_and_expectations

GUARD_PREFIXES = ("_should_retry_for_", "_should_clarify_", "_drop_",
                  "_input_is_", "_input_has_", "_normalize_",
                  "_should_treat_", "_is_today_time_range_",
                  "_is_bounded_cadence_", "_is_unbounded_high_frequency_")


def discover_guards():
    """Return [(name, callable, signature)] for every guard helper."""
    out = []
    for name, fn in inspect.getmembers(rim, inspect.isfunction):
        if not any(name.startswith(p) for p in GUARD_PREFIXES):
            continue
        sig = inspect.signature(fn)
        out.append((name, fn, sig))
    return sorted(out)


def call_safely(fn, sig, input_message, decision):
    """Try calling guard with different param permutations the codebase uses."""
    params = list(sig.parameters)
    try:
        if len(params) == 1:
            return bool(fn(input_message))
        if len(params) == 2:
            return bool(fn(input_message, decision))
        return None  # other shapes — skip
    except Exception:
        return None


def main():
    cases, expectations = load_cases_and_expectations()
    guards = discover_guards()
    hits = {name: 0 for name, _, _ in guards}
    skipped = {name: 0 for name, _, _ in guards}
    # Use a generic decision shape that satisfies most guards
    from types import SimpleNamespace
    decision = SimpleNamespace(
        intent_type="crud", action="create",
        title="placeholder", trigger_at="2026-05-12T10:00:00+09:00",
        operations=[], rrule="", schedule_basis="", schedule_evidence="",
        deadline_at="", new_title="", new_trigger_at="", keyword="",
        reminder_id="",
    )
    for idx_str, _ in expectations.items():
        idx = int(idx_str)
        if idx >= len(cases):
            continue
        text = cases[idx].get("input", "")
        for name, fn, sig in guards:
            result = call_safely(fn, sig, text, decision)
            if result is None:
                skipped[name] += 1
            elif result:
                hits[name] += 1
    rows = []
    for name, _, _ in guards:
        rows.append({"guard": name, "hits": hits[name], "skipped": skipped[name]})
    rows.sort(key=lambda r: r["hits"])
    print(f"{'GUARD':50s} HITS  SKIPPED")
    for r in rows:
        print(f"  {r['guard']:48s} {r['hits']:>4d}  {r['skipped']:>4d}")
    out = Path("artifacts/evidence/reminder-model-compare/2026-05-12-guard-coverage.json")
    out.write_text(json.dumps({"total_cases": len(expectations), "rows": rows},
                              ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\nWrote: {out}")
    print(f"\nDead guards (hits=0): {sum(1 for r in rows if r['hits']==0)}")
    print(f"Low-hit (1-2): {sum(1 for r in rows if 0 < r['hits'] <= 2)}")
    print(f"Used (>=3): {sum(1 for r in rows if r['hits'] >= 3)}")


if __name__ == "__main__":
    main()
```

- [ ] **D2: Run the audit**

Run: `.venv/bin/python scripts/_audit_reminder_guards.py`

This is local-only — no LLM calls, just running pure Python predicates against corpus inputs. Should finish in seconds.

Read the table. Note the count of dead guards (`hits=0`).

- [ ] **D3: Delete dead guards**

For each guard with `hits=0` in the report:
1. Grep the codebase for its name: `grep -n "_should_xyz" agent/agno_agent/`
2. If the only references are the definition + the `ReminderIntentPort.run` call site, delete both.
3. If there are other references (e.g. other guards composing it), leave it for now and add to a "deferred" list.

Run `pytest tests/unit/agent/test_reminder_intent_capability.py -q` after every 3-5 deletions. If a test breaks, the guard wasn't actually dead — the corpus doesn't cover its case but the test does. Add the test's input to corpus instead (as `severity: critical` if it tests user-visible damage).

- [ ] **D4: Consolidate low-hit guards**

For guards with `hits ∈ {1, 2}`, look for near-duplicates. Common pattern: `_normalize_chinese_period_5min` and `_normalize_chinese_period_10min` differ only in a literal number. Merge into one parameterized helper.

This is a judgment call. If a low-hit guard tests a structural pattern that may grow (e.g. "before-hour Chinese clocks" — likely more cases coming), keep it. If it's a one-off bandage, fold its body into the calling guard.

- [ ] **D5: Run the severity-tiered eval gate (from Task B)**

Run: `.venv/bin/python scripts/user_path_normal_eval.py --run-all`

Expected: critical=100%, important≥95%, nice≥80%. If a tier fails, you deleted a guard that was actually protecting some case. Restore it.

- [ ] **D6: Update the doc**

In `docs/issues/2026-05-12-reminder-detect-model-bake-off.md`, add to the "Follow-up" or "Forward changes" section:

```markdown
- Guard audit: scripts/_audit_reminder_guards.py measured per-guard
  hit count on the corpus; <N> dead guards removed, <M> consolidated.
  reminder_intent.py shrank from 2918 lines to <new> lines. Tiered
  eval (critical 100%, important ≥95%, nice ≥80%) still passes.
```

- [ ] **D7: Commit**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py \
        scripts/_audit_reminder_guards.py \
        artifacts/evidence/reminder-model-compare/2026-05-12-guard-coverage.json \
        docs/issues/2026-05-12-reminder-detect-model-bake-off.md
git commit -m "$(cat <<'COMMIT_EOF'
Prune dead and near-duplicate reminder_detect guards

After the v2 prompt diet, guard hit rates measured by
scripts/_audit_reminder_guards.py showed <N> guards with zero corpus
hits and <M> guards with ≤2 hits. Removed the dead set; consolidated
near-duplicates. Tiered eval still passes.

reminder_intent.py: 2918 → <new> lines.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
COMMIT_EOF
)"
```

---

## Task E: Diet INSTRUCTIONS_ORCHESTRATOR and Other Prompts [P2, ~2-3 days]

**Why:** ADR 0004 budgets are deliberate ceilings. `INSTRUCTIONS_ORCHESTRATOR` is at ~989 tokens against a 1100 budget — one more rule and it breaks the gate. Apply the same v2 diet pattern that worked for `INSTRUCTIONS_REMINDER_DETECT`.

**Files:**
- Modify: `agent/prompt/agent_instructions_prompt.py` (slim ORCHESTRATOR, possibly CHAT_RESPONSE)
- Modify: `tests/unit/prompt/test_prompt_token_budgets.py` (tighten budgets after diet)

### Steps

- [ ] **E1: Read what ORCHESTRATOR actually does**

Read `agent/prompt/agent_instructions_prompt.py:138-192`. Note which sections feel like rule sprawl (lots of bullets explaining edge cases) versus core schema (concise format definition).

- [ ] **E2: Identify diet targets**

The `need_reminder_detect` and `need_web_search` sections are the largest. Each has both a "set to true" enumeration and a "set to false" enumeration with overlapping edge cases. The format follows what reminder_detect v1 looked like before the diet.

Compress each section to:
- One sentence stating the *positive* signal that triggers true
- One sentence stating the *negative* signal that overrides it
- A "when uncertain, default to X" line

Drop every edge case that's an instance of those signals (the model will reach the same conclusion from the general principle on cases not enumerated).

- [ ] **E3: Apply the diet**

Edit `INSTRUCTIONS_ORCHESTRATOR` in `agent/prompt/agent_instructions_prompt.py`. Target ~600-700 approximate tokens. Use the v2 reminder_detect format as the template:

- Markdown sections (`## need_reminder_detect`)
- ~3-5 bullet points per section, each ≤25 words
- No "any of the following" enumerations
- One "default" sentence

Keep the schema-format details (`timezone_action ∈ none/direct_set/proposal`, etc) — those are not rule sprawl, they're contract.

- [ ] **E4: Run the budget test**

Run: `.venv/bin/python -m pytest tests/unit/prompt/test_prompt_token_budgets.py -v`

Expected: PASS, with `INSTRUCTIONS_ORCHESTRATOR` ~600-700 tokens, well under the 1100 budget.

- [ ] **E5: Tighten the budget to lock in the diet**

In `tests/unit/prompt/test_prompt_token_budgets.py`, lower the ORCHESTRATOR budget from 1100 to (your new count + 100 headroom):

```python
PROMPT_BUDGETS: dict[str, tuple[str, int]] = {
    "INSTRUCTIONS_REMINDER_DETECT": (INSTRUCTIONS_REMINDER_DETECT, 1000),
    "INSTRUCTIONS_ORCHESTRATOR": (INSTRUCTIONS_ORCHESTRATOR, 800),  # was 1100
    # ... others unchanged
}
```

Run the test again. Expected: PASS.

- [ ] **E6: Spot-check orchestrator behavior**

Run the orchestrator unit tests:

```bash
.venv/bin/python -m pytest tests/unit/agent/ -q -k "orchestrator"
```

Expected: PASS.

Optionally trigger an end-to-end orchestrator decision on a known input:

```python
.venv/bin/python -c "
import asyncio
from agent.agno_agent.agents import orchestrator_agent
async def go():
    r = await orchestrator_agent.arun(input='17:00提醒我喝水')
    print(r.content)
asyncio.run(go())
"
```

The output should still set `need_reminder_detect=True`.

- [ ] **E7: Commit**

```bash
git add agent/prompt/agent_instructions_prompt.py \
        tests/unit/prompt/test_prompt_token_budgets.py
git commit -m "$(cat <<'COMMIT_EOF'
Diet INSTRUCTIONS_ORCHESTRATOR and tighten budget

Apply the v2 reminder_detect compression pattern: replace "any of the
following" rule lists with one positive signal + one negative override
+ default. Budget lowered from 1100 to 800 tokens to lock the diet in.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
COMMIT_EOF
)"
```

---

## Task F: Remove the Reminder-Intent Preflight Path [P2, ~1-2 days, depends on A]

**Why:** `agent/agno_agent/runtime/agent_runtime.py:336-415` defines `_should_preflight_reminder_intent` and `_preflight_reminder_intent_result`, which run the reminder_intent capability *before* the main agent turn for inputs that look reminder-shaped. This is a workaround for v1 prompt overload — the main agent's prompt was so big it couldn't reliably decide which tool to invoke, so the runner pre-ran one. With v2 prompt budgets, the main agent should be able to make this decision itself.

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py` (remove preflight code)
- Modify: `tests/unit/agent/test_agent_runtime_*.py` (remove preflight assertions)

### Steps

- [ ] **F1: Read what preflight does and confirm it's a workaround**

Read `agent/agno_agent/runtime/agent_runtime.py:336-525` (the preflight functions and their call site). Read the surrounding comments. Confirm there is no functional requirement other than "main agent isn't reliable enough".

If the preflight enables a feature that the main agent legitimately cannot provide (e.g., faster pre-LLM signal for downstream routing), STOP and report this back. Don't remove it without understanding.

- [ ] **F2: Find the tests that pin preflight behavior**

Run: `grep -rln "preflight" tests/`

For each test file that references `preflight`, read the test and decide:
- Does it assert that preflight *fires*? — that's an implementation detail; the test should assert the runtime *result* instead.
- Does it assert that preflight is *skipped* in a given mode? — that's testing an absence, leave for now.

- [ ] **F3: Write a runtime regression test that protects the user-visible behavior**

Before removing preflight, ensure there's a test that pins the user-visible outcome (correct intent_type returned, correct tool called) for a typical reminder input. If `tests/unit/agent/test_agent_runtime_*.py` already has such a test, note its name. If not, add:

```python
# In tests/unit/agent/test_agent_runtime_construction.py or similar
@pytest.mark.asyncio
async def test_runtime_routes_reminder_request_to_capability_without_preflight():
    """Verify the main agent reaches the reminder_intent tool for a
    typical reminder input — i.e. the preflight was not load-bearing."""
    # Minimal end-to-end: build an AgentRunContext, call the runtime,
    # confirm the resulting decision has intent_type='crud' for
    # "17:00 提醒我喝水". Use the standard test fixtures already in
    # this file for context construction.
    # ... use existing fixtures; adapt from a similar end-to-end test ...
```

If this test is impossible to write at unit level (requires an actual LLM), use a mocked agent that returns a fixed decision and verify the runtime forwards it correctly.

Run the new test. Expected: PASS.

- [ ] **F4: Remove preflight code**

Open `agent/agno_agent/runtime/agent_runtime.py`. Delete:
- `_should_preflight_reminder_intent` (function and any helper)
- `_preflight_reminder_intent_result` (function and any helper)
- The call to `_preflight_reminder_intent_result(...)` inside the main runtime function (the one with the trace tag `"preflight_reminder_intent"`)

Also delete any imports that become unused.

- [ ] **F5: Run the protective tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/ -q`

Expected: all pass except tests that *directly* asserted preflight was firing. Those need to be updated or removed.

- [ ] **F6: Update or remove preflight-specific tests**

For each test that asserted preflight behavior:
- If it was asserting that the runtime works correctly, replace the assertion with one against the user-visible outcome (intent_type, tool call).
- If it was only asserting "preflight fires", delete it (it was testing implementation, not behavior).

- [ ] **F7: Spot-check the Phase 0 time accuracy regression**

Run: `.venv/bin/python scripts/_phase0_time_accuracy.py 2>&1 | tail -10`

The exact-rate should be at least as high as after Task A. If it drops more than 2 pp, the preflight was load-bearing in a way that wasn't obvious from reading the code. Restore preflight and report findings.

- [ ] **F8: Update the issue follow-up note**

In `docs/issues/2026-05-12-reminder-detect-model-bake-off.md`, add a note:

```markdown
- The `_preflight_reminder_intent_result` path in
  `agent/agno_agent/runtime/agent_runtime.py` was a workaround for v1
  prompt overload (main agent's prompt was too big to reliably decide
  tool invocation). Removed after Phase 0 confirmed the v2 main-agent
  prompt routes reminder inputs correctly without the preflight.
```

- [ ] **F9: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py \
        tests/unit/agent/ \
        docs/issues/2026-05-12-reminder-detect-model-bake-off.md
git commit -m "$(cat <<'COMMIT_EOF'
Remove reminder_intent preflight workaround

The preflight code in agent_runtime.py pre-ran the reminder_intent
capability before the main agent turn because the v1 prompt was so
overloaded the main agent could not reliably route. After the v2
prompt diet (commit 8d2a968), Phase 0 confirms the main agent routes
reminder inputs correctly without the preflight. Removed.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
COMMIT_EOF
)"
```

---

## Coordination Notes

- **Parallel-safe pairs:** A + B + C can all run on separate branches at the same time. They touch different files (A: prompt builder + few-shot, B: corpus json + eval runner, C: capability guards + tests).
- **Sequential pair:** D depends on B (severity tiers) and A (final prompt shape). Don't start D until B is merged.
- **Sequential pair:** F depends on A (the few-shot decision affects how stable the v2 prompt feels in practice). Don't start F until A is merged.
- **E is independent** of all the others; can run any time.

After all 6 are merged, append a one-line resolution note to
`docs/issues/2026-05-12-reminder-detect-model-bake-off.md` and update
`docs/issues/issue-gc-state.yaml` to mark this investigation complete.
