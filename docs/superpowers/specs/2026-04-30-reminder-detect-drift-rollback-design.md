# Reminder Detect Drift Rollback — Design

- **Status**: Draft
- **Date**: 2026-04-30
- **Owner**: TBD
- **Related**: `.agents/skills/reminder-crud-case-testing/SKILL.md`

## Background

`.agents/skills/reminder-crud-case-testing/SKILL.md` codifies the working agreement for the reminder corpus loop: LLM-first, no per-case Python NLU, no negative-example prompt accretion, and `_validate_reminder_decision_evidence` should not become a long `if/return` chain. Despite the guardrails, recent corpus work has drifted across all of them:

- `agent/prompt/agent_instructions_prompt.py` `INSTRUCTIONS_REMINDER_DETECT` is ~175 rules with inline negative phrase strings (`"我8点回来"`, `"七点半开始正式学习"`, `"今晚7点上课"`, `"之后吃饭，8点回来"`, etc.) and a manually duplicated `INSTRUCTIONS_REMINDER_DETECT_RETRY`.
- `agent/agno_agent/workflows/prepare_workflow.py` is 1,785 lines. About half is post-LLM tessellated validation: `_validate_reminder_decision_evidence`, `_clock_time_variants` (~30 string permutations of one clock time), `_multi_clause_reminder_count`, `_should_skip_orchestrator_for_explicit_reminder`, and seven `_looks_like_*` / `_ACTIONABLE_*` regex families.
- `tasks/evidence/reminder-normal/` has 562 case files and 97 `*-failed.json` retries; case-449 alone retried 7 times across `-failed`, `-diagnose-failed`, `-evidence-fix-failed`, `-prompt-fix-failed`, `-retry-fix-failed`, `-routing-fix-failed`, `-diagnostic-2-failed`.
- The last 30 commits are mostly "Clarify X without reminder intent" / "Classify Y as Z" — the textbook one-case-at-a-time fix loop the SKILL exists to prevent.

The 97-case expectation set is treated as a **historical regression corpus**, not the product spec; expectation labels can be re-baselined as long as real product behavior does not regress (product decision recorded 2026-04-30: option B in the brainstorming dialogue).

## Goals

- Restore the LLM-first contract: detection lives in `ReminderDetectAgent` + retry, with a thin pydantic schema for structural correctness; no Python NLU.
- Collapse the prompt to a positive decision boundary; move concrete examples into evaluation fixtures (few-shot or eval expectations), not into the prompt string.
- Single source of truth for the detect prompt — retry derives from the same source.
- Eliminate the post-LLM evidence/clock/time-variant validators; rely on schema for structural rules and on eval for behavior.
- Establish a documentable, reversible rollout: each PR has an eval-pass-rate gate.

## Non-goals

- No change to the firing/scheduling pipeline (`agent/runner/reminder_scheduler.py`, `agent/runner/reminder_event_handler.py`, `agent/reminder/service.py`). Reviewed and clean.
- No change to the chat reply pipeline (`agent/agno_agent/workflows/chat_workflow_streaming.py`, `chat_response_agent`).
- No change to `Orchestrator` *schema*. Its prompt may be tightened in PR2 if Orchestrator misroutes a real product class after the regex bypass is removed.
- No new product features. Behavior changes are limited to those that follow from removing engineering false positives/negatives, and they must be flagged in PR descriptions with affected case lists.

## Product invariants preserved

These behaviors must survive the refactor. They become the implicit contract the new prompt and eval corpus enforce.

1. Explicit reminder request with concrete time + content → `crud.create` (or `crud.batch` for multiple safe clauses).
2. Date-only or time-missing reminder request → `clarify`. No midnight default.
3. Bounded cadence with deadline → enumerate one-shot operations and set `deadline_at`. RRULE only for unbounded recurrence.
4. Broad cancel / do-not-disturb → `crud.delete` if target identifiable, otherwise `clarify`. Never `create`.
5. Mixed safe/unsafe clauses in one message → execute the safe ones, clarify the unsafe ones. No all-or-nothing.
6. Habitual schedule statements paired with explicit reminder/supervision intent → recurring reminder. Without that intent → `discussion`.
7. Reminder creation requires explicit user request. The LLM is the sole judge of intent; the prompt expresses this as a single positive boundary ("create only when the user asks to be reminded/notified/alarmed/called/checked-in") and **does not** enumerate the activity-statement counterexamples that previously lived inline. Eval cases that depended on the old enumeration are re-baselined in PR4 (product decision recorded 2026-04-30: aggressive route).
8. ISO 8601 trigger times must be timezone-aware; offset must match user timezone unless the user explicitly named another.
9. `schedule_evidence` is **no longer required to be a substring of the user message**. The substring-equality requirement is dropped (product decision recorded 2026-04-30). Schema continues to require `schedule_evidence` to carry a concrete cadence/time token via the existing `_looks_like_concrete_cadence` check.

## Architecture after rollback

```
User message
    ↓
OrchestratorAgent (1× LLM)            unchanged; routes reminder/search/timezone
    ↓
ReminderDetectAgent (1× LLM)          single source of truth for detection
    ↓ ReminderDetectDecision (pydantic)
Schema validators                     structural enforcement only:
  · intent_type ↔ action consistency  (existing)
  · trigger_at timezone-aware ISO     (existing)
  · cadence requires concrete token   (existing _looks_like_concrete_cadence)
  · operations non-empty for batch    (existing)
  · single create vs batch boundary   (existing)
    ↓
ReminderService                       unchanged
    ↓
visible_reminder_tool                 unchanged
    ↓
Reminder DAO + Scheduler              unchanged
```

### What is removed from `prepare_workflow.py`

- `_validate_reminder_decision_evidence` and helpers: `_clock_time_variants`, `_clock_dayparts`, `_clock_time_is_only_range_boundary`, `_is_embedded_bare_hour_match`, `_is_range_boundary_at`, `_compact_text`, `_message_mentions_midnight`, `_trigger_is_midnight_without_evidence`, `_message_has_multi_clause_reminders`, `_multi_clause_reminder_count`, `_schedule_evidence_supported_by_current_message`, `_operation_action`, `_operation_trigger_at`.
- `_should_skip_orchestrator_for_explicit_reminder` and the regex pattern families it depends on: `_EXPLICIT_REMINDER_INTENT_PATTERNS`, `_REMINDER_STATUS_COMPLAINT_PATTERNS`, `_REMINDER_STOP_INTENT_PATTERNS`, `_REMIND_MARKER_PATTERN`, `_ACTIONABLE_REMINDER_TIME_PATTERN`, `_CALL_ME_MARKER_PATTERN`, `_ACTIONABLE_CALL_ME_TIME_PATTERN`, `_ACTIONABLE_CALL_ME_TASK_PATTERN`, `_ACTIONABLE_CONTACT_TIME_PATTERN`, `_IMPLICIT_REMINDER_INTENT_PATTERNS`. **Kept**: `_REMINDER_FIRST_PATTERNS` and the calendar-import detection path (`_CALENDAR_IMPORT_INTENT_PATTERNS`, `_looks_like_calendar_import_intent`); `_REMINDER_FIRST_PATTERNS` is used by calendar-import detection to avoid misrouting reminder messages to the calendar-import handoff (`prepare_workflow.py` `_looks_like_calendar_import_intent`), not by reminder detection itself.
- `_should_run_reminder_detect` regex-override branch. Orchestrator's `need_reminder_detect` is final; if Orchestrator misses, the fix is the Orchestrator prompt.
- `_append_invalid_schedule_evidence_clarification` (its trigger goes away with the validator).
- The retry path stays, but the per-call branching shrinks because the validator no longer flags decisions as invalid. Retry remains the answer to *LLM* timeouts and *schema* validation errors only.

### What changes in `agent/prompt/agent_instructions_prompt.py`

- `INSTRUCTIONS_REMINDER_DETECT` is rewritten as a positive boundary, target ≤60 lines (≈25–30 rules at 1–2 lines each), covering schema fields, intent boundary, cadence/RRULE rules, batch/operation rules, trigger_at format, and the nine product invariants above. **No** inline negative phrase strings. **No** "Example: ... -> ..." lines in the prompt body.
- `INSTRUCTIONS_REMINDER_DETECT_RETRY` is removed as a separate constant. Retry uses the same `INSTRUCTIONS_REMINDER_DETECT`; differences live in the *input template* (shorter context, optional invalid-decision reason).
- A new `agent/prompt/reminder_few_shot.json` fixture holds the canonical examples that previously lived inline (one example per decision class, drawn from cases the eval corpus already validates). The agent injects them into its input as few-shot, not into the system prompt.

### What changes in `agent/prompt/chat_contextprompt.py`

In scope as part of PR3 (product decision recorded 2026-04-30: include the `CONTEXTPROMPT_提醒未执行` audit in this rollback):

- `CONTEXTPROMPT_提醒未执行` (currently 19 non-empty lines, under the SKILL's 25-line cap, but already showing the same "If X is missing, ask Y" enumeration pattern that drives drift). Rewrite as a positive boundary: state the rule once ("ask one direct question for whatever decision or detail blocks safe reminder creation; do not commit to a reminder until a successful tool result exists"), drop the per-missing-field enumeration. Target ≤15 non-empty lines.
- `CONTEXTPROMPT_提醒无需操作` is already short and positive — left as is.

### What changes in the eval corpus

- `scripts/reminder_normal_path_expectations.json` is pruned to a representative minimal set per decision class (target ≤70 cases, down from 97). Cases that exist purely to verify a removed prompt rule (case-449 and similar) are deleted with rationale recorded in PR4.
- `tests/evals/test_reminder_normal_path_eval.py` per-case assertions shrink correspondingly; aim for the file to drop below 1,000 lines.
- `tests/unit/test_prepare_workflow_reminder_guard.py` loses every test that pinned the removed validator. Remaining tests cover Orchestrator wiring, retry path, schema enforcement, and the RRULE/deadline interaction.

### What does not change (explicit)

- `agent/agno_agent/schemas/reminder_detect_schema.py` keeps its current shape. Its `_validate_executable_datetimes`, `_validate_schedule_basis`, `_validate_deadline_operations` are the new line of defense and they are already structural (timezone, basis, deadline ordering) — no semantic substring checks.
- The reminder firing pipeline (`reminder_scheduler.py`, `reminder_event_handler.py`, `reminder/service.py`, `reminder/schedule.py`).
- The reminder DAO, the conversation lock model, and the `visible_reminder_tool` adapter.

## Sequencing

Every PR runs:
- `pytest tests/unit/ -q`
- `pytest tests/evals/test_reminder_normal_path_eval.py -q`
- `python scripts/eval_reminder_normal_path_cases.py` (full corpus) and reports pass-rate delta plus per-class precision/recall in the PR description.
- A PR is blocked if aggregate pass rate drops by more than 5 percentage points without an explicit re-baseline note tying the regression to a removed prompt rule.
- `scripts/reminder_drift_report.py` is run at PR1 (baseline snapshot) and PR4 (post-rollback snapshot); intermediate PRs may include it but are not required to.

Each PR is independently revertable. The order is "outside-in" (delete the layers furthest from the LLM first):

### PR1 — Drop the post-LLM evidence/clock validators

Removes `_validate_reminder_decision_evidence` and its private helpers from `prepare_workflow.py`. Tests in `test_prepare_workflow_reminder_guard.py` that specifically pin those helpers are deleted; tests that pin product behavior are rewired to schema-level expectations or moved to the eval suite.

`schedule_evidence` substring requirement is dropped. Schema-side `_looks_like_concrete_cadence` continues to enforce that cadence evidence carries a concrete frequency/interval token.

Expected eval delta: small. Cases previously rescued by the validator regress to whatever the LLM decides; if LLM decides correctly they pass, otherwise they surface as work for PR3.

### PR2 — Drop the regex fast-path

Removes `_should_skip_orchestrator_for_explicit_reminder`, the regex override inside `_should_run_reminder_detect`, and all `_looks_like_*` / `_ACTIONABLE_*` patterns (the calendar-import detector keeps its own path). Orchestrator's `need_reminder_detect` is final.

Tests in `test_prepare_workflow_reminder_guard.py` for orchestrator-bypass behavior are deleted; tests for orchestrator-decided routing are kept. If Orchestrator misclassifies a real product class, the fix in this PR is in `INSTRUCTIONS_ORCHESTRATOR`. **No regex bypass may be re-added.**

Expected eval delta: small if Orchestrator is well-tuned; otherwise localized to the Orchestrator prompt.

### PR3 — Rewrite the detect prompt; unify retry

Rewrites `INSTRUCTIONS_REMINDER_DETECT` to a positive boundary (~25–30 rules). Drops `INSTRUCTIONS_REMINDER_DETECT_RETRY` as a separate constant; retry agent reuses the same instructions. The retry input template keeps the "shorter context + invalid-decision reason" affordances; the system prompt stops being two copies.

Adds `agent/prompt/reminder_few_shot.json` (one canonical example per decision class, sourced from existing eval corpus) and wires it into the agent input template (not the system prompt).

Expected eval delta: largest of the four PRs. Re-runs corpus, accepts pass-rate shifts that map onto the documented product invariants. PR description must list every case whose expectation changes and why.

### PR4 — Re-baseline the corpus

Reads the eval corpus and classifies each case as one of:
- **(a) behavior signal** — keep,
- **(b) prompt-quirk test** — delete with rationale,
- **(c) duplicate of a kept case** — delete,
- **(d) needs new expectation under new architecture** — re-annotate.

Target ≤70 cases, distributed across `crud.create`, `crud.batch`, `crud.update`, `crud.delete/cancel/complete`, `crud.list`, `clarify`, `query`, `discussion`. Updates `scripts/reminder_normal_path_expectations.json`, `tests/evals/test_reminder_normal_path_eval.py`, and the matching evidence directory hygiene (archive `*-failed.json` files into `tasks/evidence/reminder-normal/_archive/` to preserve history without polluting the active set).

Adds `scripts/reminder_drift_report.py` (extracted from the inline snippet currently embedded in `SKILL.md`) and runs it; commits the snapshot. The drift report becomes a recommended pre-commit signal in `SKILL.md`.

## Tests

- All unit tests stay green at every PR boundary.
- Normal-path eval (`pytest tests/evals/test_reminder_normal_path_eval.py`) gates every PR.
- E2E (`tests/e2e/test_reminder_system_flow.py`) gates PR1 and PR4 (it covers the fire path, untouched in mechanism by PR2/PR3).
- `python scripts/eval_reminder_normal_path_cases.py` full-corpus run gates PR3 and PR4 specifically; the PR description carries pass-rate delta and per-class precision/recall.

## Risks and mitigations

- **R1: The few-shot fixture grows back into a prompt by another name.** Mitigation: `agent/prompt/reminder_few_shot.json` is capped at a hard line-count budget enforced by a unit test; new examples require deleting an old example.
- **R2: Orchestrator misroutes some reminder messages once PR2 lands and that becomes visible.** Mitigation: fix in `INSTRUCTIONS_ORCHESTRATOR`. Adding a regex bypass back is forbidden; the prompt change can use the freed budget from PR3.
- **R3: Re-baselining the corpus in PR4 hides regressions if pass rate is the only metric.** Mitigation: PR4 reports per-class precision/recall (`crud` vs `clarify` vs `discussion` etc.) so a class-level shift is visible even if aggregate stays flat.
- **R4: Drift returns after the refactor.** Mitigation: the drift report runs in CI on changes to `agent/prompt/agent_instructions_prompt.py`, `agent/agno_agent/workflows/prepare_workflow.py`, `scripts/reminder_normal_path_expectations.json`. The SKILL is updated to require the report attached to any reminder-related PR.

## Open questions

- **OQ1**: ~~`CONTEXTPROMPT_提醒未执行` audit scope.~~ **Resolved 2026-04-30**: in scope for PR3; see "What changes in `chat_contextprompt.py`".
- **OQ2**: Should `agent/runner/reminder_scheduler.py::misfire_grace_time=None` policy be revisited? Out of scope; this rollback does not touch the fire path.
- **OQ3**: PR3 introduces `agent/prompt/reminder_few_shot.json`. Should the few-shot live in code (committed) or be loaded from a fixture path discoverable at runtime? Tentative: committed JSON next to the prompt module; revisit if it grows.

## Success criteria

- `prepare_workflow.py` returns to ≤ ~700 lines (orchestrator + context + url + timezone + reminder dispatcher only; no Python NLU).
- `INSTRUCTIONS_REMINDER_DETECT` is the single detect prompt; ≤ 60 lines of rules; no inline example strings.
- `CONTEXTPROMPT_提醒未执行` ≤ 15 non-empty lines, positive boundary, no per-missing-field enumeration.
- `tests/unit/test_prepare_workflow_reminder_guard.py` ≤ 600 lines, all remaining tests cover preserved behavior.
- `scripts/reminder_normal_path_expectations.json` ≤ 70 cases with class-level coverage table in PR4.
- `tasks/evidence/reminder-normal/` retry artifacts are not the basis of new fixes after PR3 lands; future failures resolve via prompt + fixture only.
- Two drift reports committed: PR1 (baseline) and PR4 (final).
