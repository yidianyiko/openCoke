---
kind: implementation_plan
status: ready
authors:
  - YDYK
created: 2026-05-24
spec: docs/superpowers/specs/2026-05-24-reminder-intent-llm-semantic-boundary-design.md
---

# reminder_intent LLM Semantic Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ~16 regex/keyword semantic-classification helpers in `agent/agno_agent/capabilities/reminder_intent.py` with a single `clarification_reason` enum field on `ReminderDetectDecision`, plus prompt + few-shot teaching `intent_type='discussion'` to absorb five non-request topic shapes. Keep all schema/state-machine/time-math/cross-field-consistency/clause-locality helpers.

**Architecture:** Single `ReminderDetectAgent` LLM call (no new model, no second call). One new schema enum field replaces two free-form fields (`reason`, `clarification_question`). Code maps `clarification_reason → (missing_fields, safety_boundary, template)` via a module-level dict (single source of truth). Cross-field consistency, clause locality, and time normalisation stay in code as fail-close guards against LLM hallucination. Six-step hard cutover with eval gate on each step.

**Tech Stack:** Python 3.12, pydantic v2 (schema + validators), agno Agent runtime, GLM-5.1 thinking-off via SiliconFlow (model lock; see project memory), pytest.

**Read first (every task):**

- `CLAUDE.md` — repo conventions, no compatibility shims, evidence-before-assertions.
- `docs/superpowers/specs/2026-05-24-reminder-intent-llm-semantic-boundary-design.md` — the source of truth.
- `docs/adr/0004-per-agent-prompt-budget-discipline.md` — prompt budget rationale.

**Global verification commands** (every phase must pass these before commit):

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/prompt/test_agent_instructions_prompt.py tests/unit/prompt/test_prompt_token_budgets.py -v
```

Eval subset (run before *and after* each phase; record both numbers in the commit body):

```bash
.venv/bin/python scripts/run_reminder_intent_eval.py --subset 30case
```

If the eval command does not exist yet under that exact path, use whatever entry point `docs/fitness/coke-verification-matrix.md` lists for `reminder-intent`; do not invent a new script.

---

## File Inventory

**Modify:**

- `agent/agno_agent/schemas/reminder_detect_schema.py` — add `clarification_reason`; later remove `reason` and `clarification_question`.
- `agent/agno_agent/capabilities/reminder_intent.py` — delete ~16 helpers across phases; add reason→template mapping; rewrite `run` control flow.
- `agent/prompt/agent_instructions_prompt.py` — compress existing prompt, add Topic classification + Clarification reason codes sections, remove `clarification_question` line.
- `agent/prompt/reminder_few_shot.json` — add 4 clarification + 5 discussion examples; later update clarify entries to use `clarification_reason` instead of `clarification_question`.
- `tests/unit/test_reminder_detect_structured_output.py` — assertions for new field; delete `clarification_question` test; update existing decisions.
- `tests/unit/agent/test_reminder_intent_capability.py` — switch clarification paths to reason-driven; delete tests covering deleted helpers; keep cross-field/locality tests.

**Create:** none.

**Delete (entire functions across phases):**

| Phase | Function | Location |
|---|---|---|
| 3 | `_should_clarify_date_only_create` | `reminder_intent.py:1002` |
| 3 | `_should_clarify_ambiguous_time_range_create` | `reminder_intent.py:1015` |
| 3 | `_should_clarify_completion_condition_create` | `reminder_intent.py:1024` |
| 3 | `_should_clarify_status_only_content_create` | `reminder_intent.py:1044` |
| 3 | `_input_has_concrete_time_without_reminder_content` | `reminder_intent.py:1573` |
| 3 | `_input_has_event_time_with_vague_advance_request` | `reminder_intent.py:1593` |
| 3 | `_input_has_one_shot_deadline_without_trigger` | `reminder_intent.py:1545` |
| 3 | `_input_has_date_reference_without_clock` | `reminder_intent.py:1829` |
| 3 | `_input_has_today_time_range_points_request` | `reminder_intent.py:1307` |
| 3 | `_input_has_large_today_time_range_points_request` | `reminder_intent.py:1316` |
| 3 | `_is_today_time_range_points_incomplete_or_recurring` | `reminder_intent.py:1288` |
| 4 | `_input_is_reminder_behavior_meta_discussion` | `reminder_intent.py:1692` |
| 4 | `_input_is_reminder_feature_work_topic` | `reminder_intent.py:1722` |
| 4 | `_input_is_plain_schedule_statement_without_reminder_request` | `reminder_intent.py:1604` |
| 4 | `_input_is_standalone_reminder_acknowledgement` | `reminder_intent.py:1665` |
| 4 | `_input_is_standalone_reminder_opt_out` | `reminder_intent.py:1639` |
| 5 | `_fallback_clarification_for_input` | `reminder_intent.py:1800` |

**Explicitly keep** (do not touch in this plan): `_drop_*`, `_title_has_local_*`, `_should_reject_*` (all of them), `_input_has_high_frequency_without_deadline`, `_input_has_bounded_cadence_deadline`, `_is_bounded_cadence_deadline_loss`, `_is_unbounded_high_frequency_cadence`, all RRULE helpers, all time-math helpers, `_normalize_*`, `_input_has_relative_delay_and_preceding_task_content`, `_input_has_next_whole_hour_reference`, `_input_has_clocked_task_before_trailing_reminder_verb`, `_explicit_scheduled_clause_count`, `_previous_clause_boundary` / `_next_clause_boundary`.

---

## Phase 1: Add `clarification_reason` schema field

**Files:**

- Modify: `agent/agno_agent/schemas/reminder_detect_schema.py:58-188` (decision class + before-validator)
- Modify: `tests/unit/test_reminder_detect_structured_output.py`

This phase only adds the field. Nothing is deleted. The model can start emitting it under the new schema; routing in `reminder_intent.py` still ignores it (next phase wires it up).

### Task 1.1: Add failing test for new field

- [ ] **Step 1: Write failing tests in `tests/unit/test_reminder_detect_structured_output.py` (append to file)**

```python
def test_reminder_detect_clarify_requires_clarification_reason():
    import pytest
    from pydantic import ValidationError
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    with pytest.raises(ValidationError, match="clarification_reason"):
        ReminderDetectDecision(intent_type="clarify", action="", clarification_reason="")


def test_reminder_detect_non_clarify_rejects_clarification_reason():
    import pytest
    from pydantic import ValidationError
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    with pytest.raises(ValidationError, match="clarification_reason"):
        ReminderDetectDecision(
            intent_type="discussion",
            action="",
            clarification_reason="date_only_missing_time",
        )


def test_reminder_detect_clarify_accepts_known_reason():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    decision = ReminderDetectDecision(
        intent_type="clarify",
        action="",
        clarification_reason="date_only_missing_time",
    )
    assert decision.clarification_reason == "date_only_missing_time"


def test_reminder_detect_rejects_unknown_clarification_reason():
    import pytest
    from pydantic import ValidationError
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="clarify",
            action="",
            clarification_reason="not_a_real_reason",
        )
```

- [ ] **Step 2: Run tests — expected FAIL (field does not exist)**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_clarify_requires_clarification_reason tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_non_clarify_rejects_clarification_reason tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_clarify_accepts_known_reason tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_rejects_unknown_clarification_reason -v
```

Expected: all four FAIL with errors like `Field "clarification_reason" does not exist` or extra-forbid.

### Task 1.2: Add the field + validator

- [ ] **Step 3: Add the `clarification_reason` field to `ReminderDetectDecision` after `reason` field (around `agent/agno_agent/schemas/reminder_detect_schema.py:154`)**

Insert (after the `reason: str = Field(...)` line):

```python
    clarification_reason: Literal[
        "",
        "date_only_missing_time",
        "ambiguous_time_range",
        "completion_condition_missing_time",
        "status_only_content",
        "deadline_without_trigger",
        "advance_offset_missing",
        "high_frequency_requires_end",
        "missing_reminder_content",
        "ambiguous_request",
    ] = Field(
        default="",
        description=(
            "Reason code that selects the clarification template. "
            "Must be non-empty when intent_type='clarify'; must be empty otherwise."
        ),
    )
```

- [ ] **Step 4: Extend `enforce_intent_field_boundaries` validator (`reminder_detect_schema.py:190-234`) to enforce the clarify ↔ reason invariant**

Add inside the `if self.intent_type == "crud":` block before the final `return self`: nothing (crud should not have a reason).

Add at the end, before the final `return self` of the non-crud path: nothing — instead add a new top-level check just after `has_write_fields = ...` (around line 205):

```python
        if self.intent_type == "clarify" and not self.clarification_reason:
            raise ValueError("clarify intent requires clarification_reason")
        if self.intent_type != "clarify" and self.clarification_reason:
            raise ValueError(
                "clarification_reason is only allowed for intent_type='clarify'"
            )
```

Place these two checks before `if self.intent_type == "crud":` so they fire regardless of branch.

- [ ] **Step 5: Run tests — expected PASS**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_clarify_requires_clarification_reason tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_non_clarify_rejects_clarification_reason tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_clarify_accepts_known_reason tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_rejects_unknown_clarification_reason -v
```

Expected: 4 PASS.

### Task 1.3: Make existing clarify tests forward-compatible

The existing test file constructs `ReminderDetectDecision(intent_type="clarify", clarification_question="…")` in several places. The new validator will reject them because `clarification_reason` is empty. Add the reason to every such test.

- [ ] **Step 6: Find every existing clarify construction**

```bash
grep -n 'intent_type="clarify"\|"intent_type": "clarify"' tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py
```

For each match, add `clarification_reason="ambiguous_request"` (or a more specific reason if the test's intent is clear) so the validator passes. The `clarification_question` field stays in this phase; it is deleted in Phase 6.

- [ ] **Step 7: Run the full test files**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py -v
```

Expected: PASS. (If a test fails because of the new validator, add `clarification_reason="ambiguous_request"` until it passes; do not edit any production code in this step.)

### Task 1.4: Verify prompt budgets still pass

- [ ] **Step 8: Run prompt tests (no prompt change yet, but proves baseline)**

```bash
.venv/bin/python -m pytest tests/unit/prompt/ -v
```

Expected: PASS.

### Task 1.5: Commit Phase 1

- [ ] **Step 9: Commit**

```bash
git add agent/agno_agent/schemas/reminder_detect_schema.py tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "$(cat <<'EOF'
feat(reminder-intent): add clarification_reason enum field

Phase 1 of moving regex-based semantic guards from
reminder_intent.py into structured LLM output. Adds the enum
field and its clarify/non-clarify invariant; no routing change.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2: Prompt diet + topic classification + reason codes + few-shot

**Files:**

- Modify: `agent/prompt/agent_instructions_prompt.py:30-92` (the prompt string)
- Modify: `agent/prompt/reminder_few_shot.json`

Current prompt: **960/1000 tokens (4% headroom), 42/60 non-empty lines (30% headroom)**. Two new sections of ≤8 lines each ≈ 16 lines and ≈ 200–250 tokens. We must compress first.

### Task 2.1: Measure exact starting baseline

- [ ] **Step 1: Snapshot the baseline tokens and lines**

```bash
.venv/bin/python -c "
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_REMINDER_DETECT
from tests.unit.prompt.test_prompt_token_budgets import approximate_tokens
lines = [l for l in INSTRUCTIONS_REMINDER_DETECT.splitlines() if l.strip()]
print(f'BASELINE tokens={approximate_tokens(INSTRUCTIONS_REMINDER_DETECT)}/1000  lines={len(lines)}/60')
"
```

Record both numbers in your scratchpad. Target post-diet: ≤880 tokens / ≤35 lines (leaves 120 tokens / 25 lines for additions plus 5% headroom).

### Task 2.2: Compress existing prompt without losing load-bearing rules

The following rules are load-bearing and **must not be deleted** (tests enforce them):

- AM/PM disambiguation block (`"prefer PM same day"` — asserted by
  `tests/unit/prompt/test_agent_instructions_prompt.py:30`).
- All four `intent_type` names appearing as `- {intent}:` (asserted by line 25).
- `"ISO 8601"` literal (line 28).
- `"Output only the structured decision"` literal (line 32).
- Current-time placeholder substitution (line 23).

Everything else can be rephrased shorter.

- [ ] **Step 2: Rewrite long bullets in `## Edge rules` and `## Schema` more compactly**

Open `agent/prompt/agent_instructions_prompt.py:68-91` and tighten. Concrete moves you can make:

1. Combine the two "Date-only" + "Time but no title" + "Completion-conditioned" + "One-shot deadline wording" bullets into a single line: `- Missing or ambiguous fields (date-only, time-only, completion-conditioned, deadline-only): clarify; do not invent defaults.`
2. Drop the "Day-of-month before reminder verb" example — the cross-field guard enforces it; the LLM does not need it explicitly.
3. Drop the "Stop/cancel/do-not-disturb" sentence — covered by `intent_type=crud + action=delete/cancel` semantics and discussion routing.

Keep the rest verbatim.

- [ ] **Step 3: Re-measure**

Re-run Step 1's command. Expected: ≤880 tokens, ≤35 non-empty lines. If not, compress further (next candidates: collapse the four `Time output` clock-handling sub-bullets into one paragraph, dropping `"Chinese clock separators such as"` since `:` matching is mechanical in code).

- [ ] **Step 4: Run prompt tests to confirm load-bearing strings still present**

```bash
.venv/bin/python -m pytest tests/unit/prompt/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit the diet**

```bash
git add agent/prompt/agent_instructions_prompt.py
git commit -m "$(cat <<'EOF'
refactor(prompt): diet reminder_detect to make room for new sections

Compresses Edge rules and Schema bullets without removing
load-bearing rules. Frees ~120 tokens for the upcoming Topic
classification and Clarification reason code sections.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 2.3: Add Topic classification section

- [ ] **Step 6: Add the section after `## Intent` block in `get_reminder_detect_instructions` (`agent/prompt/agent_instructions_prompt.py`)**

Insert exactly this block (8 non-empty lines, no `Example:` / `->` / forbidden phrases):

```
## Topic shapes that route to discussion

- meta_discussion: user is asking how the reminder system itself works.
- feature_work: user is discussing the reminder feature for development purposes.
- plain_schedule: user states their schedule without asking to be reminded.
- acknowledgement: user thanks a past reminder or alarm.
- opt_out: user says they do not want any reminders.
All five emit intent_type=discussion with empty fields.
```

- [ ] **Step 7: Re-measure budget**

Run the Step 1 measurement. Must stay ≤950 tokens / ≤43 lines (still leaving room for reason codes).

- [ ] **Step 8: Run prompt tests**

```bash
.venv/bin/python -m pytest tests/unit/prompt/ -v
```

Expected: PASS.

### Task 2.4: Add Clarification reason codes section

- [ ] **Step 9: Add the section before `## Schema` block**

```
## Clarification reason codes

For intent_type=clarify, set clarification_reason to exactly one of:
date_only_missing_time, ambiguous_time_range,
completion_condition_missing_time, status_only_content,
deadline_without_trigger, advance_offset_missing,
high_frequency_requires_end, missing_reminder_content,
ambiguous_request. Pick the most specific code; use ambiguous_request only when none of the others fits.
```

- [ ] **Step 10: Remove the now-dead line** `- clarification_question uses the same language as the user message.` from the `## Schema` block.

- [ ] **Step 11: Re-measure budget**

Must be ≤1000 tokens / ≤60 lines with ≥5% headroom on tokens.

- [ ] **Step 12: Run prompt tests**

```bash
.venv/bin/python -m pytest tests/unit/prompt/ -v
```

Expected: PASS.

- [ ] **Step 13: Commit the new sections**

```bash
git add agent/prompt/agent_instructions_prompt.py
git commit -m "$(cat <<'EOF'
feat(prompt): add topic shapes and clarification reason codes

Teaches the model to emit intent_type=discussion for the five
non-request topic shapes and to set clarification_reason on
clarify decisions. Stays within the per-agent prompt budget.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 2.5: Add few-shot examples

- [ ] **Step 14: Append 9 new entries to `agent/prompt/reminder_few_shot.json` (4 clarification + 5 discussion)**

The file is a JSON array of `{decision_class, input, decision}` objects. Append (do not remove existing entries; keep valid JSON):

```json
  {
    "decision_class": "clarify.status_only",
    "input": "提醒我没做完",
    "decision": {
      "intent_type": "clarify",
      "action": "",
      "clarification_reason": "status_only_content"
    }
  },
  {
    "decision_class": "clarify.completion_condition",
    "input": "看完书后提醒我",
    "decision": {
      "intent_type": "clarify",
      "action": "",
      "clarification_reason": "completion_condition_missing_time"
    }
  },
  {
    "decision_class": "clarify.date_only",
    "input": "5月25号提醒我交报告",
    "decision": {
      "intent_type": "clarify",
      "action": "",
      "clarification_reason": "date_only_missing_time"
    }
  },
  {
    "decision_class": "clarify.ambiguous_range",
    "input": "下午两三点提醒我开会",
    "decision": {
      "intent_type": "clarify",
      "action": "",
      "clarification_reason": "ambiguous_time_range"
    }
  },
  {
    "decision_class": "discussion.meta",
    "input": "你这个提醒功能怎么保持发出去之后还得回复啊",
    "decision": {
      "intent_type": "discussion",
      "action": ""
    }
  },
  {
    "decision_class": "discussion.feature_work",
    "input": "我们来测试一下提醒功能能不能讨论一下",
    "decision": {
      "intent_type": "discussion",
      "action": ""
    }
  },
  {
    "decision_class": "discussion.plain_schedule",
    "input": "今天晚上8点我要看电影",
    "decision": {
      "intent_type": "discussion",
      "action": ""
    }
  },
  {
    "decision_class": "discussion.acknowledgement",
    "input": "谢谢闹钟",
    "decision": {
      "intent_type": "discussion",
      "action": ""
    }
  },
  {
    "decision_class": "discussion.opt_out",
    "input": "All good, no reminders pls",
    "decision": {
      "intent_type": "discussion",
      "action": ""
    }
  }
```

Existing clarify entries (`crud.batch`, `clarify` with `clarification_question`) are left alone for now; Phase 6 updates them after the field deletion.

- [ ] **Step 15: Validate JSON parses**

```bash
.venv/bin/python -c "import json; json.load(open('agent/prompt/reminder_few_shot.json')); print('ok')"
```

Expected: `ok`.

- [ ] **Step 16: Run the existing few-shot tests if any**

```bash
.venv/bin/python -m pytest tests/unit/prompt/ tests/unit/agent/test_reminder_intent_capability.py -v -k 'few_shot or reminder_few'
```

If no matching tests, this is a no-op (acceptable).

- [ ] **Step 17: Commit few-shot additions**

```bash
git add agent/prompt/reminder_few_shot.json
git commit -m "$(cat <<'EOF'
feat(prompt): add 4 clarification + 5 discussion few-shots

Covers the new clarification_reason codes and the five
intent_type=discussion topic shapes that absorb the regex
classifiers slated for deletion in phases 3 and 4.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 2.6: Phase 2 eval gate

- [ ] **Step 18: Run global verification commands and eval subset**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/prompt/test_agent_instructions_prompt.py tests/unit/prompt/test_prompt_token_budgets.py -v
```

Then run the reminder-intent eval subset (entry point from `docs/fitness/coke-verification-matrix.md`).

Expected: 0 regressions vs Phase 1 baseline; record the numbers in the next commit. If regressed → revert Phase 2 commits and re-do the diet without losing the regressed cases.

---

## Phase 3: Route on `clarification_reason`; delete C.2 + C.3 input-only detectors

**Files:**

- Modify: `agent/agno_agent/capabilities/reminder_intent.py` (extensive)
- Modify: `tests/unit/agent/test_reminder_intent_capability.py`

### Task 3.1: Build the reason→template lookup

- [ ] **Step 1: In `reminder_intent.py`, after the imports block, add a module-level dict**

```python
_CLARIFICATION_TEMPLATES: dict[str, callable[[], "DomainExecutionResult"]] = {
    "date_only_missing_time": _date_only_missing_time_clarification_result,
    "ambiguous_time_range": _ambiguous_time_range_clarification_result,
    "completion_condition_missing_time": _completion_condition_missing_time_clarification_result,
    "status_only_content": _missing_reminder_content_clarification_result,
    "deadline_without_trigger": _deadline_without_trigger_clarification_result,
    "advance_offset_missing": _advance_offset_missing_clarification_result,
    "high_frequency_requires_end": _high_frequency_input_clarification_result,
    "missing_reminder_content": _missing_reminder_content_clarification_result,
    "ambiguous_request": lambda: _needs_clarification_result(
        summary="请补充提醒信息。",
        missing_fields=("target_reminder",),
        safety_boundary="ambiguous_request",
        required_questions=("target_reminder",),
    ),
}
```

Place it *below* the result-builder functions it references (i.e. near the end of the file), or use string lookups that resolve lazily. Concrete location: after `_needs_clarification_result` (around line 1965). Confirm the file still imports cleanly:

```bash
.venv/bin/python -c "import agent.agno_agent.capabilities.reminder_intent; print('ok')"
```

Expected: `ok`.

### Task 3.2: Write failing tests for the new routing

- [ ] **Step 2: Add tests to `tests/unit/agent/test_reminder_intent_capability.py`**

```python
import pytest
from types import SimpleNamespace


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,expected_boundary,expected_missing", [
    ("date_only_missing_time", "date_only_missing_time", ("trigger_at",)),
    ("ambiguous_time_range", "ambiguous_time_range", ("trigger_at",)),
    ("completion_condition_missing_time", "completion_condition_missing_time", ("trigger_at",)),
    ("status_only_content", "missing_reminder_content", ("title",)),
    ("deadline_without_trigger", "deadline_without_trigger", ("trigger_at",)),
    ("advance_offset_missing", "advance_offset_missing", ("advance_offset",)),
    ("high_frequency_requires_end", "high_frequency_requires_end", ("trigger_at", "end_time")),
    ("missing_reminder_content", "missing_reminder_content", ("title",)),
    ("ambiguous_request", "ambiguous_request", ("target_reminder",)),
])
async def test_reminder_intent_port_routes_clarification_reason_to_template(
    reason, expected_boundary, expected_missing,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=SimpleNamespace(
                intent_type="clarify",
                action="",
                clarification_reason=reason,
            ))

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("doesn't matter", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary=expected_boundary,
        missing_fields=expected_missing,
    )
```

`FakeExecutor`, `_run_context`, and `_assert_needs_clarification` already exist in the test file — reuse them. Place this test next to the other clarify-path tests.

- [ ] **Step 3: Run the new test — expected FAIL**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_clarification_reason_to_template -v
```

Expected: FAIL (routing not yet wired).

### Task 3.3: Wire routing into `ReminderIntentPort.run`

- [ ] **Step 4: Edit `ReminderIntentPort.run` (`reminder_intent.py:112-285`)**

Find the existing clarify-handling block:

```python
        if _is_clarification_decision(decision):
            if _input_is_standalone_reminder_opt_out(
                input_message
            ) or _input_is_reminder_behavior_meta_discussion(
                input_message
            ) or _input_is_reminder_feature_work_topic(input_message):
                return _no_action_discussion_result()
            return _clarification_result(decision)
```

Replace it with:

```python
        if _is_clarification_decision(decision):
            reason = str(
                _decision_value(decision, "clarification_reason") or ""
            ).strip()
            builder = _CLARIFICATION_TEMPLATES.get(reason)
            if builder is None:
                return _invalid_decision_clarification_result()
            return builder()
```

Keep the `_is_clarification_decision` definition pointing at `intent_type='clarify'` only — drop the dependency on `clarification_question` non-empty (it will be deleted in Phase 6; for now, allow either signal to pass):

```python
def _is_clarification_decision(decision: Any) -> bool:
    return _decision_value(decision, "intent_type") == "clarify"
```

- [ ] **Step 5: Run the parametrised test — expected PASS**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_clarification_reason_to_template -v
```

Expected: 9 PASS.

### Task 3.4: Delete the four `_should_clarify_*` helpers and their call sites

- [ ] **Step 6: Remove the four call sites in `ReminderIntentPort.run` (`reminder_intent.py:249-256`)**

Delete:

```python
        if _should_clarify_date_only_create(input_message, decision):
            return _date_only_missing_time_clarification_result()
        if _should_clarify_ambiguous_time_range_create(input_message, decision):
            return _ambiguous_time_range_clarification_result()
        if _should_clarify_completion_condition_create(input_message, decision):
            return _completion_condition_missing_time_clarification_result()
        if _should_clarify_status_only_content_create(input_message, decision):
            return _missing_reminder_content_clarification_result()
```

- [ ] **Step 7: Delete the four functions (`reminder_intent.py:1002-1060`)**

Delete `_should_clarify_date_only_create`, `_should_clarify_ambiguous_time_range_create`, `_should_clarify_completion_condition_create`, `_should_clarify_status_only_content_create`.

- [ ] **Step 8: Run unit tests; expect failures only on tests covering the deleted helpers**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -v 2>&1 | head -120
```

Read failures. For each failing test:

- If it asserts that the LLM-side `clarify + reason` path produces the same outcome: rewrite it to drive `clarification_reason` in the fake decision instead of relying on regex on input.
- If it tested only the regex helper in isolation: delete it.

- [ ] **Step 9: Run again — expected PASS**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -v
```

Expected: PASS.

### Task 3.5: Delete the seven C.3 input-only detectors and call sites

- [ ] **Step 10: Find call sites for each deletion target**

```bash
for fn in _input_has_concrete_time_without_reminder_content \
          _input_has_event_time_with_vague_advance_request \
          _input_has_one_shot_deadline_without_trigger \
          _input_has_date_reference_without_clock \
          _input_has_today_time_range_points_request \
          _input_has_large_today_time_range_points_request \
          _is_today_time_range_points_incomplete_or_recurring; do
  echo "=== $fn ==="
  grep -rn "$fn" agent/ tests/ 2>/dev/null
done
```

Expected: call sites mostly inside `reminder_intent.py` (`run` body) and `_fallback_clarification_for_input`, plus a few unit tests covering the helpers in isolation.

- [ ] **Step 11: Remove call sites in `ReminderIntentPort.run` (around `reminder_intent.py:186-203`)**

Delete:

```python
        if _should_execute_decision(
            decision
        ) and _input_has_large_today_time_range_points_request(input_message):
            return _ambiguous_time_range_clarification_result()
        if _should_execute_decision(
            decision
        ) and _is_today_time_range_points_incomplete_or_recurring(
            input_message, decision
        ):
            return _ambiguous_time_range_clarification_result()
```

The model now emits `clarification_reason="ambiguous_time_range"` when needed — no input scanning.

- [ ] **Step 12: Remove the seven function definitions**

Delete the bodies of `_input_has_concrete_time_without_reminder_content` (1573), `_input_has_event_time_with_vague_advance_request` (1593), `_input_has_one_shot_deadline_without_trigger` (1545), `_input_has_date_reference_without_clock` (1829), `_input_has_today_time_range_points_request` (1307), `_input_has_large_today_time_range_points_request` (1316), `_is_today_time_range_points_incomplete_or_recurring` (1288).

- [ ] **Step 13: `_fallback_clarification_for_input` still calls some of these — update it temporarily**

Inside `_fallback_clarification_for_input` (1800), the branches that called the deleted detectors must be removed. Simplify the body to:

```python
def _fallback_clarification_for_input(
    input_message: str,
    fallback: DomainExecutionResult,
) -> DomainExecutionResult:
    return fallback
```

(Phase 5 deletes the function entirely; for now, neuter it so imports do not break.)

- [ ] **Step 14: Run unit tests**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/test_reminder_detect_structured_output.py -v
```

Expected: PASS. (Some tests may need to be deleted if they only exercised the now-removed input detectors — read the failure and delete the test.)

### Task 3.6: Phase 3 commit + eval gate

- [ ] **Step 15: Run all verification commands**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/prompt/ -v
```

Plus eval subset (record diff vs Phase 2).

- [ ] **Step 16: Commit Phase 3**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "$(cat <<'EOF'
refactor(reminder-intent): route clarify on reason code; drop C.2 + C.3

Replaces 4 _should_clarify_* helpers and 7 _input_has_* detectors
with a clarification_reason -> template lookup. Regex on raw input
no longer drives clarification routing. Cross-field consistency
and clause-locality guards untouched.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

If eval regressed: revert and revisit the prompt + few-shot in Phase 2 (likely missing coverage for a clarification reason the LLM is now guessing wrong).

---

## Phase 4: Delete C.1 topic classifiers

**Files:**

- Modify: `agent/agno_agent/capabilities/reminder_intent.py`
- Modify: `tests/unit/agent/test_reminder_intent_capability.py`

`intent_type='discussion'` now routes the five topic shapes directly (taught by Phase 2 prompt + few-shot). Backstops go away.

### Task 4.1: Add a failing test that `discussion` routes to no_action

- [ ] **Step 1: Add test (placement: near other no-action tests)**

```python
@pytest.mark.asyncio
async def test_reminder_intent_port_routes_intent_discussion_to_no_action():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=SimpleNamespace(
                intent_type="discussion",
                action="",
            ))

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("你这个提醒功能怎么保持发出去之后还得回复啊", _run_context())

    _assert_no_action(result)
```

- [ ] **Step 2: Run — expected PASS (existing code already handles this via early discussion check; but if absent, add the early check first)**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_intent_discussion_to_no_action -v
```

Expected: PASS.

### Task 4.2: Add the early `discussion` short-circuit (defensive)

- [ ] **Step 3: In `ReminderIntentPort.run`, add immediately after `_decision_from_response`**

```python
        if _decision_value(decision, "intent_type") == "discussion":
            return _no_action_discussion_result()
```

This makes the path that the deleted backstops protected explicit and minimal.

### Task 4.3: Remove the five C.1 call sites + functions

- [ ] **Step 4: Find all call sites**

```bash
for fn in _input_is_reminder_behavior_meta_discussion \
          _input_is_reminder_feature_work_topic \
          _input_is_plain_schedule_statement_without_reminder_request \
          _input_is_standalone_reminder_acknowledgement \
          _input_is_standalone_reminder_opt_out; do
  echo "=== $fn ==="
  grep -rn "$fn" agent/ tests/ 2>/dev/null
done
```

- [ ] **Step 5: Remove every call site inside `ReminderIntentPort.run` and `_fallback_clarification_for_input` (the latter is already a one-liner from Phase 3; leave it as `return fallback`)**

Concrete lines in `run` (current file, before edits this phase): 147–224. Delete every clause that calls one of the five.

- [ ] **Step 6: Delete the five function bodies**

Delete `_input_is_reminder_behavior_meta_discussion`, `_input_is_reminder_feature_work_topic`, `_input_is_plain_schedule_statement_without_reminder_request`, `_input_is_standalone_reminder_acknowledgement`, `_input_is_standalone_reminder_opt_out`.

### Task 4.4: Update tests that proved backstop behaviour

The four tests at lines 2105, 2131, 2156, 2183 (per the spec risk table) currently force a fake LLM to emit `crud + cancel/complete` and expect no_action. With the backstops gone, those tests **no longer model real behaviour** — the LLM is supposed to emit `discussion` for those inputs.

- [ ] **Step 7: For each of those four tests, change the fake decision to `intent_type="discussion", action=""` and re-assert no_action**

This proves the new contract: when the LLM correctly classifies, the port routes to no_action. (The Phase 5/Risk table monitoring acceptance still stands for the case where the LLM gets it wrong in production.)

If a test was specifically testing the backstop ("model says crud-cancel but input is opt-out"), delete the test entirely. Record the deletion in the commit message.

- [ ] **Step 8: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -v
```

Expected: PASS.

### Task 4.5: Phase 4 commit + eval gate

- [ ] **Step 9: Verification gate**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/prompt/ -v
```

Plus eval subset, plus pay special attention to the discussion cases added in Phase 2 few-shots.

- [ ] **Step 10: Commit**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "$(cat <<'EOF'
refactor(reminder-intent): drop C.1 regex topic classifiers

intent_type='discussion' now routes the five non-request topic
shapes (meta_discussion / feature_work / plain_schedule /
acknowledgement / opt_out) directly. Backstops removed per the
risk acceptance documented in the spec. Tests that proved the
backstops were rewritten to assert the LLM-classified contract.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

If eval regressed (especially `谢谢闹钟` or `All good, no reminders pls`): revert this phase **only**, add more few-shot coverage in Phase 2, retry Phase 4. Do not restore the regex.

---

## Phase 5: Simplify fallback

**Files:**

- Modify: `agent/agno_agent/capabilities/reminder_intent.py`

`_fallback_clarification_for_input` has been a passthrough since Phase 3. Now delete it.

### Task 5.1: Inline the fallback at every call site

- [ ] **Step 1: Find call sites**

```bash
grep -n '_fallback_clarification_for_input' agent/agno_agent/capabilities/reminder_intent.py
```

- [ ] **Step 2: Replace every call**

Every `_fallback_clarification_for_input(input_message, X)` becomes simply `X`. Examples:

```python
return _fallback_clarification_for_input(
    input_message,
    _invalid_decision_clarification_result(),
)
```

becomes:

```python
return _invalid_decision_clarification_result()
```

Likewise for `_timeout_clarification_result()`.

### Task 5.2: Delete the function

- [ ] **Step 3: Delete the body of `_fallback_clarification_for_input`**

### Task 5.3: Phase 5 verification + commit

- [ ] **Step 4: Run gate**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/prompt/ -v
```

Plus eval subset.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py
git commit -m "$(cat <<'EOF'
refactor(reminder-intent): delete _fallback_clarification_for_input

The function has been a passthrough since clarification routing
moved to clarification_reason. Inline its callers and remove the
indirection.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6: Delete `reason` and `clarification_question` schema fields (breaking)

**Files:**

- Modify: `agent/agno_agent/schemas/reminder_detect_schema.py`
- Modify: `agent/agno_agent/capabilities/reminder_intent.py`
- Modify: `agent/prompt/reminder_few_shot.json`
- Modify: `tests/unit/test_reminder_detect_structured_output.py`
- Modify: `tests/unit/agent/test_reminder_intent_capability.py`

### Task 6.1: Add failing tests that the fields are gone

- [ ] **Step 1: Add a test**

```python
def test_reminder_detect_decision_rejects_clarification_question_kwarg():
    import pytest
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    with pytest.raises(Exception):
        ReminderDetectDecision(
            intent_type="clarify",
            clarification_reason="ambiguous_request",
            clarification_question="anything",
        )


def test_reminder_detect_decision_rejects_reason_kwarg():
    import pytest
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    with pytest.raises(Exception):
        ReminderDetectDecision(intent_type="discussion", reason="anything")
```

- [ ] **Step 2: Run — expected FAIL (fields still allowed)**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_decision_rejects_clarification_question_kwarg tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_decision_rejects_reason_kwarg -v
```

### Task 6.2: Remove the two fields from the schema

- [ ] **Step 3: Edit `agent/agno_agent/schemas/reminder_detect_schema.py`**

Delete the `clarification_question: str = Field(...)` declaration (around line 146) and the `reason: str = Field(...)` declaration (around line 154).

Update `normalize_intent_from_action` (line 156): remove every reference to `clarification_question`. The block:

```python
        clarification_question = str(data.get("clarification_question") or "").strip()
        explicit_intent = str(data.get("intent_type") or "").strip()
        if clarification_question and explicit_intent == "clarify":
            return _strip_executable_fields_for_clarification(data)
```

becomes (replace with):

```python
        explicit_intent = str(data.get("intent_type") or "").strip()
        clarification_reason = str(data.get("clarification_reason") or "").strip()
        if clarification_reason and explicit_intent == "clarify":
            return _strip_executable_fields_for_clarification(data)
```

And the later block:

```python
        if clarification_question and not has_executable_fields:
            return {**data, "intent_type": "clarify", "action": ""}
```

becomes:

```python
        if clarification_reason and not has_executable_fields:
            return {**data, "intent_type": "clarify", "action": ""}
```

Update `_strip_executable_fields_for_clarification` (line 318) — remove `"clarification_question"` from the list it does not strip (it should already not include reason or clarification_question; verify and adjust).

### Task 6.3: Remove field reads in `reminder_intent.py`

- [ ] **Step 4: Find references**

```bash
grep -n 'clarification_question\|"reason"' agent/agno_agent/capabilities/reminder_intent.py
```

- [ ] **Step 5: Edit `_clarification_result` (`reminder_intent.py:1749`)**

The function is no longer called from any place (Phase 3 replaced the call with `_CLARIFICATION_TEMPLATES`). Delete it.

- [ ] **Step 6: Delete `_is_clarification_decision`'s old form if it still checks `clarification_question`**

Already simplified in Phase 3 Task 3.3 Step 4 — verify by reading the function. Body should be:

```python
def _is_clarification_decision(decision: Any) -> bool:
    return _decision_value(decision, "intent_type") == "clarify"
```

### Task 6.4: Update few-shot data and unit tests

- [ ] **Step 7: Remove `clarification_question` from every existing entry in `agent/prompt/reminder_few_shot.json`**

For each clarify entry, replace:

```json
"clarification_question": "<some text>"
```

with `"clarification_reason": "<enum value>"`, using this mapping:

- Input has a clock/date but title is missing or generic → `"missing_reminder_content"`.
- Input has a date but no clock → `"date_only_missing_time"`.
- Input has a deadline word ("之前", "before", "by") but no remind time → `"deadline_without_trigger"`.
- Input says "提前提醒" but no offset → `"advance_offset_missing"`.
- Input has high-frequency cadence ("每小时", "每分钟") with no end → `"high_frequency_requires_end"`.
- Input has title "没做完"-style only → `"status_only_content"`.
- Input has ambiguous range ("两三点", "3-4 点") → `"ambiguous_time_range"`.
- Input is "after I finish X" with no clock → `"completion_condition_missing_time"`.
- Anything else → `"ambiguous_request"`.

Concretely the existing `clarify` entry (`提醒我每天打卡多邻国，学西班牙语`) has cadence "每天" + reminder verbs + no clock; that maps to `"missing_reminder_content"` is wrong (title is present). It is missing a specific clock — closest enum is `"date_only_missing_time"` (recurring → still needs a clock). Use that.

- [ ] **Step 8: Update `tests/unit/test_reminder_detect_structured_output.py`**

Search for every `clarification_question=` and every `.clarification_question` assertion. Delete the assertions or rewrite them to assert `clarification_reason`. Delete `test_reminder_detect_clarification_question_schema_keeps_current_language` entirely (per spec §4.1).

- [ ] **Step 9: Update `tests/unit/agent/test_reminder_intent_capability.py`**

Search and replace as in Step 8.

### Task 6.5: Update prompt to drop any leftover wording

- [ ] **Step 10: Confirm `agent/prompt/agent_instructions_prompt.py` has no `clarification_question` mention**

```bash
grep -n clarification_question agent/prompt/agent_instructions_prompt.py
```

Expected: no matches (already removed in Phase 2 Step 10). If any remain, delete them.

### Task 6.6: Final verification gate

- [ ] **Step 11: Run everything**

```bash
.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/prompt/ -v
```

Plus (use `git log --oneline | head -10` to count this plan's commits and substitute the right `HEAD~N`; typically 8 commits from Phase 1.5 + Phase 2.5/3/3/3 + Phase 3.6 + Phase 4.5 + Phase 5.3 + Phase 6.7):

```bash
zsh scripts/suggest-verification --base HEAD~8
zsh scripts/review-trigger --base HEAD~8
```

Plus reminder-intent eval subset (record final numbers vs Phase 1 baseline).

Expected: all PASS; 0 eval regressions; the +10–20 new cases pass.

### Task 6.7: Final commit

- [ ] **Step 12: Commit**

```bash
git add agent/agno_agent/schemas/reminder_detect_schema.py agent/agno_agent/capabilities/reminder_intent.py agent/prompt/reminder_few_shot.json tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "$(cat <<'EOF'
refactor(reminder-intent): drop reason and clarification_question schema fields

Completes the LLM semantic boundary migration. The reason field
had no consumers and was dead. clarification_question is fully
replaced by clarification_reason -> code-side template lookup,
removing the last duplicate routing surface.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Post-merge monitoring

Per spec §5, observe `reminder.{create,cancel,complete}.count` for 7 days after merge. Any anomalous spike attributable to LLM misclassifying English opt-out (`All good, no reminders pls`) or Chinese acknowledgement (`谢谢闹钟`) as crud → revert Phase 4 only and add a minimal regex backstop limited to those two exact patterns. Do not restore the rest of C.1.

## Out of scope

- No changes to multi-agent routing (`docs/superpowers/specs/2026-05-22-multi-agent-routing-design.md`).
- No changes to `command_executor`, tool protocol, or reminder data model.
- No changes to `DomainExecutionResult` or `ReplyContract` contracts.
- No regex restoration on title clause-locality, cross-field consistency, or RRULE validation (all kept as-is per spec §3.4).
