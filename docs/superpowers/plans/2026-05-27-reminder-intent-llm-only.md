---
title: Reminder Intent — LLM-Only Migration
status: active
created: 2026-05-27
owner: YDYK
kind: plan
---

# Reminder Intent LLM-Only Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every keyword/regex code path that performs semantic intent classification in the reminder pipeline so that intent recognition, slot extraction, and cadence shape are produced exclusively by the `ReminderDetectAgent` LLM. Keep only true output guardrails (write-claim safety net) and pure data-format helpers.

**Architecture:** `ReminderIntentCapability.run` currently sandwiches the detector LLM call between (a) pre-LLM keyword shortcuts that bypass the LLM, and (b) a post-LLM regex shadow layer that patches the detector's structured decision. Both layers violate `[[feedback_no_keyword_routing]]`. The detector prompt in `agent/prompt/agent_instructions_prompt.py:get_reminder_detect_instructions` already enumerates every intent (`crud`/`clarify`/`query`/`discussion`), every action (`create`/`update`/`delete`/`complete`/`batch`/`list`), every clarification reason, target-selector handling, snooze semantics, high-frequency-end requirement, and recurrence cadence rules. The LLM is therefore already responsible for these decisions; the regex layers are redundant compensation. We delete the layers, route empty/ambiguous detector output to clarification, and verify with reminder eval.

**Tech Stack:** Python, agno Agent runtime, pydantic schemas, pytest, reminder eval harness.

**Scope phasing (stop-and-check between phases):**
- Phase 1: Pre-LLM keyword short-circuits in `ReminderIntentCapability.run`.
- Phase 2: Post-LLM `_fallback_decision_from_text` orchestrator and its sub-paths.
- Phase 3: Post-LLM `_normalize_*` decision-patching helpers.
- Phase 4: Raw-text cadence safety nets (`_input_has_high_frequency_without_deadline`, `_looks_like_concrete_cadence`).
- Phase 5: Per-validator review of `_should_reject_*` (delete redundant ones; keep true output safety nets and annotate).

Each phase ends with: unit tests and a commit. The corpus eval (`scripts/run_reminder_eval.py --limit 50`) runs once at the end after Phase 4 per `[[feedback_eval_subset_not_full_corpus]]`. Phases run autonomously end-to-end; no user-approval pauses between phases.

**Non-goals:**
- Do not touch `_COMPLETED_WRITE_CLAIM_PATTERNS` or `_is_reminder_capability_offer_not_write_claim` (runtime output safety net — Phase 5 only adds a rationale comment).
- Do not change the detector prompt unless an eval failure points to a real coverage gap. The plan trusts the prompt as the source of truth.
- Do not change the detector model (locked per `[[project_reminder_detect_model_lock]]`).

---

## File Structure

Files modified:
- `agent/agno_agent/capabilities/reminder_intent.py` — primary file; all deletions land here.
- `agent/agno_agent/schemas/reminder_detect_schema.py` — `_looks_like_concrete_cadence` removal in Phase 4.
- `agent/agno_agent/runtime/agent_runtime.py` — comment-only edit in Phase 5 for `_COMPLETED_WRITE_CLAIM_PATTERNS`.
- `tests/unit/agent/test_reminder_intent_capability.py` — adapt tests that exercised the regex shadow path.
- `tests/unit/agent/agno_agent/capabilities/test_reminder_intent_port.py` — same as above if affected.

Files created:
- `docs/issues/2026-05-27-reminder-intent-llm-only.md` — issue tracker with evidence trail.

No new files in `agent/`; the goal is deletion, not abstraction.

---

## Phase 1 — Delete pre-LLM keyword short-circuits

### Task 1.1: Delete `_explicit_reminder_list_decision` shortcut

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:132-140` (caller), `:268-269` (`_is_explicit_reminder_list_query`), `:272-326` (definition), `:329-390` (`_explicit_list_local_date` if only this caller).

- [ ] **Step 1: Confirm `_explicit_list_local_date` has only one caller**

Run: `rg -n '_explicit_list_local_date' agent/`
Expected: only `:314` (call site inside `_explicit_reminder_list_decision`) and `:329` (definition).

- [ ] **Step 2: Confirm `_is_explicit_reminder_list_query` has no production callers**

Run: `rg -n '_is_explicit_reminder_list_query' agent/ tests/`
Expected: only the definition at `:268`. If any caller exists, stop and re-scope.

- [ ] **Step 3: Delete the call site at `run()`**

Edit `agent/agno_agent/capabilities/reminder_intent.py`. Remove lines 132-140:
```python
        explicit_list_decision = _explicit_reminder_list_decision(
            input_message,
            run_context,
        )
        if explicit_list_decision is not None:
            return self.command_executor.execute(
                explicit_list_decision,
                run_context,
            )
```

- [ ] **Step 4: Delete `_is_explicit_reminder_list_query` and `_explicit_reminder_list_decision`**

Remove the function bodies at `:268-269` and `:272-326`.

- [ ] **Step 5: Delete `_explicit_list_local_date`**

Remove the function body at `:329-390` (assumes Step 1 confirmed it has no other callers).

- [ ] **Step 6: Run targeted unit tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -v -k "list or query"`
Expected: tests that pass through the detector mock continue to pass; any test that asserted the regex shortcut path fires must be re-pointed to detector mock (record as follow-up in Task 6.x).

### Task 1.2: Delete `_is_unsupported_booking_request` shortcut

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:130-131` (caller), `:399-405` (definition).

- [ ] **Step 1: Confirm no other callers**

Run: `rg -n '_is_unsupported_booking_request\|_UNSUPPORTED_BOOKING_REQUEST_PATTERN' agent/`
Expected: caller line, definition, and the regex constant. No other call sites.

- [ ] **Step 2: Delete caller**

Edit `agent/agno_agent/capabilities/reminder_intent.py`. Remove lines 130-131:
```python
        if _is_unsupported_booking_request(input_message):
            return _no_action_discussion_result()
```

- [ ] **Step 3: Delete function and its regex constant**

Remove `_is_unsupported_booking_request` at `:399-405` and the `_UNSUPPORTED_BOOKING_REQUEST_PATTERN` constant (locate via `rg`).

- [ ] **Step 4: Verify no stale imports / unused regex constant remain**

Run: `.venv/bin/python -c "from agent.agno_agent.capabilities import reminder_intent"` — must not raise.

### Task 1.3: Delete `_is_recurring_occurrence_skip_text` shortcut

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:141-147` (caller), `:393-396` (definition).

- [ ] **Step 1: Delete caller (lines 141-147)**

```python
        if _is_recurring_occurrence_skip_text(_latest_user_turn_text(input_message)):
            return _needs_clarification_result(
                summary="请确认这周的哪一个提醒不用了。",
                missing_fields=("哪一个提醒",),
                safety_boundary="ambiguous_request",
                required_questions=("哪一个提醒",),
            )
```

- [ ] **Step 2: Delete definition at `:393-396`**

- [ ] **Step 3: Verify no remaining callers**

Run: `rg -n '_is_recurring_occurrence_skip_text' agent/ tests/`
Expected: empty.

### Task 1.4: Delete pre-LLM `_snooze_update_decision` call

The capability calls `_snooze_update_decision` twice: once **before** the detector (line 148) and once **after** the detector (line 186). Phase 1 only removes the pre-LLM call; the post-LLM call is handled in Phase 2.

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:148-154`.

- [ ] **Step 1: Delete the pre-LLM call (lines 148-154)**

```python
        snooze_update = _snooze_update_decision(
            input_message,
            SimpleNamespace(intent_type="clarify", action=""),
            run_context,
        )
        if snooze_update is not None:
            return self.command_executor.execute(snooze_update, run_context)
```

- [ ] **Step 2: Verify the post-LLM caller at line 186 still references the function**

Run: `rg -n '_snooze_update_decision' agent/`
Expected: function definition + post-LLM caller. (Definition removed later in Phase 2.)

### Task 1.5: Clean up dead helper, run unit tests, and commit Phase 1

- [ ] **Step 1: Verify `_explicit_list_title_query` is now dead**

Run: `rg -n '_explicit_list_title_query' agent/ tests/`
Expected: only its definition in `reminder_intent.py`. It was previously only called from the now-deleted `_explicit_reminder_list_decision`. If any surviving caller appears, stop and re-scope.

- [ ] **Step 2: Delete `_explicit_list_title_query`**

Remove the function body in `agent/agno_agent/capabilities/reminder_intent.py` (locate via `rg`).

- [ ] **Step 3: Run focused unit tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/agno_agent/capabilities/test_reminder_intent_port.py -v`
Expected: all pass (113+). If failures appear, classify as (a) test asserted regex shortcut path (re-point to detector mock per Phase 6 Task 6.1 pattern) or (b) detector mock used in test no longer matches the new path (fix mock to match the LLM-only flow). Do not weaken / xfail.

Rationale for not running the corpus eval here: Phase 1 only deletes pre-LLM short-circuits; detector behavior is unchanged, only the runtime stops bypassing it. The 113-passing unit suite covers the runtime wiring. The full corpus eval (`.venv/bin/python scripts/run_reminder_eval.py --limit 50`) is deferred to a single end-of-plan run after Phase 4, per user-confirmed gating.

- [ ] **Step 4: Commit Phase 1 (code + tests only)**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "refactor(reminder-intent): remove pre-LLM keyword short-circuits

Delete _explicit_reminder_list_decision, _is_unsupported_booking_request,
_is_recurring_occurrence_skip_text, _explicit_list_title_query, and the
pre-LLM _snooze_update_decision call. Detector LLM already covers
list/discussion/snooze intents (see INSTRUCTIONS_REMINDER_DETECT)."
```

- [ ] **Step 5: Separately commit the doc edit to `docs/issues/2026-05-25-product-notification-outbound.md`**

This doc edit was made during Phase 1 because the existing wording (referring to a "短 确认/同意/接受/通过/拒绝 reply word list") had been superseded by the Focus + semantic-interpreter flow. The content is correct; keep it but commit it as a doc-only follow-up to honor scope discipline.

```bash
git add docs/issues/2026-05-25-product-notification-outbound.md
git commit -m "docs(issue): refresh product-notification action description to Focus + semantic interpreter

The outbound-flow issue file still described the legacy short
confirmation/rejection keyword list. Update to match the current Focus
binding + semantic interpreter path that recent commits introduced."
```

---

## Phase 2 — Delete `_fallback_decision_from_text` orchestrator

### Task 2.1: Delete `_fallback_decision_from_text` caller

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:175-179`.

- [ ] **Step 1: Delete the call block**

```python
        fallback_decision = _fallback_decision_from_text(
            input_message, decision, run_context
        )
        if fallback_decision is not None:
            decision = fallback_decision
```

When the detector returns `_is_unrecognized_decision(...)`, the existing check at line 182 routes to `_invalid_decision_clarification_result()`. No new branch needed.

### Task 2.2: Delete the post-LLM `_snooze_update_decision` call

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:186-188`.

- [ ] **Step 1: Delete the call**

```python
        snooze_update = _snooze_update_decision(input_message, decision, run_context)
        if snooze_update is not None:
            decision = snooze_update
```

Rationale: the detector instruction explicitly handles "再过 N 分钟提醒我" as `action=update, target_scope=recent_active, new_trigger_at=current_time+offset`.

### Task 2.3: Delete the fallback functions and their helpers

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py` — remove these definitions (line numbers from current HEAD):
  - `_fallback_decision_from_text` (`:882-941`)
  - `_snooze_update_decision` (`:838-879`)
  - `_fallback_update_decision_from_text` (`:1095-1146`)
  - `_fallback_recurring_create_decision_from_text` (`:1147-1228`)
  - `_should_repair_update_decision` (`:943-953`)
  - `_should_repair_create_decision` (`:954-977`)
  - `_extract_target_title_from_write_text` (`:1299-1314`)
  - `_extract_create_title_after_reminder_verb` (`:1241-1249`)
  - `_extract_create_title_after_reminder_verb_verbatim` (`:1250-1258`)
  - `_extract_new_title_from_update_text` (`:1331-1340`)
  - `_extract_new_trigger_at_from_update_text` (`:1341-1349`)
  - `_extract_single_local_time_selector` (`:1351-1390`)
  - `_is_workday_text` (`:1231-1236`)
  - `_is_explicit_workday_create_text` (`:1237-1239`)
  - `_is_bare_snooze_reference` (`:1391-1404`)
  - `_single_relative_delay` (`:1405-1493`)
  - `_relative_delay_trigger_at` (`:1494-1507`)
  - `_next_future_trigger_at_for_single_bare_clock` (`:1727-…`) **only if** no `_normalize_*` survivor (Phase 3) still references it. Skip in Phase 2 if still in use; revisit in Phase 3.

- [ ] **Step 1: Use `rg` to scan each helper for surviving references before deleting**

For each helper above, run:
```bash
rg -n '<helper_name>' agent/ tests/
```
Expected: only the definition + already-being-deleted callers. If any survivor remains (e.g. a `_normalize_*` that Phase 3 will delete), defer that helper's removal to Phase 3 and leave a `# kept for Phase 3 cleanup` note.

- [ ] **Step 2: Delete in dependency order (callers first, leaves last)**

Order: `_fallback_decision_from_text` → `_snooze_update_decision` → `_fallback_update_decision_from_text` → `_fallback_recurring_create_decision_from_text` → `_should_repair_*` → `_extract_*` → `_is_workday_text` / `_is_explicit_workday_create_text` / `_is_bare_snooze_reference` → `_single_relative_delay` / `_relative_delay_trigger_at`.

- [ ] **Step 3: Run `python -c "import agent.agno_agent.capabilities.reminder_intent"`**

Expected: no NameError. Resolve any "imported but unused" / leftover regex constants by deleting them.

- [ ] **Step 4: Drop the regex constant pool used only by these fallbacks**

Search for module-level `_*_PATTERN`, `_*_RE`, `_*_TOKENS` constants no longer referenced. Delete each after confirming `rg -n '<NAME>' agent/` shows zero remaining usages.

### Task 2.4: Run unit tests, commit Phase 2, pause

- [ ] **Step 1: Run reminder unit tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/agno_agent/capabilities/test_reminder_intent_port.py -v`
Expected: all pass. Failures classified per Task 6 rule (test bug vs. detector coverage gap). Do not weaken / xfail.

Rationale: same as Task 1.5 Step 3 — the corpus eval is deferred to a single end-of-plan run after Phase 4. Phase 2 deletes post-LLM regex fallbacks; the detector LLM remains the source of truth, and unit-level wiring is covered by the test suite.

- [ ] **Step 2: Commit Phase 2**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "refactor(reminder-intent): remove _fallback_decision_from_text shadow layer

Detector LLM produces snooze/update/recurring-create decisions directly;
delete the regex-based shadow path that reconstructed decisions from raw
user text after the detector returned. Empty detector output now routes
to existing _invalid_decision_clarification_result instead of regex
repair."
```

- [ ] **Step 3: Continue immediately to Phase 3.**

The Phase 3 layer (`_normalize_*`) is deeper and has more potential blast radius, so commit Phase 2 first and proceed in isolated per-helper commits to keep blast radius bisectable.

---

## Phase 3 — Delete `_normalize_*` decision-patching helpers

Each `_normalize_*` patches one slot of the detector's decision based on raw user text. Per option A, all are removed; if the detector emits a wrong slot, the runtime should rely on `_should_reject_*` validators (Phase 5) or fall through to clarification.

### Task 3.1: Inventory and dependency map

- [ ] **Step 1: Confirm caller list**

Run: `rg -n '_normalize_\|_drop_' agent/agno_agent/capabilities/reminder_intent.py`
Expected: only the in-`run()` calls at the post-decision pipeline (`:189-258`), no other callers.

- [ ] **Step 2: Print the deletion order**

The in-`run()` order is the deletion order. Each step deletes one call + one helper, runs unit tests, and commits separately so any regression is bisectable.

### Task 3.2 .. 3.14: One helper per task

For each of the following helpers (in this order), run Step 1 → Step 4 below as one task:

1. `_normalize_write_target_selectors_from_text` (`:189-191`, `:978-…`)
2. `_normalize_relative_delay_create_trigger` (`:210-214`, `:799-…`)
3. `_normalize_past_bare_create_trigger` (`:215-219`, `:1508-…`)
4. `_normalize_relative_day_create_trigger` (`:220-224`, `:1636-…`)
5. `_normalize_update_trigger_from_text` (`:225-229`, `:1679-…`)
6. `_normalize_weekday_bare_create_trigger` (`:230-234`, `:1578-…`)
7. `_normalize_time_evidence_decision` (`:235-242`, `:567-…`)
8. `_normalize_create_title_from_user_text` (`:243`, `:1259-…`)
9. `_drop_ungoverned_batch_plan_operations` (`:244`, `:2160-…`)
10. `_drop_batch_operations_without_local_schedule_evidence` (`:245-247`, `:2196-…`)
11. `_normalize_create_duration_from_title` (`:258`, `:2033-…`)
12. `_normalize_explicit_list_title_query` (`:378-…`) — delete if Phase 1 left no caller.
13. `_drop_ungoverned_cadence_task_operations` (`:2224-…`) — delete if no caller remains.

For each item N (3.N):

- [ ] **Step 1: Verify no external callers**

Run: `rg -n '<name>' agent/ tests/`. Helper must only appear at its definition and its in-`run()` call site.

- [ ] **Step 2: Delete the call in `run()` and the function body**

- [ ] **Step 3: Run unit tests + the matching reminder eval slice**

Eval keyword for each helper:
- selector / title helpers → `-k "target or title or update"`
- trigger / time helpers → `-k "trigger or time or weekday"`
- batch helpers → `-k "batch"`
- duration helper → `-k "duration"`

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(reminder-intent): trust detector for <slot>; delete <helper>"
```

### Task 3.15: Final Phase 3 verification

- [ ] **Step 1: Run full reminder unit test file**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -v`

- [ ] **Step 2: Run reminder eval subset (30-50 cases)**

Run: `.venv/bin/python -m pytest tests/evals/test_reminder_eval_runner.py -v --maxfail=5`

- [ ] **Step 3: Continue immediately to Phase 4**

---

## Phase 4 — Raw-text cadence safety nets

### Task 4.1: Delete `_input_has_high_frequency_without_deadline`

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:2643-2644`, `:2783-2800`.

The structured branch of `_is_unbounded_high_frequency_cadence` (rrule-based, lines 2645-2659) is sufficient — the LLM's `rrule` + `deadline_at` carry the same signal.

- [ ] **Step 1: Delete the raw-text branch caller (lines 2643-2644)**

```python
    if _input_has_high_frequency_without_deadline(input_message):
        return True
```

- [ ] **Step 2: Remove the `input_message` parameter from `_is_unbounded_high_frequency_cadence` and its caller (line 204-207)**

Drop the `input_message=input_message` kwarg from the call site at `:204-206` and the parameter from the signature at `:2638-2642`.

- [ ] **Step 3: Delete `_input_has_high_frequency_without_deadline` (`:2783-2800`)**

- [ ] **Step 4: Delete `_is_high_frequency_evidence` if no caller remains**

Run: `rg -n '_is_high_frequency_evidence' agent/`. If only its definition and the now-deleted caller remain, delete it.

- [ ] **Step 5: Run cadence unit tests + eval slice**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -v -k "high_frequency or cadence or hourly"`

- [ ] **Step 6: Commit**

### Task 4.2: Delete `_looks_like_concrete_cadence`

**Files:**
- Modify: `agent/agno_agent/schemas/reminder_detect_schema.py:432`, `:503-558`.

- [ ] **Step 1: Read context around line 432 to understand the validator that uses it**

Read `agent/agno_agent/schemas/reminder_detect_schema.py:420-445`.

- [ ] **Step 2: Decide replacement**

If the validator's purpose is "reject decisions where `schedule_evidence` doesn't look like a real cadence string": this is regex re-validation of LLM output. Delete both the validator branch and the helper, trusting the detector's structured `rrule` and `schedule_basis` fields.

- [ ] **Step 3: Delete the validator branch at `:432` (the `and not _looks_like_concrete_cadence(...)` clause) so it becomes a pure structural check**

- [ ] **Step 4: Delete `_looks_like_concrete_cadence` (`:503-558`)**

- [ ] **Step 5: Run schema and eval tests**

Run: `.venv/bin/python -m pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py -v -k "cadence or schedule_evidence"`

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(reminder-detect): trust detector schedule fields; remove _looks_like_concrete_cadence

Schema no longer re-validates schedule_evidence with a keyword/regex
pass. Detector's structured rrule and schedule_basis carry the cadence
shape signal."
```

---

## Phase 5 — Output guardrails: keep, annotate, prune dead validators

### Task 5.1: Annotate `_COMPLETED_WRITE_CLAIM_PATTERNS` as a safety net

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py:180-187`.

- [ ] **Step 1: Add a one-line comment above the constant block at `:180`**

```python
# OUTPUT SAFETY NET (not a semantic classifier): catches LLM final-text
# claims of a completed reminder write when no tool write actually
# succeeded. Survives the LLM-only intent migration because its purpose
# is to compensate for LLM unreliability, not to classify user intent.
_COMPLETED_WRITE_CLAIM_PATTERNS = (
    ...
)
```

- [ ] **Step 2: Commit (comment-only)**

### Task 5.2: Audit `_should_reject_*` validators in `reminder_intent.py`

Each validator must be classified:
- **Safety net on LLM output** (e.g. `_should_reject_quoted_title_loss`, `_should_reject_weekday_mismatch`): keep, add comment.
- **Redundant with detector schema / pure regex re-derivation**: delete.

Validators in scope:
- `_should_reject_quoted_title_loss`
- `_should_reject_weekday_mismatch`
- `_should_reject_ungoverned_single_create_title`
- `_should_reject_day_of_month_mismatch`
- `_should_reject_missing_scheduled_clauses`
- `_should_reject_title_schedule_evidence_leak`

- [ ] **Step 1: For each validator, read body and classify**

- [ ] **Step 2: Delete redundant ones; annotate kept ones with one-line "OUTPUT SAFETY NET" comment**

- [ ] **Step 3: Run unit + eval subset**

- [ ] **Step 4: Commit**

---

## Phase 6 — Test adaptation and finalization

### Task 6.1: Re-point regex-asserting tests to detector-mock path

Tests in `tests/unit/agent/test_reminder_intent_capability.py` that pre-supposed the regex fallback path (e.g. tests that asserted "改成下午4点" produces an update decision without mocking the detector) need to mock the detector to return the same decision the LLM would produce in production.

- [ ] **Step 1: Identify tests by running unit suite after Phase 2 and 3**

- [ ] **Step 2: For each failing test, replace the regex-fallback assertion with a detector mock that returns the equivalent structured decision**

Pattern:
```python
detector_agent = MagicMock()
detector_agent.arun = AsyncMock(return_value=_make_response(
    ReminderDetectDecision(
        intent_type="crud",
        action="update",
        target_title="喝水",
        new_trigger_at="2026-05-27T16:00:00+08:00",
        ...
    )
))
ReminderIntentCapability(detector_agent=detector_agent, ...).run(...)
```

- [ ] **Step 3: Delete any test whose only purpose was "verify regex fallback fires"**

These tests become meaningless once the regex layer is gone — their behavior is now equivalent to the test in Step 2.

### Task 6.2: Final repo-OS check and eval evidence capture

- [ ] **Step 1: Run repo-OS structure check**

Run: `zsh scripts/check`
Expected: clean.

- [ ] **Step 2: Run `scripts/suggest-verification`**

Run: `zsh scripts/suggest-verification --base HEAD~1`
Expected: command list including reminder eval + unit subset.

- [ ] **Step 3: Run the suggested commands; capture output to `artifacts/evidence/2026-05-27-reminder-intent-llm-only/`**

- [ ] **Step 4: Update `docs/issues/2026-05-27-reminder-intent-llm-only.md` with the final commit list and evidence path**

- [ ] **Step 5: Mark the issue as resolved with status: closed and reference the final commit**

---

## Risk Register

- **Detector coverage gap**: a deletion exposes an intent the detector LLM does not currently handle. Mitigation: each phase ends with an eval subset, classified per `[[feedback_eval_not_sacred]]`. If the eval surfaces a gap, do not patch the regex back; fix the detector prompt in a separate plan or capture as an issue.
- **Unit-test mocks expecting regex path**: covered by Phase 6 Task 6.1.
- **Detector latency / timeout**: not affected — the detector was already on the hot path; deletions only reduce post-processing.
- **`schedule_evidence` cadence-shape validation**: Phase 4 Task 4.2 trusts the detector's structured `rrule`. If eval surfaces wrong rrules, capture the case in the issue file rather than reinstating the regex check.

## Self-Review

- Spec coverage: every helper in the original audit (Buckets 0/1/3/4) appears in Phases 1-5.
- Placeholder scan: no TBD / "handle edge cases" / "similar to above" — every helper is named explicitly.
- Type consistency: `ReminderDetectDecision`, `_invalid_decision_clarification_result`, `_should_execute_decision` referenced consistently across phases.
- Phase boundaries align with blast radius: each phase commits independently and the plan explicitly pauses for user review at the highest-risk boundary (end of Phase 2).
