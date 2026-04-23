# Task: User Timezone System Design

- Status: Complete
- Owner: Codex
- Date: 2026-04-23

## Goal

Write the approved product spec for Coke's account-level timezone system across
WhatsApp, web, and future app surfaces.

## Scope

- In scope:
  - Canonical timezone model and ownership rules
  - Default timezone inference at registration or first account creation
  - User-driven timezone changes and confirmation rules
  - Time parsing and reminder behavior when timezone changes
  - Chat-side minimum management UX for timezone visibility and updates
- Out of scope:
  - Detailed implementation plan
  - Schema migration or code changes
  - Final web settings UI design

## Touched Surfaces

- repo-os

## Acceptance Criteria

- The spec defines one global user timezone shared across channels.
- The spec distinguishes system-inferred timezone from user-confirmed timezone.
- The spec defines source priority, confirmation rules, and ambiguity handling.
- The spec defines how reminders and time parsing behave when timezone changes.
- The spec is saved under `docs/superpowers/specs/` using the repo naming
  convention.

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Expected evidence: repo-OS structure tests still pass after adding the task
  and spec files.
- Command: `zsh scripts/check`
- Expected evidence: repository structure and routing checks pass.

## Notes

- This task writes the final design spec only.
- The implementation plan should be written later in a separate step.
