# Ownership Fitness Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ownership-oriented verification surfaces for product systems without replacing existing planning surfaces.

**Architecture:** Extend `docs/fitness/surfaces.yaml` and `scripts/verify-surface` with product surfaces that map to focused verification commands. `scripts/suggest-verification` continues to route by changed paths and can return both planning and ownership surfaces when paths overlap.

**Tech Stack:** YAML, zsh, Python guardrail tests, pytest.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after ownership registry vocabulary exists.

## Scope

Included:

- Add `product-reminder`, `product-memo`, `product-calendar-import`, and `product-timezone` surfaces.
- Add dry-run and command tests.
- Keep current surfaces unchanged.

Excluded:

- New test suites for product behavior.
- Full generated impact graph.

## File Map

- `docs/fitness/surfaces.yaml`: add product surfaces.
- `scripts/verify-surface`: add product surface commands.
- `tests/unit/test_verify_surface.py`: add dry-run coverage.
- `tests/unit/test_guardrail_scripts.py`: add suggest-verification coverage.

## Work Breakdown

### Task 1: Add Product Surfaces

**Files:**
- Modify: `docs/fitness/surfaces.yaml`

- [x] **Step 1: Add product surface entries**

Add these surfaces after `worker-runtime`:

```yaml
  - name: product-reminder
    paths:
      - agent/reminder/**
      - agent/runner/reminder_*.py
      - gateway/packages/api/src/routes/customer-reminder-routes.ts
      - connector/clawscale_bridge/reminder_management_service.py
      - dao/reminder_dao.py

  - name: product-memo
    paths:
      - memo-runtime/**
      - agent/agno_agent/capabilities/memo.py

  - name: product-calendar-import
    paths:
      - gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts
      - gateway/packages/api/src/routes/customer-google-calendar-import-callback-routes.ts
      - gateway/packages/api/src/routes/calendar-import-handoff-routes.ts
      - gateway/packages/api/src/lib/google-calendar-*
      - gateway/packages/api/src/lib/calendar-import-handoff.ts
      - connector/clawscale_bridge/google_calendar_import_service.py
      - agent/agno_agent/capabilities/calendar_import_port.py
      - agent/agno_agent/tools/calendar_import_handoff.py

  - name: product-timezone
    paths:
      - agent/timezone_service.py
      - agent/agno_agent/capabilities/timezone_port.py
      - agent/agno_agent/tools/timezone_tools.py
      - dao/user_dao.py
```

### Task 2: Add Verification Commands

**Files:**
- Modify: `scripts/verify-surface`
- Modify: `tests/unit/test_verify_surface.py`

- [x] **Step 1: Add dry-run test**

Add to `tests/unit/test_verify_surface.py`:

```python
def test_verify_surface_dry_run_prints_product_surface_commands():
    result = run_verify_surface(
        "--dry-run",
        "product-reminder",
        "product-calendar-import",
        "product-timezone",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/unit/agent/test_reminder" in result.stdout
    assert "calendar_import" in result.stdout
    assert "timezone" in result.stdout
```

- [x] **Step 2: Add `verify-surface` cases**

Add cases:

```zsh
    product-reminder)
      print "$pytest_cmd tests/unit/reminder/ tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_command_executor.py tests/unit/runner/test_reminder_event_handler.py tests/unit/runner/test_reminder_scheduler.py -v"
      ;;
    product-memo)
      print "$pytest_cmd tests/unit/agent/test_memo_capability_adapter.py -v"
      print "$pytest_cmd memo-runtime/tests -v"
      ;;
    product-calendar-import)
      print "$pytest_cmd tests/unit/agent/test_calendar_import_handoff_tool.py tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py -v"
      print "pnpm --dir gateway/packages/api test calendar-import"
      ;;
    product-timezone)
      print "$pytest_cmd tests/unit/agent/test_timezone_port.py tests/unit/agent/test_timezone_service.py tests/unit/test_timezone_tools.py tests/unit/test_user_dao_timezone.py -v"
      ;;
```

### Task 3: Add Suggestion Tests

**Files:**
- Modify: `tests/unit/test_guardrail_scripts.py`

- [x] **Step 1: Add product surface suggestion test**

Add:

```python
def test_suggest_verification_includes_product_surfaces():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "agent/reminder/runtime_contract.py",
        "--files",
        "agent/timezone_service.py",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "product-reminder" in result.stdout
    assert "product-timezone" in result.stdout
```

### Task 4: Verify Product Surface Routing

**Files:**
- Read: guardrail and verification files

- [x] **Step 1: Run repo-OS tests**

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/ownership-fitness-surfaces
.venv/bin/python -m pytest tests/unit/test_verify_surface.py tests/unit/test_guardrail_scripts.py -v \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/ownership-fitness-surfaces/pytest.log
zsh scripts/check
```

Expected: tests and check pass.

- [x] **Step 2: Dry-run product surfaces**

```bash
zsh scripts/verify-surface --dry-run product-reminder product-memo product-calendar-import product-timezone \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/ownership-fitness-surfaces/dry-run.log
```

Expected: every surface is recognized and prints commands.

### Task 5: E2E Existence Check For Surface Commands

**Files:**
- Create: `scripts/e2e/ownership-fitness-surfaces.sh`

- [x] **Step 1: Verify every test path referenced by a product surface exists**

A surface that prints commands referencing non-existent test files is silently broken. Create `scripts/e2e/ownership-fitness-surfaces.sh` (executable) that:

1. Runs `zsh scripts/verify-surface --dry-run product-reminder product-memo product-calendar-import product-timezone` and captures the command list.
2. For each path token that looks like a test path (matches `^tests/.*\.py$` or `^memo-runtime/tests` or a TypeScript test path), checks the file or directory exists. If a token is a directory (ends with `/`), it must contain at least one matching test.
3. Writes `{surface, command, missing_paths}` JSON lines to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/ownership-fitness-surfaces/path-existence.jsonl`.
4. Prints `[BEGIN]`/`[STEP <surface>]`/`[OK <surface>]`/`[FAIL <surface> <missing>]` lines and exits non-zero if any referenced test path is missing.
5. As a sanity step, runs `zsh scripts/suggest-verification --files agent/reminder/runtime_contract.py --files agent/timezone_service.py` and asserts the output contains both `product-reminder` and `product-timezone`.

Expected: the script exits 0, proving the new surfaces wire to commands that actually exist.
