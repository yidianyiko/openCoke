# Turn Eager Execute (Abolish Staging) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Companion spec (authoritative for every per-symbol detail, deletion line, and contract):** `docs/superpowers/specs/2026-06-12-turn-eager-execute-abolish-staging-design.md`. Read it fully before starting. This plan orders the work into committable phases; the spec gives the exact symbols, file:line anchors, and rationale. When they disagree, the spec wins — but verify both against the current tree (line numbers drift).

**Goal:** Replace optimistic staging + materialize-at-close with execute-before-express (B2): Execute calls the real domain service (writing into the shared turn session, uncommitted); Express describes the real `settled_outcome`; Close commits writes+outbound+disposition atomically; delete the entire staged-command layer.

**Architecture:** B2 transaction boundary — all inbound-handler domain writes go through the shared `child_session`; the only commit is the close-boundary committer (`coke/composition.py:1677`). Uncommitted writes roll back on supersession. Plan→PlanCompile→Execute(real write)→Express(render real outcome; recover-in-pipeline on failure)→Close(commit+deliver). Inbound interactive path only; render/notification `pending_async_reply`/`WAITING_TEXT` untouched.

**Tech Stack:** Python 3.12, pytest, SQLAlchemy + Alembic, Postgres, Redis; existing `coke/turn/inbound/*` pipeline.

---

## Conventions for every phase

- **Branch:** do all work on `turn-eager-execute-abolish-staging` (create from `main` once, at Phase 0). Do NOT commit to `main`.
- **TDD:** for behavior changes (handlers, recovery, close, pipeline), write/adjust the failing test first, watch it fail, implement, watch it pass. For pure deletions, the gate is "the suites that referenced the deleted symbol are updated and green."
- **Commit after each phase** with a focused message; end every commit message with the Co-Authored-By trailer.
- **Per-phase verification command:** `.venv/bin/python -m pytest <the touched suites> -q`. Full gate runs in Phase 11.
- **Never** add a compatibility shim, alias, or dual path (AGENTS.md delivery rules). This is a clean cut.

---

## Phase 0: Foundation — verify and lock the B2 transaction boundary

**Why first:** every later phase's correctness (atomicity, supersession-undo, replay) depends on "no inbound mutating service self-commits; only the close boundary commits." Confirm before changing anything.

**Files:**
- Inspect: `coke/composition.py:1655-1678` (shared `child_session`, `close_boundary_committer=child_session.commit`)
- Inspect: `coke/domains/reminder/service.py`, `coke/domains/social_scheduling/service.py` + `repository.py`, `coke/domains/settings/service.py`, `coke/domains/calendar_import/service.py` + repos, `coke/domains/_pg.py`
- Test: `tests/unit/coke/turn/inbound/test_autonomous_commit_guard.py` (Create)

- [ ] **Step 1:** Grep every domain service/repository for self-commits: `grep -rn "\.commit(\|session.begin(\b\|\.begin()" coke/domains coke/turn` and classify each as savepoint (`begin_nested`) / boundary-committer / helper vs an autonomous `session.commit()`. Record findings in the PR description. (Confirmation review found none today; re-verify because handlers will now drive these in Execute.)
- [ ] **Step 2: Write the guard test (failing or asserting-current):** a test that runs a mutating handler through Execute WITHOUT firing the close-boundary committer, then asserts the DB row is NOT visible to a fresh session (i.e., uncommitted). Cover reminder create + one social op + settings + calendar import.

```python
# tests/unit/coke/turn/inbound/test_autonomous_commit_guard.py
def test_execute_writes_are_not_durable_until_close_boundary(pg_runtime):
    # run handler.execute(...) for a reminder create inside a turn session,
    # do NOT call the close-boundary committer,
    # open a second session and assert the reminder row is absent.
    ...
```

- [ ] **Step 3:** If any service self-commits, change it to write through the injected shared-session repository only (no `session.commit()`); otherwise record "no change needed".
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/unit/coke/turn/inbound/test_autonomous_commit_guard.py -q` → PASS.
- [ ] **Step 5: Commit** `test(turn): assert execute writes are uncommitted until close boundary (B2 foundation)`.

---

## Phase 1: Contracts — drop `staged_command_id` and `MaterializationPlan`, rename to `execute`

**Files:**
- Modify: `coke/turn/inbound/contracts.py` (remove `ActionOutcome.staged_command_id`, delete `MaterializationPlan`)
- Modify: `coke/turn/inbound/execute.py` (protocol `resolve_and_stage` → `execute(compiled_action, guard, *, action_index, turn_id)`; `ActionExecutor` enumerates with `action_index`/`turn_id` and derives the stable per-action identity)
- Test: `tests/unit/coke/turn/inbound/test_contracts.py`, `tests/unit/coke/turn/inbound/test_execute.py`

- [ ] **Step 1:** Update `test_contracts.py:40,74` to drop the staged field / `MaterializationPlan`; update `test_execute.py:18,48` fakes to expose `execute` and assert no staged id. Run → FAIL.
- [ ] **Step 2:** Edit `contracts.py` and `execute.py` per spec "Execute Contract". Keep `ActionOutcome = {category, status, data}`.
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/unit/coke/turn/inbound/test_contracts.py tests/unit/coke/turn/inbound/test_execute.py -q` → PASS.
- [ ] **Step 4: Commit** `refactor(turn): execute contract replaces resolve_and_stage; drop staged_command_id/MaterializationPlan`.

---

## Phase 2: Reminder handler — real `execute_batch` in Execute (fixes the original bug)

**Files:**
- Modify: `coke/turn/inbound/handlers/reminder.py` (`_create`/`_batch_create`/`_keyword_mutation` call the service for real; delete `_stage_execute_batch`, `_optimistic_batch_data`, `_staged_create_item`; map real `ReminderItemResult`s incl. `needs_past_time_confirmation` → `needs_confirmation`; preserve the existing duration-required guard)
- Test: `tests/unit/coke/turn/inbound/test_reminder_handler.py`

- [ ] **Step 1:** Rewrite the reminder handler tests to drive a fake `ReminderService.execute_batch` and assert real outcomes + no `staged_command_id`. Add the regression: detected genuinely-past time → `ActionOutcome(category="needs_confirmation", status="needs_past_time_confirmation")`, never a staged success. Keep duration-required tests. Run → FAIL.
- [ ] **Step 2:** Implement per spec "Reminder Handler": `guard.guard_state_change(); batch = reminder_service.execute_batch(owner, [item], commit_guard=guard.guard_state_change)`; map results; delete the optimistic helpers.
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/unit/coke/turn/inbound/test_reminder_handler.py -q` → PASS.
- [ ] **Step 4: Commit** `fix(turn): reminder create executes for real in Execute; past time → needs_confirmation`.

---

## Phase 3: Social/friend/settings/calendar handlers — remove post-write staging

**Files:**
- Modify: `coke/turn/inbound/handlers/social.py` (delete the stage-after-write blocks; return the real service outcome; drop `staged_pending_close`), `coke/domains/social_scheduling/models.py` (drop `staged_pending_close` status + `staged_command_id`), `coke/turn/output_protocol.py:23` (drop `staged_pending_close` mapping)
- Modify: `coke/turn/inbound/handlers/friend.py`, `coke/turn/inbound/handlers/settings.py`, `coke/turn/inbound/handlers/calendar.py` (delete `_stage_*` helpers + staged id assignment; keep real call). Settings/calendar: thread `commit_guard` if cheap (optional early-abort per spec); otherwise leave (close boundary is the gate).
- Test: `test_social_handler.py`, `test_friend_handler.py`, `test_settings_handler.py`, `test_calendar_handler.py`, `tests/unit/coke/turn/test_output_protocol.py`

- [ ] **Step 1:** Update each handler test to assert exactly one real service write and no staged id (`test_social_handler.py:359`, `test_friend_handler.py:219`, `test_settings_handler.py:123`, `test_calendar_handler.py:146`; `test_output_protocol.py:216,246,272`). Run → FAIL.
- [ ] **Step 2:** Implement deletions/mappings per spec "Social, Friend, Settings, Calendar".
- [ ] **Step 3: Run** the four handler suites + `test_output_protocol.py` → PASS.
- [ ] **Step 4: Commit** `refactor(turn): handlers return real service outcomes; drop staged replay + staged_pending_close`.

---

## Phase 4: Express — drop staged payload field; recovery grounded in `settled_outcome` inside the pipeline

**Files:**
- Modify: `coke/turn/inbound/express.py` (payload no longer serializes `staged_command_id`)
- Modify: `coke/turn/inbound/pipeline.py` (on `ExpressOutputError`, build grounded recovery from `settled_outcome` and `commit_recovery_reply` — recovery lives here, it owns `settled_outcome`)
- Add: a `settled_outcome`-grounded recovery-text helper (repoint `coke/turn/runner.py:_grounded_recovery_text` staged branch, or add a pipeline-local builder)
- Test: `tests/unit/coke/turn/inbound/test_express.py`, `tests/unit/coke/turn/inbound/test_pipeline.py`

- [ ] **Step 1:** Add a pipeline test: Execute returns `done/created`; Express raises `ExpressOutputError`; assert pipeline produces a `recovered` close grounded in the real outcome, with delivered segments and no zero-outbound failed disposition. Update `test_express.py:148,250` for the dropped field. Run → FAIL.
- [ ] **Step 2:** Implement recovery-in-pipeline + payload field removal per spec "Express" + "Pipeline".
- [ ] **Step 3: Run** `test_express.py test_pipeline.py` → PASS.
- [ ] **Step 4: Commit** `feat(turn): express-failure recovery grounded in settled_outcome inside pipeline`.

---

## Phase 5: Close — no materialization; buffer-then-deliver-after-commit streaming

**Files:**
- Modify: `coke/turn/inbound/close.py` (drop `selected_staged_command_ids` from `CloseRequest`/`CloseResult`; `CloseCoordinator` no longer takes/calls a materializer; delete the materialization-failure rewrite at `:172`)
- Modify: `coke/domains/conversation_runtime/service.py` (`commit_reply`/`commit_no_reply`/`mark_pending_async_reply` lose `materialize_staged_command`; delete `_materialize_staged_commands`; `commit_recovery_reply` drops staged supersession loop)
- Modify: `coke/turn/inbound/pipeline.py` (delete `_staged_command_ids` + staged branch; uniform execute→express→close→deliver; buffer segments, commit, then deliver committed rows exactly once)
- Test: `tests/unit/coke/turn/inbound/test_close.py`, `test_pipeline.py`, `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`

- [ ] **Step 1:** Update close/pipeline/runtime tests to drop materializer + staged ids and assert close order (outbound → disposition → `_save_close_state`) and deliver-after-commit (`test_close.py:80,226`; `test_pipeline.py:269,559`; `test_conversation_runtime_service.py:311,607,640`). Add a no-pre-commit-delivery assertion. Run → FAIL.
- [ ] **Step 2:** Implement per spec "Close" + "Pipeline" + "Streaming Policy".
- [ ] **Step 3: Run** those suites → PASS.
- [ ] **Step 4: Commit** `refactor(turn): close has no materialization; buffer-then-deliver-after-commit`.

---

## Phase 6: Runner — remove materializer wiring; recovery is pipeline-owned

**Files:**
- Modify: `coke/turn/runner.py` (remove `staged_command_materializer` from `__init__`; delete `_materialize_staged_command`; drop materializer args from render-agent close calls; remove `staged_command_id` parsing at `:1972` and `_has_current_turn_social_scheduling_create_stage`; `_run_inbound_pipeline_async` reports the pipeline's `recovered` close, reserves `mark_failed` for infra/close failures only)
- Test: `tests/unit/coke/worker/test_waiting_reply.py`, `tests/unit/coke/worker/test_media_resolution.py`, runner-level pipeline tests

- [ ] **Step 1:** Update `test_waiting_reply.py:105,151`, `test_media_resolution.py:116` to drop materializer expectations; keep render/notification `pending_async`/`WAITING_TEXT` behavior intact. Run → FAIL.
- [ ] **Step 2:** Implement runner changes per spec "Runner". Preserve render/notification path untouched except dropping the now-typeless materializer param.
- [ ] **Step 3: Run** those suites → PASS.
- [ ] **Step 4: Commit** `refactor(turn): runner drops staged materializer wiring; pipeline owns recovery`.

---

## Phase 7: Composition + adapters — collapse dual API; delete materializer wiring

**Files:**
- Modify: `coke/composition.py` (delete `_FreshStagedCommandMaterializer`, materializer construction/wiring `:1528,:1556,:1587`; collapse `execute`/`execute_without_staging` dual adapter API to one real `execute`; delete `_staged_command_result`, `_guard_can_stage`, staged write validators `:2001,:2043,:2120,:2136,:2151`)
- Modify: `coke/llm/agno_interaction_agent.py` (remove `staged_pending_close` prompt text + model-visible pruning `:489,:506,:1389`; preserve render/notification `pending_async`)
- Test: `tests/unit/coke/test_social_scheduling_tool_adapter.py`, `tests/unit/coke/test_tool_adapter_staging_guards.py`, `tests/unit/coke/llm/test_interaction_agent.py`

- [ ] **Step 1:** Update `test_social_scheduling_tool_adapter.py:399,433,457`, `test_tool_adapter_staging_guards.py:20`, `test_interaction_agent.py:1039` to the single-execute API and no staged-pending-close. Run → FAIL.
- [ ] **Step 2:** Implement deletions per spec "Deletions Table" composition rows.
- [ ] **Step 3: Run** those suites → PASS.
- [ ] **Step 4: Commit** `refactor(adapters): single execute API; delete staged tool surfaces`.

---

## Phase 8: Delete the staged-command storage layer + migration

**Files:**
- Modify: `coke/domains/conversation_runtime/models.py` (delete `StagedCommand`), `repository.py` (delete protocol/in-memory/postgres staged methods + mappers), `coke/domains/conversation_runtime/service.py` (delete `stage_command`), `coke/turn/freshness.py` (delete `stage_command`), `coke/turn/staged_commands.py` (delete file), `coke/turn/inbound/staging.py` (`json_safe`: remove if unused after handler edits; else keep only non-staging usage), `coke/schema.py:270` (delete table)
- Create: `migrations/versions/20260612_0001_drop_staged_command.py`
- Test: `tests/unit/coke/test_clean_schema_contract.py:64,563,916`, `tests/unit/coke/conversation_runtime/test_schema_contract.py:55`, `tests/unit/coke/turn/inbound/test_staging.py`

- [ ] **Step 1:** Update schema-contract tests to not expect `staged_command`; delete/retarget `test_staging.py`. Run → FAIL.
- [ ] **Step 2:** Delete the storage layer + write the Alembic drop migration (down_revision = current head; document downgrade policy in the migration per spec).
- [ ] **Step 3: Run** schema-contract tests + `.venv/bin/python -m pytest tests/unit/coke/conversation_runtime -q` → PASS. Verify migration head: `.venv/bin/alembic heads` is single.
- [ ] **Step 4: Commit** `refactor(db): drop staged_command table, model, repository, schema`.

---

## Phase 9: Prompts — ambiguous clock-time near-future resolution

**Files:**
- Modify: `coke/turn/inbound/plan.py:32` (planner: keep ambiguous `8-9` verbatim in `time_phrase`, no AM/PM resolution in Plan)
- Modify: `coke/llm/reminder_detector.py:48-70` (detector: ambiguous hour without AM/PM → plausible near-future relative to authoritative `now`; example "今天8-9" at 14:52 → 20:00-21:00; only return past time when clearly meant)
- Test: detector unit test if one exists; otherwise add a focused prompt-contract test or rely on the smoke in Phase 11

- [ ] **Step 1:** Add/extend a detector test asserting the near-future evening reading for an afternoon `now`, and the genuinely-past phrase still returns a past time (→ `needs_past_time_confirmation` downstream). Run → FAIL (or document why it must be a smoke if the detector is a live-LLM call — then assert via Phase 11 smoke).
- [ ] **Step 2:** Edit the two prompts per spec "Prompt Changes".
- [ ] **Step 3: Run** the detector test → PASS (or note smoke-deferred).
- [ ] **Step 4: Commit** `feat(prompt): resolve ambiguous clock times to plausible near-future`.

---

## Phase 10: Regression + supersession/atomicity/replay tests + smoke-script updates

**Files:**
- Test: add the original-bug regression (today after 14:00, "今天8-9给我建立一个运动的日程" → real reply, never silent); B2 rollback-on-supersession test; B2 atomicity/replay test; (autonomous-commit guard already in Phase 0)
- Modify: `scripts/smoke/v6_wechat_smoke.py:228-233`, `scripts/smoke/v6_cases.py:13-19`, `scripts/turn_pipeline_probe.py:70` (assert real domain rows/outcomes, not staged rows)

- [ ] **Step 1:** Write the supersession test per spec Test Plan item 7: destructive handler writes in Execute, Express awaits, newer inbound cancels before close → assert the write did NOT become durable, turn superseded, no delivery. Write the replay test (item 8). Run → FAIL/PASS as written.
- [ ] **Step 2:** Implement any glue the tests reveal as missing; update the smoke scripts.
- [ ] **Step 3: Run** the new tests → PASS.
- [ ] **Step 4: Commit** `test(turn): B2 supersession-rollback, atomicity/replay, original-bug regression; fix smoke scripts`.

---

## Phase 11: Docs + full verification gate

**Files:**
- Modify: `docs/ARCHITECTURE.md:22,70,74,144,152` (Execute writes for real; Close no longer materializes; preserve render/waiting docs)
- Modify: `docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md` (mark staging/`MaterializationPlan`/mutating-streaming sections amended/superseded, pointing to this spec)
- Create/Modify: `docs/issues/2026-06-12-reminder-past-time-silent-failure.md` (incident record: symptom, root cause, fix commits, verification)

- [ ] **Step 1:** Update the docs above.
- [ ] **Step 2: Full gate:** `.venv/bin/python -m pytest tests/unit/coke -q`; then `zsh scripts/suggest-verification --base main` and `zsh scripts/review-trigger --base main`; run the suggested surfaces; `zsh scripts/check`.
- [ ] **Step 3:** Confirm no remaining staging references: `grep -rn "staged_command\|resolve_and_stage\|MaterializationPlan\|staged_pending_close\|materialize_staged\|StagedCommand" coke/ tests/ scripts/ migrations/` returns only the new drop-migration. Fix any stragglers.
- [ ] **Step 4: Commit** `docs(turn): record eager-execute cutover; amend 2026-06-10 spec; close incident`.

---

## Phase 12: Handoff for review + deploy (owner: Claude)

Not executed by the implementer. After Phases 0-11 are green on the branch, Claude reviews the diff against the spec, runs the smoke plan (`v6-wechat-smoke`, `coke-agent-smoke`, the real "今天8-9" smoke, the Express-failure recovery smoke), and follows the spec "Rollout And Deploy" sequence (drain workers → migration → code → restart → smoke → watch).

---

## Self-Review (done by plan author)

- **Spec coverage:** Phases 0-11 map to spec task list items 0-19 (Phase 0↔task 0; Phase 1↔tasks 1-of-contracts+5+6; Phase 2↔task 7; Phase 3↔task 8; Phase 4↔task 12; Phase 5↔tasks 11+3-of-close; Phase 6↔tasks 4-runner+10; Phase 7↔tasks 4+9+10; Phase 8↔tasks 1-3 storage; Phase 9↔task 13; Phase 10↔tasks 15+16+14; Phase 11↔tasks 17+18+19). No spec section unmapped.
- **Ordering safety:** behavior phases (1-7) precede storage deletion (8) so tests stay runnable; Phase 0 locks the B2 invariant first.
- **No placeholders:** each phase names exact files + the spec section carrying the per-symbol code; deletions are concrete symbols, not "remove staging stuff".
