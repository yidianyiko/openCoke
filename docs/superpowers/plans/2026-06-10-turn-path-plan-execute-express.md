# Turn Path Plan → Execute → Express Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maintain the inbound interactive turn path as a single uniform
`Plan → PlanCompile → Execute → Express` pipeline.

**Current implementation status (2026-06-11):** The inbound pipeline is the only
interactive path. The classifier-only planning pass, parallel action bypass, ad
hoc streaming eligibility, and recoverable-command implementation are removed.
Render-mode Interaction Agent remains for
notification, access-denied, reminder-fire, and other structured render turns.
Manual V6 smoke was completed outside this repo by the user; no further V6
completion work is required for this cleanup.

**Architecture:** Plan proposes a flat `TurnPlan` of keyword-param actions →
PlanCompile (deterministic enum/required-param
validation) → Execute (per-domain `ActionHandler`s that resolve via domain
services and return `ActionOutcome{category, mandatory status, data}`; resolve_and_stage;
`ExecutionOutcomeBuilder`; `CloseCoordinator` selective atomic materialize;
`PendingClarification` for unresolved actions) → Express (the Interaction Agent
narrowed to render `settled_outcome` / converse, streamed; no tools; no
downstream verifier). Source spec:
`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md`.

**Tech Stack:** Python 3.12, pytest, Agno 2.5.9, existing `coke/turn`,
`coke/domains/*`, `coke/llm` modules, ZAILLMConfig (GLM thinking-off).

---

## Phasing And Cutover Strategy

The rebuild lives in `coke/turn/inbound/` and is now the active inbound
interactive path. Inbound turns enter the pipeline unconditionally after the
standard access, lock, freshness, and focus gates.
Render/notification turns always use the retained render-mode path.

Phases (each produces working, testable software; phases 2–6 are expanded to
full task detail when their predecessor lands):

- **Phase 1 (detailed below):** Data contracts + Plan + PlanCompile.
- **Phase 2:** Execute core + reminder `ActionHandler` + `ActionOutcome` typed
  outcomes (category + mandatory status) + resolve_and_stage.
- **Phase 3:** Express (narrowed render/converse agent) + streaming rule
  (non-mutating stream, mutating buffer-until-commit).
- **Phase 4:** `CloseCoordinator` (selective atomic materialize, disposition,
  close-advance) + `PendingClarification` record + runner wiring.
- **Phase 5:** Remaining `ActionHandler`s (social_scheduling, friendship,
  settings, calendar_import) with their typed statuses; multi-action aggregation.
- **Phase 6:** Parity evals + real-account smoke + cutover + deletion of the
  retired inbound bypasses / output-protocol claim layer / recoverable-command
  subsystem. Manual smoke is complete; cleanup removes the remaining migration
  scaffolding.

## File Structure (new, additive)

- `coke/turn/inbound/contracts.py` — `TurnPlan`, `ProposedAction`, `CompiledAction`,
  `ActionOutcome`, `SettledOutcome`, `PendingClarification`, `MaterializationPlan`
  (frozen dataclasses + the `category`/`status` literals).
- `coke/turn/inbound/plan.py` — `Planner` protocol + `SiliconFlowPlanner` (LLM,
  replaces the classify-only interpreter; emits `TurnPlan`).
- `coke/turn/inbound/plan_compile.py` — `compile_plan(plan) -> CompiledPlan` pure
  deterministic validation.
- `coke/turn/inbound/execute.py` (Phase 2) — `ActionExecutor`, `ActionHandler`
  protocol, `ExecutionOutcomeBuilder`.
- `coke/turn/inbound/handlers/reminder.py` (Phase 2), `.../social.py`, `.../friend.py`,
  `.../settings.py`, `.../calendar.py` (Phase 5).
- `coke/turn/inbound/express.py` (Phase 3) — narrowed render/converse agent.
- `coke/turn/inbound/close.py` (Phase 4) — `CloseCoordinator`, `PendingClarification`
  repository use.
- `coke/turn/inbound/pipeline.py` (Phase 4) — wires Plan→Compile→Execute→Express→Close
  as the unconditional inbound path.
- Tests mirror under `tests/unit/coke/turn/inbound/`.

---

## Phase 1: Data Contracts + Plan + PlanCompile

### Task 1: Data contracts

**Files:** Create `coke/turn/inbound/contracts.py`; Test `tests/unit/coke/turn/inbound/test_contracts.py`.

- [ ] Step 1: Write a failing test constructing each frozen dataclass and asserting
  field defaults and immutability:

```python
from coke.turn.inbound.contracts import (
    TurnPlan, ProposedAction, ActionOutcome, SettledOutcome, PendingClarification,
)

def test_proposed_action_holds_keyword_params():
    a = ProposedAction(domain="reminder", operation="delete", params={"match": "gym"})
    assert a.params["match"] == "gym"

def test_action_outcome_requires_category_and_status():
    o = ActionOutcome(category="done", status="created", data={"id": "r1"})
    assert o.category == "done" and o.status == "created"

def test_turn_plan_defaults_reply_needed():
    p = TurnPlan(actions=(), reply_necessity="reply_needed")
    assert p.actions == ()
```

- [ ] Step 2: Run `tests/unit/coke/turn/inbound/test_contracts.py` — expect import failure.
- [ ] Step 3: Implement the frozen dataclasses with `Literal` types:
  `Category = Literal["done","needs_choice","needs_input","needs_confirmation","not_possible","nothing"]`;
  `ReplyNecessity = Literal["reply_needed","intentional_no_reply"]`. `ActionOutcome`
  carries `category`, `status: str` (mandatory domain status), `data: Mapping`,
  `staged_command_id: str | None = None`. `SettledOutcome` wraps
  `outcomes: tuple[ActionOutcome, ...]`. `PendingClarification` carries
  `unresolved_action_fingerprint: str`, `candidates: tuple[Mapping, ...]`,
  `source_input_window: tuple[int, int]`, `expires_at`, `status`.
- [ ] Step 4: Run the test — expect PASS.
- [ ] Step 5: Commit `feat(turn-inbound): typed data contracts`.

### Task 2: Planner emits a TurnPlan (LLM)

**Files:** Create `coke/turn/inbound/plan.py`; Test `tests/unit/coke/turn/inbound/test_plan.py`.
Reference the current shared JSON completion client in
`coke/llm/json_completion.py` and planner model factory
`coke/llm/config.py` (`create_planner_model`, GLM thinking-off).

- [ ] Step 1: Write a failing test with a stubbed JSON completion client whose
  `complete_json` returns `{"actions":[{"domain":"reminder","operation":"delete","params":{"match":"gym"}}],"reply_necessity":"reply_needed"}` and assert
  `SiliconFlowPlanner(client).plan(request)` returns a `TurnPlan` with one
  `ProposedAction(domain="reminder", operation="delete")` and
  `reply_necessity="reply_needed"`. Add cases: empty actions → greeting/converse;
  `intentional_no_reply` parsed.
- [ ] Step 2: Run — expect failure.
- [ ] Step 3: Implement `Planner` Protocol (`plan(request) -> TurnPlan`) and
  `SiliconFlowPlanner` using `AgnoJSONCompletionClient`. Prompt: propose a flat list of
  `{domain, operation, params}` with **keyword/natural params, never IDs, never
  precise extracted times** (detector owns extraction in Execute), plus
  `reply_necessity`. No `confidence`, no keyword routing. Validate domain/operation
  against allow-lists; reject unknown.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat(turn-inbound): planner emits TurnPlan`.

### Task 3: Planner prompt eval scaffold (subset corpus)

**Files:** Test `tests/unit/coke/turn/inbound/test_plan_cases.py`.

- [ ] Step 1: Encode ~30 representative cases (zh+en) as `(message, expected
  actions[domain/operation], expected reply_necessity)` covering: plain list,
  filtered list, create, batch create, update by keyword, delete by keyword,
  shared-reminder create with friend name, friend list, settings, greeting,
  intentional no-reply. Assert the planner (with a recorded/stub client per case)
  produces the expected action set. (Live-model run is a Phase 6 eval; here lock
  the parsing + shape.)
- [ ] Step 2–4: Run/iterate to green.
- [ ] Step 5: Commit `test(turn-inbound): planner case corpus`.

### Task 4: PlanCompile (deterministic, no LLM)

**Files:** Create `coke/turn/inbound/plan_compile.py`; Test `tests/unit/coke/turn/inbound/test_plan_compile.py`.

- [ ] Step 1: Write failing tests: `compile_plan` validates each `ProposedAction`'s
  operation against a per-domain required-param map; a structurally-missing
  required param yields a `needs_input` compiled mark (not an exception); unknown
  domain/operation → `not_possible` compiled mark; a valid action → `CompiledAction`.
  No resolution happens here (that is the service's job in Execute).
- [ ] Step 2: Run — expect failure.
- [ ] Step 3: Implement `compile_plan(plan) -> CompiledPlan` with a static
  required-param table (e.g. reminder.create requires `content`; reminder.delete
  requires `match`). Pure function, no I/O.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat(turn-inbound): deterministic plan compile`.

### Phase 1 Verification

- [ ] `.venv/bin/python -m pytest tests/unit/coke/turn/inbound -q` — all pass.
- [ ] `black coke/turn/inbound tests/unit/coke/turn/inbound && isort coke/turn/inbound tests/unit/coke/turn/inbound`.
- [ ] `zsh scripts/suggest-verification --base main` then run the suggested surface.
- [ ] Confirm nothing in the existing turn path was touched (`git diff --stat main` shows only `coke/turn/inbound/**`, tests, docs).

---

## Phase 2–6 Roadmap (expanded when reached)

### Phase 2: Execute core + reminder handler

Files: `coke/turn/inbound/execute.py`, `coke/turn/inbound/handlers/reminder.py`.
- `ActionHandler` protocol: `resolve_and_stage(compiled_action, guard) -> ActionOutcome`.
- Reminder handler calls existing `ReminderService` (`coke/domains/reminder/service.py`)
  for list/create/update/delete; maps service results to `ActionOutcome` with the
  mandatory status (`created`/`updated`/`cancelled`/`listed`/`partial`/
  `duplicate_active`/`already_cancelled`/`needs_choice`(ambiguous)/`needs_input`).
  Uses the detector (`coke/llm/reminder_detector.py`) for time extraction before a
  mutating create/update. Resolve before staging; stage only concrete commands.
- `ExecutionOutcomeBuilder` assembles `SettledOutcome` preserving model-visible
  vs internal facts.
- Tests: each service result → correct typed outcome+status; ambiguous→needs_choice;
  resolve_and_stage stages nothing on ambiguous.

### Phase 3: Express + streaming

Files: `coke/turn/inbound/express.py`.
- Narrow the interaction agent to render `SettledOutcome` (category+status, incl.
  partial-as-partial) or converse; no tools; reuse the streaming invoke proven in
  `coke/llm/agno_interaction_agent.py` (the corrected non-awaited `arun(stream=True)`).
- Streaming rule: non-mutating turns stream; mutating turns return full segments to
  be delivered post-commit (buffer in pipeline, not streamed pre-close).
- Tests: renders status faithfully; mutating-turn segments not delivered before close.

### Phase 4: CloseCoordinator + PendingClarification + pipeline wiring

Files: `coke/turn/inbound/close.py`, `coke/turn/inbound/pipeline.py`.
- `CloseCoordinator.commit(plan, segments, selected_staged_command_ids)`: recheck
  freshness/supersede, materialize selected commands atomically (reuse
  `ConversationRuntimeService.commit_reply` materialization semantics,
  `coke/domains/conversation_runtime/service.py:207`), set disposition, advance
  `last_closed_inbound_seq`, persist `PendingClarification` for unresolved actions.
- `pipeline.py` wires Plan→Compile→Execute→Express→Close, reads any open
  `PendingClarification`, and is selected at the runner inbound entry.
- Tests: selective partial close materializes only resolved commands; supersede
  before commit mutates/delivers nothing; pending_async_reply non-closing;
  PendingClarification round-trips and resolves next turn by fingerprint.

### Phase 5: Remaining handlers + multi-action aggregation

Files: `coke/turn/inbound/handlers/{social,friend,settings,calendar}.py`.
- Each maps its service results to category+status (social: missing title/time/
  context, inactive receiver, duplicate, unreachable; calendar: imported/skipped/
  downgraded/failed counts as `done.partial`; friend add/remove/list).
- Multi-action: run-all + aggregate; resolved stage, unresolved → PendingClarification.
- Tests: per-domain typed-outcome coverage; mixed multi-action aggregation.

### Phase 6: Parity, smoke, cutover, deletion

- Live-model planner eval + detector parity eval (zero-tolerance: false concrete
  time, missed clarification).
- Real-account webhook smoke (greeting/list/create/update/cancel/ambiguous-delete/
  shared/calendar/multi-action/clarification) reading `turn.plan|execute|express`
  telemetry; latency + TTFT before/after.
- Cut over inbound turns to the pipeline and verify on the real path.
- Delete retired inbound bypasses: action routing, streaming eligibility,
  output-protocol claim layer, recoverable-command subsystem, and
  interaction-agent orchestration — keeping render-mode agent for notifications.

---

## Self-Review

- **Spec coverage:** Phase 1 covers data contracts + Plan + PlanCompile; Phases
  2–6 map to Execute/handlers/typed-outcomes (2,5), Express+streaming (3), close +
  PendingClarification + partial materialize (4), evals/smoke/cutover/deletion (6).
  Scope (inbound-only, render retained) is enforced by runner entry points and
  inbound pipeline isolation.
- **No placeholders in Phase 1:** tasks carry concrete tests, signatures, and the
  contract fields. Phases 2–6 are explicitly roadmap, expanded before execution.
- **Type consistency:** `ActionOutcome{category,status,data,staged_command_id}`,
  `TurnPlan{actions,reply_necessity}`, `ProposedAction{domain,operation,params}`
  used consistently across phases.
