# Coke Clean Rebuild Product Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the missing conversational settings/profile backend and close the live product bugs for unsupported coach booking and global timezone switching.

**Architecture:** Settings is a bounded domain over the existing `account`, `agent_settings`, and `user_profile` tables in `coke/schema.py`. Customer HTTP routes use session-token authentication, and chat changes go through a settings tool exposed to the single Interaction Agent. Unsupported external booking remains a prompt/tool-contract boundary: the agent declines and may offer a reminder, but reminder creation happens only when the user explicitly asks to be reminded.

**Tech Stack:** Python 3.12, Flask blueprints, SQLAlchemy Core repositories, pytest unit tests, in-memory service tests, Agno tool adapter wiring.

---

**Plan Status:** complete
**Status Date:** 2026-05-31
**Completion Evidence:** Product-settings targeted tests: `66 passed`; full backend unit suite: `441 passed`; web surface: `51 passed (51)` files / `210 passed`; repo-OS checks passed. `COKE_TEST_DATABASE_URL` was unset, so gated integration tests were not run.
**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md` sections 5.5 and 5.11.
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md` sections 3, 4, 8, 9, 10, and 11.

## File Structure

- Create `coke/domains/settings/__init__.py`: public exports for the settings domain.
- Create `coke/domains/settings/models.py`: immutable settings/profile view models and domain errors.
- Create `coke/domains/settings/repository.py`: in-memory and Postgres repositories mapped to existing schema tables only.
- Create `coke/domains/settings/service.py`: view/update/reset behavior, timezone validation, proactive-off reminder cancellation.
- Create `coke/api/settings_routes.py`: session-authenticated customer settings routes under `/api/settings`.
- Modify `coke/app.py`: optional `settings_service` kwarg and blueprint registration.
- Modify `coke/composition.py`: settings service construction, settings tool adapter, and pre-LLM trusted settings facts.
- Modify `coke/turn/context.py`: add `settings` as an interactive tool name.
- Modify `coke/turn/agent.py`: add `settings_tool` to `AgentToolPorts`.
- Modify `coke/llm/agno_interaction_agent.py`: settings tool documentation, user personalization instructions, and unsupported external-booking boundary.
- Modify `docs/fitness/ownership-registry.yaml`: register the new settings API route owner for repo-OS checks.
- Create `tests/unit/coke/settings/test_settings_service.py`: service behavior for timezone, profile/settings, proactive off.
- Create `tests/unit/coke/settings/test_settings_routes.py`: session-authenticated API behavior.
- Create `tests/unit/coke/settings/test_settings_composition.py`: runtime composition and trusted facts.
- Modify `tests/unit/coke/llm/test_interaction_agent.py`: agent instructions/tool docs and coach-booking refusal test.
- Modify `tests/unit/coke/test_backend_foundation.py`: keep composed runtime fixture compatible with the new optional settings service.

## Task 1: Red Tests

**Files:**
- Create: `tests/unit/coke/settings/test_settings_service.py`
- Create: `tests/unit/coke/settings/test_settings_routes.py`
- Create: `tests/unit/coke/settings/test_settings_composition.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `tests/unit/coke/test_backend_foundation.py`

- [x] **Step 1: Write service tests**

Add tests that prove `default_timezone` persists globally, subsequent reminder creation uses the new timezone when the tool supplies trusted settings facts, existing reminders keep their original `next_fire_at` and `captured_timezone`, proactive-off discards untriggered proactive reminders, memory-off persists without deleting profile/settings data, and reset restores only agent settings defaults.

- [x] **Step 2: Write route tests**

Add tests for `GET /api/settings`, `PATCH /api/settings`, `PATCH /api/settings/profile`, and `POST /api/settings/reset`. Each route must derive `account_id` from the session token via `auth_helpers` and ignore any client-supplied `account_id`.

- [x] **Step 3: Write composition and agent tests**

Add tests that composition exposes a `settings_tool`, pre-LLM trusted facts reflect persisted settings, the Agno agent publishes settings tool docs, and unsupported coach-booking phrasing produces a refusal path with no reminder row and no booking claim.

- [x] **Step 4: Run red tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/settings tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/test_backend_foundation.py -q
```

Expected before implementation: FAIL because the settings domain/routes/tool do not exist and the agent instructions do not yet contain the booking/settings contract.

## Task 2: Settings Domain

**Files:**
- Create: `coke/domains/settings/__init__.py`
- Create: `coke/domains/settings/models.py`
- Create: `coke/domains/settings/repository.py`
- Create: `coke/domains/settings/service.py`

- [x] **Step 1: Implement models and errors**

Define `SettingsError`, `AgentSettings`, `UserProfile`, and `SettingsView`. Use `None` for unset optional text fields and `True` defaults for `proactive_enabled` and `memory_enabled`.

- [x] **Step 2: Implement repositories**

Map only to `schema.account`, `schema.agent_settings`, and `schema.user_profile`. The in-memory repository shares the identity repository account dictionary when composed in memory; the Postgres repository uses the existing SQLAlchemy table metadata and does not create or assume new columns.

- [x] **Step 3: Implement service behavior**

Validate IANA timezone names with `zoneinfo.ZoneInfo`. Persist account `default_timezone` without touching existing reminders. Update/reset agent settings, update profile fields, and call `discard_future_proactive(account_id, discarded_at)` only when `proactive_enabled` changes from true to false.

- [x] **Step 4: Run service tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/settings/test_settings_service.py -q
```

Expected after implementation: all service tests pass.

## Task 3: API and Composition Wiring

**Files:**
- Create: `coke/api/settings_routes.py`
- Modify: `coke/app.py`
- Modify: `coke/composition.py`
- Modify: `coke/turn/context.py`
- Modify: `coke/turn/agent.py`

- [x] **Step 1: Implement `/api/settings` routes**

Register routes only when both `settings_service` and `identity_access_service` are present. Use `require_customer_account_id(identity_service, SettingsError)` for every customer settings route.

- [x] **Step 2: Add settings service and tool to composition**

Construct `SettingsService` with the settings repository and reminder repository. Add `SettingsToolAdapter` operations `view_settings`, `update_settings`, `set_timezone`, `update_profile`, and `reset_agent_settings`. Add `settings_tool` to interactive tool profiles.

- [x] **Step 3: Feed trusted settings facts to the agent**

Update the pre-LLM gate to read persisted settings for the active account. Trusted facts must include `default_timezone`, personalization fields, `proactive_enabled`, and `memory_enabled`.

- [x] **Step 4: Run route and composition tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/settings/test_settings_routes.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/test_backend_foundation.py -q
```

Expected after implementation: all route/composition tests pass.

## Task 4: Interaction Agent Contract

**Files:**
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [x] **Step 1: Add settings tool docs**

Document when to call `settings_tool`, including conversational global timezone switches, assistant name/address/persona/style/rules changes, proactive switch, memory switch, profile updates, and reset.

- [x] **Step 2: Add unsupported external-booking boundary**

Tell the agent that external booking/reservation/class/coach actions are unsupported unless a product tool exists and succeeds. The correct behavior is to decline gracefully and offer to set a reminder; call `reminder_tool` only when the user explicitly asks for a reminder, and never claim the class or appointment is booked.

- [x] **Step 3: Run agent tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected after implementation: all agent tests pass.

## Task 5: Verification, Plan Closeout, Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-product-settings.md`

- [x] **Step 1: Run targeted product-settings tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/settings tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/test_backend_foundation.py -q
```

- [x] **Step 2: Run full unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

- [x] **Step 3: Run integration tests only when the gated database URL exists**

Run when `COKE_TEST_DATABASE_URL` is set:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

- [x] **Step 4: Run diff-aware repository checks**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [x] **Step 5: Mark this plan complete**

Set `Plan Status` to `complete` only after the verification commands above have been read and any failures are classified or fixed.

- [x] **Step 6: Commit the coherent product-settings change**

Run:

```bash
git status --short
git add coke/domains/settings coke/api/settings_routes.py coke/app.py coke/composition.py coke/turn/context.py coke/turn/agent.py coke/llm/agno_interaction_agent.py docs/fitness/ownership-registry.yaml tests/unit/coke/settings tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/test_backend_foundation.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-product-settings.md
git commit -m "feat: add product settings backend"
git log --oneline main..HEAD
```

Expected final state: working tree contains only unrelated pre-existing changes, if any; the new commit appears on `fix/product-settings`.
