---
kind: progress_note
status: completed
surface:
  - product-requirements
  - conversation-runtime
  - reminder
  - interaction-agent
created_at: 2026-05-31
updated_at: 2026-05-31
---

# Legacy Capability Gap Analysis

## Purpose

This note records legacy-comparison evidence and implementation decisions. It is
not a product requirements source. Current requirements live in
`docs/product-requirements/current.md`.

## Decision For This Pass

Implement only these two gaps now:

- Segmented visible replies must be delivered as separate ordered messages on
  message-style channels.
- Reminder lookup and mutation must support natural-language keyword resolution
  plus keyword, status, type, and trigger-time filters.

Do not implement the other legacy-only surfaces from this comparison in this
pass.

## Evidence

- Legacy prompt guidance used multiple `MultiModalResponse` text entries as
  message segmentation, usually one to three short messages, and legacy sending
  streamed each response item as an individual outbound message. Current Coke
  already accepts 1-3 output segments, but `TurnRunner` currently joins them
  with `\n` into one delivery request.
- Legacy reminder tooling accepted keyword-based update/delete/filter/complete
  actions and filter fields for status, reminder type, keyword,
  `trigger_after`, and `trigger_before`. Current Coke supports id-based
  update/delete/complete and active-list reads, but does not yet provide the
  same natural-language filter and safe keyword resolution path.

## Requirement Boundary

The product requirement is not "copy legacy." The normalized requirements are:

- Users receiving a segmented Coke text reply in a message-style channel should
  see separate ordered messages, not one merged message with newline separators.
- Users should be able to find reminders by keyword, status, type, and
  trigger-time range through conversation.
- Users should be able to edit, complete, or delete a reminder by keyword only
  when the target is unambiguous. Ambiguous matches must ask for clarification
  before state changes.

## Explicit Non-Goals For This Pass

- No legacy `*` delete-all shortcut.
- No bulk destructive keyword mutation when multiple reminders match.
- No media input/output expansion.
- No legacy role busy/hold behavior, relationship-score behavior, admin command
  surface, URL reader, web search, photo album, or Moments feature.

## Current Status

Completed in this pass:

- Product requirements moved to `docs/product-requirements/current.md`.
- Runtime architecture updated for per-segment visible delivery semantics.
- Segmented reply delivery now emits one ordered delivery request per visible
  reply segment.
- Reminder list/filter and keyword mutation support owner-scoped keyword,
  lifecycle/status, kind/type, and trigger-time filters; keyword mutation only
  proceeds for one unambiguous active user-mutable reminder.
- Interaction Agent prompt guidance now includes short message-channel segments,
  no generic customer-service openings/closers, and no ordinary final full stop
  for final statement segments.

Verification:

- `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_interaction_agent.py -q`
- `git diff --check`
- `zsh scripts/check`
- `zsh scripts/suggest-verification --base HEAD~1`
- `zsh scripts/review-trigger --base HEAD~1`
- `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`
