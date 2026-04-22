# Task: User Timezone System Implementation

- Status: In Progress
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

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Expected evidence: repo-OS structure tests still pass with the plan/task docs.
- Command: `zsh scripts/check`
- Expected evidence: repository structure and routing checks pass.

## Notes

- Plan lives in `docs/exec-plans/2026-04-23-user-timezone-system.md`.
- Execution is expected to use subagent-driven development in this worktree.
