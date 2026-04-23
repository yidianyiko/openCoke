# Task: User Timezone System Implementation

- Status: Completed
- Owner: Codex
- Date: 2026-04-23

## Goal

Implement the first production slice of Coke's account-level timezone system in
the `spec-timezone-feature-design` worktree.

## Scope

- In scope:
  - Canonical account timezone state in Mongo business settings
  - First-touch inferred timezone resolution for current runtime entry points
  - User-explicit timezone changes and system-signal confirmation flow
  - Prompt/runtime visibility of inferred vs confirmed timezone state
  - Reminder semantics split between floating local time and absolute delay
- Out of scope:
  - New web settings UI
  - Native app client timezone producers
  - Full gateway UX for external timezone-signal capture

## Touched Surfaces

- worker-runtime
- repo-os

## Acceptance Criteria

- Current runtime reads one canonical account-level timezone state instead of a
  bare timezone string.
- Messaging-first users can receive an inferred default timezone on first touch.
- Direct user timezone changes apply immediately when unambiguous.
- Non-user timezone changes require immediate confirmation and only consume
  replies from the originating conversation.
- Reminder parsing distinguishes floating local-time tasks from absolute-delay
  tasks.

## Verification

- Command: `pytest tests/unit/test_user_dao_timezone.py tests/unit/agent/test_timezone_service.py tests/unit/runner/test_identity.py tests/unit/test_context_timezone.py tests/unit/test_prepare_workflow_timezone.py tests/unit/test_timezone_tools.py tests/unit/test_tool_results_context.py tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_visible_reminder_time_parser.py -v`
- Evidence: `72 passed`
- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Evidence: `4 passed`
- Command: `zsh scripts/check`
- Evidence: `check passed`

## Notes

- Plan lives in `docs/exec-plans/2026-04-23-user-timezone-system.md`.
- Execution is expected to use subagent-driven development in this worktree.
- Final implementation head: `5f940df7154cc18e5a38de44c1d6714aa6c4b3b0`
