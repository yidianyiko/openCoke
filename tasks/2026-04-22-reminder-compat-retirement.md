# Task: Retire Legacy Reminder Compatibility

- Status: Completed
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

- Command: `pytest tests/unit/test_context_timezone.py tests/unit/runner/test_background_handler_deferred_only.py tests/unit/dao/test_user_dao_auth_retirement_audit.py tests/unit/connector/clawscale_bridge/test_verify_auth_retirement.py tests/unit/scripts/test_retire_legacy_reminder_compat.py tests/unit/test_repo_os_structure.py -v`
- Command: `pnpm --dir gateway/packages/api exec vitest run src/scripts/audit-customer-id-parity.test.ts`
- Command: `python3 scripts/retire_legacy_reminder_compat.py --help`
- Command: `zsh scripts/check`

## Notes

- Final state is now documented: `deferred_actions` owns reminder and proactive
  scheduling, no live runtime depends on `conversation_info.future`, and
  `scripts/retire_legacy_reminder_compat.py` is the cleanup path for retiring
  legacy compatibility data.
- Historical plan/spec docs retain their original design intent but now carry
  concise status notes so they no longer read like open migration work.
