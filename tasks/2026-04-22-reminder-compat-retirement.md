# Task: Retire Legacy Reminder Compatibility

- Status: Active
- Owner: Codex
- Date: 2026-04-22

## Goal

Remove every remaining legacy reminder/future compatibility surface so `deferred_actions` is the only reminder runtime and data model.

## Scope

- In scope:
  - Remove `conversation_info.future` compatibility fields from runtime code and fixtures
  - Replace legacy `reminders` collection audits with `deferred_actions`
  - Add a one-time cleanup path for live Mongo data
  - Delete or trim outdated docs and descriptions that still imply legacy compatibility
- Out of scope:
  - Redesigning deferred-action behavior
  - Broad documentation cleanup unrelated to reminder compatibility retirement

## Touched Surfaces

- worker-runtime
- gateway-api
- repo-os

## Acceptance Criteria

- No runtime path creates, normalizes, or depends on `conversation_info.future`
- No active audit/script/test path treats Mongo `reminders` as the live reminder collection
- A repeatable cleanup path exists for unsetting legacy conversation fields and retiring the old `reminders` collection from live Mongo
- Canonical docs describe `deferred_actions` as the only live reminder runtime

## Verification

- Command: `pytest tests/unit/test_context_timezone.py tests/unit/runner/test_background_handler_deferred_only.py tests/unit/dao/test_user_dao_auth_retirement_audit.py tests/unit/test_repo_os_structure.py -v`
- Expected evidence: all selected Python tests pass with no failures
- Command: `pnpm --dir gateway/packages/api test -- --run src/scripts/audit-customer-id-parity.test.ts`
- Expected evidence: target Vitest passes

## Notes

Implementation runs in worktree `compat-retirement-reminders` and will be merged back to local `main` after verification.
