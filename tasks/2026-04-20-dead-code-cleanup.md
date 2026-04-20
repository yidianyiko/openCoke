# Task: Dead Code Cleanup

- Status: Verified
- Owner: Codex
- Date: 2026-04-20

## Goal

Use static analysis to identify high-confidence dead code and remove it without changing runtime behavior.

## Scope

- In scope:
- Remove unused Python imports and locals confirmed by `ruff`/`vulture`
- Remove zero-reference TypeScript files confirmed by `knip` plus repository-wide search
- Record verification commands and evidence for the touched surfaces
- Out of scope:
- Refactoring live code paths for style only
- Removing compatibility placeholders or signatures with ambiguous external use
- Cleaning every low-confidence `knip`/`vulture` report in one pass

## Touched Surfaces

- worker-runtime
- gateway-api
- gateway-web
- repo-os

## Acceptance Criteria

- High-confidence dead code identified by tooling is removed
- No referenced runtime entrypoints or externally consumed exports are deleted
- Relevant Python and gateway verification commands run with fresh output

## Verification

- Command: `ruff check agent connector dao util framework entity conf --select F401,F841`
- Expected evidence: no remaining unused-import or unused-local findings in touched Python code
- Command: `pnpm dlx knip --reporter compact`
- Expected evidence: removed files no longer appear in the dead-code report
- Command: targeted `pytest` and gateway package tests for touched surfaces
- Expected evidence: touched runtime and gateway paths still pass
- Command: `pytest tests/unit/test_repo_os_structure.py -v && zsh scripts/check`
- Expected evidence: repo-OS checks stay green after adding the task file

## Notes

Initial scans showed a mix of true dead code and compatibility placeholders. This task removed the high-confidence subset only.

Remaining tool findings after cleanup:
- `vulture` still reports `dao/reminder_dao.py:find_pending_reminders(time_window=...)` and `dao/user_dao.py` placeholder parameters because they are retained for signature compatibility.
- `knip` still reports several API scripts, exported types, and package dependencies that need a separate pass because they may still be operator entrypoints or external contracts.
