# Shared Reminder False Success Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent shared-reminder retry turns from confirming creation or duplicate-active existence unless a durable active shared reminder backs the claim.

**Architecture:** Keep the fix structural. The social-scheduling service remains active-row based for duplicate detection; the close-boundary output guard rejects missing or unbacked active outcomes.

**Tech Stack:** Python, pytest, Coke TurnRunner, OutputProtocolValidator, SocialSchedulingService.

---

**Plan Status:** verified
**Status Date:** 2026-06-07
**Freshness Check:** Verified against current `docs/ARCHITECTURE.md`, `docs/superpowers/specs/2026-06-07-response-contract-recovery-design.md`, and touched code before execution.

### Task 1: RED regressions

**Files:**
- Modify: `tests/unit/coke/turn/test_output_protocol.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`

- [x] Add an output-protocol regression that rejects `duplicate_active` without `shared_reminder_id`.
- [x] Add a TurnRunner regression for failed staged create followed by duplicate-language retry with no active shared reminder; expect failed close, no delivery, and no shared-reminder row.
- [x] Add a legitimate duplicate-active regression with an existing active shared reminder id; expect reply allowed.
- [x] Run the new tests and confirm they fail for the expected contract gap.

### Task 2: Structural guard

**Files:**
- Modify: `coke/turn/output_protocol.py`
- Modify: `coke/turn/runner.py`
- Modify tests that asserted now-invalid no-tool social-scheduling closes.

- [x] Require `created_active` and `duplicate_active` outcomes to carry `shared_reminder_id`.
- [x] Let the runner pass an active shared-reminder existence check from `SocialSchedulingService`.
- [x] Require social-scheduling create-intent replies with enabled social tools to bind to a social-scheduling outcome.
- [x] Keep clarification-only turns exempt because they are constrained no-tool question turns.
- [x] Run targeted tests and confirm green.

### Task 3: Verification and closeout

**Files:**
- Update: `docs/issues/2026-06-07-shared-reminder-false-success.md`
- Update: `docs/superpowers/plans/2026-06-07-shared-reminder-false-success.md`

- [x] Run new tests.
- [x] Run `.venv/bin/python -m pytest tests/unit/coke -q`.
- [x] Run `zsh scripts/suggest-verification --base HEAD~1` and the suggested surface.
- [x] Run `zsh scripts/review-trigger --base HEAD~1`.
- [x] Update issue and plan status with verification evidence.
- [x] Commit on `fix/shared-reminder-false-success`.

## Verification Evidence

- Targeted regression tests: 5 passed in 2.59s.
- Full unit suite: 819 passed in 21.51s.
- Suggested surface: `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`
  passed with backend 819 passed in 19.66s and `scripts/check` passed.
- Risk report: `human_review_required: no`; medium non-blocking repo-OS and
  evidence-gap triggers reported.
