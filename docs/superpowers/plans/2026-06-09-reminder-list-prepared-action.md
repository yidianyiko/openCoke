# Reminder List Prepared Action Implementation Plan

> **For agentic workers:** Implement task-by-task with TDD. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Route explicit, plain reminder-list/count requests through runtime code that calls the existing reminder list domain port and the existing list render template, skipping the ~9.8s Interaction Agent generation.

**Architecture:** Derive a route from the existing `SemanticDecision` (no new model call). When the route is the plain list action, an `ActionRunner` calls `tool_ports.reminder_tool` list path and renders with the shared list template, then records via the same close path the agent uses. Filtered list requests (keyword/time/status) stay on the full agent.

**Tech Stack:** Python, pytest, existing `coke/turn` runtime, `coke/llm/agno_interaction_agent.py` render helpers, `coke/composition.py` `ReminderToolAdapter`.

Source spec: `docs/superpowers/specs/2026-06-09-agent-flow-time-optimization-design.md`.

---

## Scope And Boundaries (do not violate)

- This is **read-only**. The list path must not stage commands, mutate state, set `completed_at` incorrectly, or change the input window beyond the normal close.
- Only the **plain** list/count case is in scope: "list my reminders", "how many reminders do I have". Any request needing a filter (keyword, time range, status/lifecycle, kind) MUST route to the full agent unchanged.
- No keyword/regex matching on user text. Routing reads structured interpreter fields only.
- The runtime list reply text must be byte-for-byte the same as the existing template output (`_render_reminder_list_reply`). Reuse it; do not rewrite the wording.
- Preserve all existing tests. Do not weaken the output protocol.

## File Structure

- Create `coke/turn/reminder_list_render.py` — move `_render_reminder_list_reply`, `_render_reminder_list_line`, and their helpers (`_looks_chinese`, `_user_text` as needed) here as a shared module. Re-export from `coke/llm/agno_interaction_agent.py` so the agent path keeps working with zero behavior change.
- Create `coke/turn/action_runner.py` — `ActionRunner` with a `run_plain_reminder_list(...)` method.
- Create `coke/turn/routing.py` — pure function `derive_route(decision: SemanticDecision) -> Route` returning an enum/string in `{"prepared_list", "clarification", "no_reply", "full_agent"}`.
- Modify `coke/turn/semantic_interpreter.py` — add `list_is_plain: bool = False` to `SemanticDecision`.
- Modify `coke/llm/semantic_interpreter.py` — emit `list_is_plain` from the model (prompt + schema + parse), and add eval/unit cases.
- Modify `coke/turn/runner.py` — at both the sync (~line 519-556) and async (~line 707) interactive paths, after `semantic_decision` is finalized and `context` is built, call `derive_route`; if `prepared_list`, run `ActionRunner.run_plain_reminder_list` and record via `_record_validated_output`, otherwise fall through to the agent exactly as today.
- Modify `coke/observability/turn_latency.py` — add `"route"` and `"action"` to `SAFE_EXTRA_FIELDS`.

## Task 1: Shared list render module (zero behavior change)

**Files:** Create `coke/turn/reminder_list_render.py`; Modify `coke/llm/agno_interaction_agent.py`; Test `tests/unit/coke/turn/test_reminder_list_render.py`.

- [ ] Step 1: Write a failing test asserting `reminder_list_render.render_reminder_list_reply(facts, user_text, account_id)` produces the same string as the current `_render_reminder_list_reply` for a 2-reminder Chinese facts dict and an English facts dict (copy expected strings from current behavior).
- [ ] Step 2: Run it, expect import/attribute failure.
- [ ] Step 3: Move the body of `_render_reminder_list_reply` / `_render_reminder_list_line` and any private helpers they call (`_looks_chinese`, `_render_reminder_list_time`, etc.) into `coke/turn/reminder_list_render.py` as public functions taking explicit inputs (no `AgentRequest` dependency — pass `user_text: str` and any needed fields directly). In `agno_interaction_agent.py`, replace the old functions with thin wrappers that call the new module so the agent path is unchanged.
- [ ] Step 4: Run the new test and the full `agno_interaction_agent` reminder-list tests; expect PASS and no behavior change.
- [ ] Step 5: Commit.

## Task 2: Route derivation (pure, no model call)

**Files:** Create `coke/turn/routing.py`; Test `tests/unit/coke/turn/test_routing.py`.

- [ ] Step 1: Write failing tests for `derive_route(decision)`:
  - `intent_action="list_reminders"`, `ambiguity="clear"`, `required_clarification="none"`, `list_is_plain=True`, `reply_necessity="reply_needed"` → `"prepared_list"`.
  - same but `list_is_plain=False` → `"full_agent"` (filtered list stays on agent).
  - `required_clarification="ask_trigger_time"` → `"clarification"`.
  - `reply_necessity="intentional_no_reply"` → `"no_reply"`.
  - `intent_action="create_reminder"` → `"full_agent"` (create not in scope yet).
  - assert there is no `confidence` field read and no substring search on any text.
- [ ] Step 2: Run, expect failure.
- [ ] Step 3: Implement `derive_route` reading only `decision` fields, gating `prepared_list` on `intent_action == "list_reminders" and ambiguity == "clear" and required_clarification == "none" and list_is_plain and reply_necessity == "reply_needed"`. `clarification` when `required_clarification != "none"`. `no_reply` when `reply_necessity == "intentional_no_reply"`. Else `full_agent`.
- [ ] Step 4: Run, expect PASS.
- [ ] Step 5: Commit.

## Task 3: `list_is_plain` on the interpreter

**Files:** Modify `coke/turn/semantic_interpreter.py`, `coke/llm/semantic_interpreter.py`; Test `tests/unit/coke/llm/test_semantic_interpreter.py` (extend) and any interpreter eval corpus.

- [ ] Step 1: Add `list_is_plain: bool = False` to the `SemanticDecision` dataclass.
- [ ] Step 2: Write a failing test that the LLM interpreter parser maps a model field `list_is_plain` (true/false) into the decision, defaulting to `False` when absent or when `intent_action != "list_reminders"`.
- [ ] Step 3: Implement parsing in `coke/llm/semantic_interpreter.py` and extend the prompt/schema instructions: define `list_is_plain` as "true only when the user asks to list or count their reminders with no filter (no keyword, no specific date/time window, no status/kind filter); false for any filtered or specific-subset list request." Force `list_is_plain=false` whenever `intent_action != "list_reminders"`.
- [ ] Step 4: Add at least 6 interpreter cases: plain list (zh+en) → true; filtered "what's on Friday" / "my gym reminders" / "show overdue" → false; non-list intents → false. Run interpreter unit/eval; expect PASS.
- [ ] Step 5: Commit.

## Task 4: ActionRunner plain list

**Files:** Create `coke/turn/action_runner.py`; Test `tests/unit/coke/turn/test_action_runner.py`.

- [ ] Step 1: Write a failing test: given a fake `reminder_tool` whose `execute_without_staging({"operation":"list_reminders", "owner_account_id":acct, "display_timezone":tz}, guard)` returns a `ToolExecutionResult` with `render_reminder_list` facts, `ActionRunner.run_plain_reminder_list(account_id, display_timezone, user_text, reminder_tool, guard)` returns a `ValidatedOutput` whose reply segments equal `render_reminder_list_reply(facts, user_text, account_id)` and whose tool_events contain the list event.
- [ ] Step 2: Run, expect failure.
- [ ] Step 3: Implement `ActionRunner.run_plain_reminder_list`: call the reminder tool list path, take `result.facts`, build segments via the shared render module, return a `ValidatedOutput` valid reply (mirror the shape produced for a successful list today — inspect `coke/turn/output_protocol.py:32` and the `_record_validated_output` contract). Carry the tool event so close-time recording and telemetry see `tool_count`.
- [ ] Step 4: Add a test that if the tool result is `ok=False`, the ActionRunner returns a non-claiming result that routes to the full agent fallback (do NOT fabricate a list). Run; expect PASS.
- [ ] Step 5: Commit.

## Task 5: Wire route into the runner (sync + async)

**Files:** Modify `coke/turn/runner.py`, `coke/observability/turn_latency.py`; Test `tests/unit/coke/turn/test_runner_prepared_list.py`.

- [ ] Step 1: Add `"route"` and `"action"` to `SAFE_EXTRA_FIELDS` in `turn_latency.py`.
- [ ] Step 2: Write a failing async test through the runner: a trigger whose interpreter yields `list_reminders/clear/none/list_is_plain=True` produces a replied turn whose reply equals the template render and whose telemetry includes a `route="prepared_list"` span, and that `interaction_agent.ainvoke` is NOT called. Use the existing runner test harness/fixtures.
- [ ] Step 3: In `_run_interactive_turn` (sync ~519-556) and the async path (~707), after `context` is built, compute `route = derive_route(semantic_decision)`. If `route == "prepared_list"`, open a `turn_latency_span("turn.prepared_action", extra={"route": route, "action": "list_reminders"})`, call `ActionRunner.run_plain_reminder_list(...)` using `context.trusted_facts` for `account_id`/timezone, `self.tool_ports.reminder_tool`, and `context.freshness_guard` as guard; then `return self._record_validated_output(turn_id=context.freshness_guard.turn_id, trigger=trigger, validated=validated, current_input_messages=..., tool_events=tool_events, onboarding_guidance_required=...)`. If the ActionRunner returns a non-claiming/failed result, fall through to the existing agent call. For every other route, behavior is unchanged (call the agent exactly as today).
- [ ] Step 4: Run the new test plus the full `tests/unit/coke` suite; expect PASS. Fix any regression in the touched paths only.
- [ ] Step 5: Commit.

## Task 6: Interruption / supersede safety

**Files:** Test `tests/unit/coke/turn/test_runner_prepared_list.py` (extend).

- [ ] Step 1: Write a test that a prepared-list turn superseded by a newer inbound before close does not deliver a normal final answer (reuse the existing supersede/cancellation test patterns in the runner tests). The prepared path must honor the same cancellation handling as the agent path.
- [ ] Step 2: Run; if it fails because the prepared branch bypasses cancellation handling, move the prepared-action call inside the same `try`/cancellation scope as the agent call so `CancelledError` and freshness checks apply identically.
- [ ] Step 3: Run the suite; expect PASS.
- [ ] Step 4: Commit.

## Verification (run before handoff)

- [ ] `.venv/bin/python -m pytest tests/unit/coke -q` — all pass.
- [ ] `zsh scripts/suggest-verification --base origin/main` then run the suggested surface command.
- [ ] `black . && isort .` then confirm `git diff --stat` is clean of formatting churn outside touched files.
- [ ] Record in the final report: which turns now skip `agent.primary`, and a unit-level before/after note (prepared list does 0 interaction-agent calls vs 1 today).

## Self-Review Checklist (do before declaring done)

- No substring/keyword routing anywhere.
- `list_is_plain=False` path is unchanged from today (filtered lists still hit the agent).
- Prepared list never stages or mutates.
- Reply text identical to the existing template.
- Cancellation/supersede behaves identically to the agent path.
