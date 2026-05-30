# Coke Clean Rebuild E2E Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the independently-built Coke domains and Turn runner through one composition root and prove the composed runtime with end-to-end in-memory integration tests.

**Architecture:** Add a composition root that constructs the real in-memory domain services, wraps domain method-name differences behind thin Turn tool adapters, and builds a `TurnRunner` with injected semantic interpreter, Interaction Agent, memory, Redis lock, outbound delivery, and calendar provider adapters. Keep HTTP integration additive by allowing `create_app` to receive the composed runtime and register existing domain blueprints from it.

**Tech Stack:** Python, Flask, pytest, in-memory repositories, existing Coke domain services, existing Turn runner ports.

**Plan Status:** complete

**Verification Evidence:**
- `/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py -v` — `5 passed`
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -v` — `312 passed`
- `git diff --check` — passed with no output
- `zsh scripts/suggest-verification --base HEAD~1` — suggested `clean-rebuild-backend repo-os-docs`
- `zsh scripts/review-trigger --base HEAD~1` — `human_review_required: no`; medium risk triggers from broader dirty-base diff and plan docs
- `zsh scripts/check` — failed on existing missing `memo-runtime`/`gateway` ownership and ownership-registry paths, unrelated to the composition files changed in this slice

---

### Task 1: Failing Integration Tests For Composed Runtime

**Files:**
- Create: `tests/integration/coke/test_composition_turn_integration.py`

- [x] **Step 1: Write failing end-to-end tests**

Create tests that build the composed runtime with deterministic fakes for the semantic interpreter, Interaction Agent, Redis lock, outbound delivery, and Google Calendar client. Drive `InboundTurn` and `ReminderFireTurn` through the real `ConversationRuntimeService`, `ReminderService`, `SocialSchedulingService`, and Turn runner.

Required assertions:
- reminder-create inbound calls the real reminder domain through the Turn tool adapter and records `replied`
- intentional no-reply skips the agent, records `no_reply`, and creates no reminder
- superseded inbound bumps `latest_inbound_seq`, blocks the reminder commit, and records `superseded`
- render-mode reminder fire produces prose, exposes no mutation tools, and creates no new reminder rows

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py -v
```

Expected: FAIL because `coke.composition` and the composed runtime API do not exist yet.

### Task 2: Composition Root And Thin Tool Adapters

**Files:**
- Create: `coke/composition.py`

- [x] **Step 1: Implement composition root**

Create `CokeRuntime` and `CokeRepositories` dataclasses, plus `compose_coke_runtime(...)`. The function constructs in-memory repositories and real domain services by default, accepts explicit repository/service overrides for later Postgres swap-in, and returns a runtime containing the services, repositories, `AgentToolPorts`, `PreLLMGateService`, `ConversationLockManager`, and `TurnRunner`.

- [x] **Step 2: Implement adapter shims**

Add thin adapters in `coke/composition.py`:
- `ReminderToolAdapter.execute(command, guard)` calls `guard.guard_state_change()` and maps command dictionaries to `ReminderService.execute_batch(...)`.
- `SocialSchedulingToolAdapter.execute(command, guard)` calls `guard.guard_state_change()` and maps command dictionaries to social scheduling service methods.
- `CalendarImportToolAdapter.execute(command, guard)` calls `guard.guard_state_change()` and maps command dictionaries to calendar import service methods.
- `IdentityAccessToolAdapter.execute(command, guard)` maps command dictionaries to identity/access methods; state-changing commands call `guard.guard_state_change()`.
- `IdentityAccessPreLLMGatePort.evaluate(trigger)` uses `IdentityAccessService.check_access_for_inbound(...)` and activation facts to create `GateDecision`.
- `ReminderAvailabilityAdapter` and `IdentityReachabilityAdapter` provide the ports needed by Social Scheduling.

- [x] **Step 3: Run integration test to verify it passes**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py -v
```

Expected: PASS for the new integration tests.

### Task 3: App Composition Hook

**Files:**
- Modify: `coke/app.py`
- Test: `tests/integration/coke/test_composition_turn_integration.py`

- [x] **Step 1: Add minimal `create_app` hook**

Add an optional `composed_runtime=None` keyword argument. If present, store it in `app.config["COKE_RUNTIME"]` and fill existing optional service variables from the runtime only when the explicit service argument is `None`. Keep all existing blueprint-registration blocks unchanged except for this additive initialization.

- [x] **Step 2: Add integration assertion**

Extend the integration test to call `create_app(settings, composed_runtime=runtime)` and assert that `app.config["COKE_RUNTIME"]` is the same runtime and the existing health route still works.

- [x] **Step 3: Run integration test**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py -v
```

Expected: PASS.

### Task 4: Required Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md`

- [x] **Step 1: Run focused integration tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py -v
```

Expected: all tests pass.

- [x] **Step 2: Run full unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -v
```

Expected: all tests pass.

- [x] **Step 3: Mark this plan complete**

Update `Plan Status` to `complete` only after both verification commands pass, and check off completed steps.

- [x] **Step 4: Commit**

Run:

```bash
git add coke/composition.py coke/app.py tests/integration/coke/test_composition_turn_integration.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md
git commit -m "feat: wire coke clean runtime composition"
```
