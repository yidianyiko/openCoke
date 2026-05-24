---
kind: design_spec
status: draft
authors:
  - YDYK
created: 2026-05-24
related:
  - docs/superpowers/specs/2026-05-21-agno-full-migration-design.md
  - docs/superpowers/specs/2026-05-22-multi-agent-routing-design.md
  - docs/superpowers/plans/2026-05-12-reminder-detect-prompt-diet-followups.md
---

# reminder_intent LLM semantic boundary

## 1. Problem

`agent/agno_agent/capabilities/reminder_intent.py` (~1965 lines, ~90 helpers)
mixes three kinds of logic:

1. **Schema state machine / time math / cross-field consistency / mechanical
   locality** (~40 helpers) — legitimate code responsibility; keep.
2. **Natural-language semantic classification** (~16 regex / keyword helpers)
   — code is currently *guessing* user intent. This is what the design moves
   out.
3. **Result builders and infrastructure** (the rest) — neutral; keep.

The class-2 helpers encode judgements like "the user is discussing reminder
behaviour", "this is a plain schedule statement, not a reminder request", or
"this title needs clarification" as regex / keyword rules. The pattern is
strictly additive:

- It conflicts with `ReminderDetectAgent`'s `intent_type` output (model is
  locked to GLM-5.1 thinking-off, per the `reminder_detect model lock`
  feedback memory) — the code has to override or refine the model
  classification after the fact.
- Every new edge case adds another regex; maintenance cost only grows.
- It is loosely coupled to the product contract: these regexes are
  compensating for an under-specified prompt rather than enforcing an
  inviolable product rule.

## 2. Goal

Move the natural-language semantic judgements out of code and let
`ReminderDetectAgent` emit them as structured fields. Code keeps schema
validation, the state machine, time arithmetic, cross-field consistency, and
inviolable product constraints.

Non-goals:

- Do not replace the `reminder_detect` model. GLM-5.1 thinking-off stays.
- Do not introduce a second LLM call. The detector remains the single call.
- Do not change the `DomainExecutionResult` public contract — only the
  internal `ReminderDetectDecision` schema changes.
- Do not change the reminder CRUD execution path or downstream tool protocol.

## 3. Design

### 3.1 One LLM call, richer structured output

`ReminderDetectAgent` remains the only LLM call. Its output schema
`ReminderDetectDecision` gains one enum field so the model can tell code
*why* it is asking for clarification, replacing the regex-based reason
inference.

### 3.2 Schema changes (breaking)

**Add:**

```python
clarification_reason: Literal[
    "",                                       # not a clarification
    "date_only_missing_time",                 # date given, no clock
    "ambiguous_time_range",                   # "两三点", "3-4 点"
    "completion_condition_missing_time",      # "after I finish X", no clock
    "status_only_content",                    # title is "没做完" style
    "deadline_without_trigger",               # deadline given, no remind time
    "advance_offset_missing",                 # "remind me earlier" no offset
    "high_frequency_requires_end",            # cadence without end
    "missing_reminder_content",               # time given, no title
    "ambiguous_request",                      # fallback (target unclear etc.)
] = ""
```

Constraint: `clarification_reason` must be non-empty when
`intent_type == "clarify"` and must be empty otherwise (pydantic validator
enforced).

**Field-semantics boundary:** `clarification_reason` only carries the
template-selection signal. Code does a hard-coded
`reason → (missing_fields, safety_boundary, prompt template)` mapping; the
**LLM does not emit `missing_fields` or `safety_boundary`**. Rationale:
those two are product-contract enums and must not be model-decided. The
mapping for any given reason value (e.g. `high_frequency_requires_end`) is
fixed in product terms. The mapping table lives in a module-level dict in
`reminder_intent.py`, as the single source of truth.

**Delete (breaking):**

- `reason: str` — no consumer anywhere in the repo. Dead field.
- `clarification_question: str` — currently read by
  `_clarification_result` and returned as the user-facing prompt. Replaced
  by a code-side `clarification_reason → template` lookup. Canonical
  templates already exist (the `_*_clarification_result()` builders); the
  routing changes from "regex detection" to "read `clarification_reason`".

**Keep (all actually consumed):** `intent_type`, `action`, `title`,
`trigger_at`, `reminder_id`, `keyword`, `new_title`, `new_trigger_at`,
`rrule`, `deadline_at`, `schedule_basis`, `schedule_evidence`, `operations`.

### 3.3 No new topic_class field

The five non-request topic shapes (meta_discussion, feature_work,
plain_schedule, acknowledgement, opt_out) all route to the same exit today,
`_no_action_discussion_result()`. Code does not need to distinguish them.
Therefore **no new `topic_class` field** — the existing
`intent_type='discussion'` absorbs all five, and the prompt teaches the LLM
to classify correctly.

### 3.4 Code-vs-LLM boundary

**LLM owns (enforced by prompt + schema):**

- intent classification: crud / clarify / query / discussion.
- When clarifying, emit a `clarification_reason` enum value.
- Route the five discussion sub-shapes (meta_discussion / feature_work /
  plain_schedule / acknowledgement / opt_out) into
  `intent_type='discussion'`.
- Title text must come from the current user message (no invented text).

**Code keeps (do not touch):**

- **State machine:** `_should_execute_decision` / `_is_unrecognized_decision`
  / `_is_clarification_decision`.
- **Time math:** `_parse_chinese_*` / `_subtract_clock_minutes` /
  `_relative_delay_trigger_at` / `_next_future_trigger_at*` /
  `_should_treat_bare_clock_as_same_afternoon` / `_parse_bare_clock_match`.
- **Trigger normalisation:** `_normalize_relative_delay_create_trigger` /
  `_normalize_past_bare_create_trigger` — corrects numeric drift from the
  model on bare-clock and relative-delay outputs.
- **Cross-field consistency (input vs decision):** all kept. These are not
  "semantic guessing" — they prevent the LLM output from contradicting the
  original user message.
  - `_should_reject_weekday_mismatch` / `_should_reject_day_of_month_mismatch`
  - `_explicit_weekday_index` /
    `_explicit_schedule_day_of_month_before_reminder_verb`
  - `_input_has_high_frequency_without_deadline`: input is high-frequency
    but decision drops the deadline → fail-close. **Covered by tests**
    `test_reminder_intent_port_blocks_input_high_frequency_batch_without_evidence`
    (`tests/unit/agent/test_reminder_intent_capability.py:656`) and
    `test_reminder_intent_port_blocks_model_inferred_deadline_for_high_frequency_batch`
    (line 699).
  - `_input_has_bounded_cadence_deadline` /
    `_is_bounded_cadence_deadline_loss`: input contains a bounded deadline
    but decision drops the deadline → fail-close.
- **RRULE schema:** `_is_unbounded_rrule` / `_is_high_frequency_rrule` /
  `_is_bounded_high_frequency_rrule` / `_has_explicit_deadline` /
  `_has_unbounded_recurring_rrule` / `_is_unbounded_high_frequency_cadence`
  / `_is_high_frequency_evidence`.
- **Title clause-locality (mechanical, keep):** title must appear in the
  input message and its surrounding clause must contain a reminder verb.
  This is not semantic guessing — it is a structural substring + clause
  boundary check against a fixed verb list. **Covered by tests**
  `test_reminder_intent_port_drops_ungoverned_task_inventory_from_cadence_batch`
  (line 1878) — the input contains `起床/跑步/睡觉` but only `打卡` is
  governed by a reminder verb; the others must be dropped. A naive
  substring backstop does not catch this. Helpers kept:
  - `_drop_ungoverned_batch_plan_operations`
  - `_drop_batch_operations_without_local_schedule_evidence`
  - `_drop_ungoverned_cadence_task_operations`
  - `_title_has_local_reminder_verb_context`
  - `_title_has_local_cadence_context`
  - `_title_has_local_schedule_context`
  - `_should_reject_ungoverned_single_create_title`
  - `_should_reject_missing_scheduled_clauses` /
    `_explicit_scheduled_clause_count`
  - `_previous_clause_boundary` / `_next_clause_boundary`
- **Title schema cleanliness:** `_should_reject_title_schedule_evidence_leak`
  (title contains scheduling words like "提前"); `_is_generic_reminder_title`
  (pydantic validator).
- **Failure fallback:** LLM timeout / malformed structure still handled by
  code, but all regex branches collapse into one simplified path (see §3.6).
- **Quoted title loss:** `_should_reject_quoted_title_loss` — kept. It is a
  mechanical substring comparison ("did the quoted segment survive into the
  title?"), not semantic.

**Delete (~16 regex helpers, moved to LLM):**

C.1 — input topic classifiers (5), absorbed by `intent_type='discussion'`:

- `_input_is_reminder_behavior_meta_discussion`
- `_input_is_reminder_feature_work_topic`
- `_input_is_plain_schedule_statement_without_reminder_request`
- `_input_is_standalone_reminder_acknowledgement`
- `_input_is_standalone_reminder_opt_out`

C.2 — clarification triggers (4), absorbed by `clarification_reason`:

- `_should_clarify_date_only_create`
- `_should_clarify_ambiguous_time_range_create`
- `_should_clarify_completion_condition_create`
- `_should_clarify_status_only_content_create`

C.3 — input-side time-semantic detectors (7). These existed only to drive
clarification routing. With `clarification_reason` emitted by the LLM, code
no longer needs to rescan input:

- `_input_has_concrete_time_without_reminder_content`
- `_input_has_event_time_with_vague_advance_request`
- `_input_has_one_shot_deadline_without_trigger`
- `_input_has_date_reference_without_clock`
- `_input_has_today_time_range_points_request` (also used by
  `_input_has_large_*` and `_is_today_time_range_points_incomplete_or_recurring`;
  all three deleted together)
- `_input_has_large_today_time_range_points_request`
- `_is_today_time_range_points_incomplete_or_recurring`

**Not deleted (only called by helpers in the keep list):**

- `_input_has_relative_delay_and_preceding_task_content` — kept; called by
  `_should_reject_ungoverned_single_create_title` (C.4 kept).
- `_input_has_next_whole_hour_reference` — kept; called by
  `_input_has_high_frequency_without_deadline` (keep) and C.4 (keep).
- `_input_has_clocked_task_before_trailing_reminder_verb` — kept; called by
  C.2 (delete) and C.4 (keep).

C.5 — regex branches inside `_fallback_clarification_for_input`: see §3.6.

### 3.5 Prompt changes

`agent/prompt/agent_instructions_prompt.py::get_reminder_detect_instructions`
is constrained by ADR 0004 and the existing test contract:

- `tests/unit/prompt/test_agent_instructions_prompt.py`: ≤60 non-empty
  lines; the literal strings `Example:` and `->` are forbidden, as are the
  listed stale example phrases.
- `tests/unit/prompt/test_prompt_token_budgets.py`:
  `INSTRUCTIONS_REMINDER_DETECT` ≤1000 tokens.

Prompt additions therefore follow these rules:

- Keep text terse; one-line rule statements; no case examples inside the
  system prompt (no `->`, no example strings).
- Put examples in the few-shot data file
  `agent/prompt/reminder_few_shot.json` — the existing
  `format_reminder_few_shots_for_prompt` pipeline injects this into the
  *user* input, not the system prompt.
- Before adding text, run `approximate_tokens()` (same algorithm as the
  test) and keep ≥5% headroom. If headroom is already gone, compress
  existing rules first.

**New system-prompt sections (each ≤8 non-empty lines, no example strings):**

1. **Topic classification:** list the five `intent_type='discussion'`
   sub-shapes (meta / feature / plain schedule / acknowledgement / opt_out)
   as one-line rules.
2. **Clarification reason codes:** list the 10 enum values with a one-line
   trigger description each.
3. Remove the line `clarification_question uses the same language as the
   user message` (the field is being deleted).

**Few-shot data additions** (`reminder_few_shot.json`):

- 4 clarification examples (status_only / completion_condition / date_only
  / ambiguous_time_range — one each).
- 5 discussion examples (one per discussion sub-shape).

No title-governance section is added to the system prompt; clause-locality
is enforced by code, and the prompt only needs one line saying "title text
must come from the user message".

### 3.6 Simplified fallback

`_fallback_clarification_for_input` currently runs seven regex branches
when the LLM errors or returns invalid structure. New behaviour:

- LLM timeout / invalid structure → return
  `_invalid_decision_clarification_result()` or
  `_timeout_clarification_result()` directly. No regex second-guess.
- For more specific clarifications, rely on the LLM retrying or the user
  rephrasing.
- The terminal builders (`_no_action_discussion_result()`, etc.) remain;
  they are called from §3.7 control flow and the timeout path.
- The function `_fallback_clarification_for_input` is deleted entirely (no
  remaining routing branches).

### 3.7 End-to-end control flow (new)

```
ReminderIntentPort.run(input):
  decision = await detector_agent.arun(...)   # single LLM call
  decision = _decision_from_response(decision)

  if _is_unrecognized_decision(decision):
      return invalid_decision_fallback

  if decision.intent_type == "discussion":
      return no_action_discussion_result

  if decision.intent_type == "clarify":
      return clarification_result_for(decision.clarification_reason)

  # crud / query only past this point
  decision = _normalize_relative_delay_create_trigger(...)
  decision = _normalize_past_bare_create_trigger(...)
  decision = _drop_ungoverned_batch_plan_operations(input, decision)
  decision = _drop_batch_operations_without_local_schedule_evidence(input, decision)

  if _should_reject_quoted_title_loss(input, decision):
      return invalid_decision_fallback
  if _should_reject_title_schedule_evidence_leak(decision):
      return invalid_decision_fallback
  if _should_reject_weekday_mismatch(input, decision, run_context):
      return invalid_decision_fallback
  if _should_reject_day_of_month_mismatch(input, decision, run_context):
      return invalid_decision_fallback
  if _should_reject_ungoverned_single_create_title(input, decision):
      return invalid_decision_fallback
  if _should_reject_missing_scheduled_clauses(input, decision):
      return invalid_decision_fallback
  if _is_unbounded_high_frequency_cadence(decision, input_message=input):
      return high_frequency_requires_end_clarification
  if _is_bounded_cadence_deadline_loss(input, decision):
      return bounded_cadence_deadline_loss_clarification

  return command_executor.execute(decision, run_context)
```

`ReminderIntentPort.run` shrinks from ~80 lines (15+ if branches, including
~7 that overrode LLM intent via regex) to ~40 lines (all cross-field and
mechanical guards retained, all semantic-guessing branches removed).

## 4. Testing and validation

### 4.1 Unit tests

- Modify `tests/unit/test_reminder_detect_structured_output.py`: drop
  assertions on `reason` and `clarification_question`; add assertions on
  `clarification_reason` enum values; delete
  `test_reminder_detect_clarification_question_schema_keeps_current_language`.
- Modify `tests/unit/agent/test_reminder_intent_capability.py`: switch
  clarification paths to the `clarification_reason`-driven flow; delete
  tests that cover only deleted C.1 / C.2 / C.3 helpers; **keep** all
  tests for C.4 title locality, cross-field consistency, and
  high-frequency / deadline fail-close (lines 656, 699, 1878, …).
- Delete unit tests that exclusively cover deleted helpers.
- Keep state-machine, time-normalisation, and cross-field consistency tests
  intact.

### 4.2 Eval

- Corpus: existing 30-case reminder-intent subset (per the
  `feedback_eval_subset_not_full_corpus` memory) plus 10–20 new cases
  covering:
  - 4 new `clarification_reason` positives (status_only,
    completion_condition, date_only, ambiguous_time_range).
  - 5 `intent_type='discussion'` sub-shape positives (one per sub-shape).
  - 3 title-governance edges (unrelated context must not become title).
- Gate: 0 regressions on the 30-case subset; all new cases pass.
- Eval is not a contract (per `feedback_eval_not_sacred`): if the eval
  distribution itself starts warping the product, change the corpus or
  drop the gate — do not restore regex to satisfy a bad eval.

### 4.3 Rollout

Per-helper hard cutover. Each step runs the following gate before the next
step starts:

- Relevant unit tests
- `tests/unit/prompt/test_agent_instructions_prompt.py`
- `tests/unit/prompt/test_prompt_token_budgets.py`
- Reminder-intent 30-case eval subset
- The ≥10 new cases added in §4.2

Steps:

1. **Add schema field.** Add `clarification_reason`; pydantic validator
   enforces `intent_type='clarify' ⇔ reason non-empty`. Do not delete
   `reason` or `clarification_question` yet; do not delete any helper.
   Verify the model emits the new field under the schema.
2. **Prompt diet + few-shot.** Run `approximate_tokens()` first; add the
   Topic classification and Clarification reason codes sections; add 4
   clarification + 5 discussion few-shot examples.
3. **Route on `clarification_reason`.** Delete C.2 (4 clarification
   triggers) and the C.3 input-only detectors that supported them:
   `_input_has_concrete_time_without_reminder_content`,
   `_input_has_event_time_with_vague_advance_request`,
   `_input_has_one_shot_deadline_without_trigger`,
   `_input_has_date_reference_without_clock`,
   `_input_has_today_time_range_points_request`,
   `_input_has_large_today_time_range_points_request`,
   `_is_today_time_range_points_incomplete_or_recurring`.
4. **Delete C.1** (5 input topic classifiers). `intent_type='discussion'`
   now routes these directly.
5. **Simplify fallback.** Delete `_fallback_clarification_for_input`;
   timeout / invalid paths go straight to
   `_timeout_clarification_result` / `_invalid_decision_clarification_result`.
6. **Delete schema fields (breaking).** Drop `reason` and
   `clarification_question`; rewrite `_clarification_result` to read
   `clarification_reason` and look up the template; update all affected
   unit tests.

Any step that fails its gate is reverted, and the next step does not run.

**Not in this rollout:** C.4 (title clause-locality), cross-field
consistency (weekday / day-of-month / high-freq input vs decision), RRULE
schema validation, quoted-title-loss, time normalisation. These are in the
keep list.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **C.1 deletion: LLM misclassifies opt-out / acknowledgement.** Today the regex backstops catch cases like `All good, no reminders pls` (`tests/.../test_reminder_intent_capability.py:2105`) and `谢谢闹钟` (line 2156) where the model may emit `intent=crud, action=cancel/complete`. Removing the backstop means false positives go through and actually execute writes. | **Deliberate risk acceptance.** Prompt + few-shot teach the LLM to route these into `intent_type='discussion'`. Eval must cover both cases. After release, monitor `reminder.{create,cancel,complete}.count` for 7 days; any anomalous spike → revert and add a minimal backstop covering just these two cases (do not restore all of C.1). |
| GLM-5.1 accuracy drops under the new prompt sections. | Model lock holds (per `project_reminder_detect_model_lock`); tune the prompt first; if the prompt cannot recover, re-evaluate the model rather than expanding the regex. If token budget overflows, compress existing rules — do not raise the cap. |
| Prompt additions trip `test_agent_instructions_prompt` or `test_prompt_token_budgets`. | Run `approximate_tokens()` before each addition; put examples in few-shot data, not the system prompt; keep ≥5% headroom. |
| Deleting `clarification_question` loses multilingual flexibility. | Current Coke user base is primarily Chinese and all clarification templates are already Chinese-only. If multilingual support becomes a requirement later, add i18n centrally — do not keep a dead field for a historical capability. |
| Breaking schema change ripples to downstream consumers. | Full-repo grep confirmed `reason` has no consumer; `clarification_question` is only read inside `reminder_intent.py` and test files. |
| Eval subset misses real long-tail. | The 10+ new cases provide targeted coverage; after release, run another representative subset regression after a 7-day observation window. |

## 6. Out of scope

- No changes to `command_executor` / tool protocol / reminder data model.
- No changes to multi-agent routing or `scheduling_domain` (see
  `2026-05-22-multi-agent-routing-design.md`).
- Few-shot injection pipeline is unchanged (see
  `2026-05-12-reminder-detect-prompt-diet-followups.md`); this design only
  adds 9 new few-shot entries (4 clarification + 5 discussion) without
  touching existing entries. If the new entries make existing entries
  redundant, evaluate compression in the implementation plan separately.
- No changes to the `DomainExecutionResult` or `ReplyContract` contracts.
