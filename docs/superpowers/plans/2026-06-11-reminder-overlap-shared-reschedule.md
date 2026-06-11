---
kind: plan
status: active
topic: reminder overlap and shared reminder reschedule
date: 2026-06-11
spec: docs/superpowers/specs/2026-06-11-reminder-overlap-shared-reschedule-design.md
---

# Reminder Overlap And Shared Reschedule

## Goal

Implement the smallest product change needed for the v6 gaps:

- personal timed reminders/self-schedule entries reject overlapping active
  calendar-visible intervals before any write or staged success;
- active shared reminders can be rescheduled in place, preserving the existing
  shared reminder identity and participant projections.

## Scope

In scope:

- personal create/update/reschedule conflict checks for timed intervals;
- turn-v2 preflight so conflict replies are normal `time_conflict` outcomes, not
  close-time materialization failures;
- `update_shared_reminder` for time and duration only;
- shared reschedule conflict checks that exclude the current shared reminder and
  its projection reminder rows;
- projection reminder sync for the successful shared reschedule path;
- targeted docs and v6 smoke expectation updates.

Out of scope:

- shared title/content editing;
- automatic alternate-time suggestions;
- changing the 15-minute default duration;
- API/web management UI changes;
- schema migrations unless tests prove the existing repository shape cannot
  support the update correctly.

## Execution

1. Add failing tests for personal overlap:
   - domain service create blocks overlap and writes no reminder;
   - v2 reminder handler returns a conflict outcome before staging;
   - update/reschedule excludes the target reminder but blocks other overlaps.
2. Add failing tests for shared reschedule:
   - service updates one shared reminder id and all projection reminder rows;
   - reschedule into a participant conflict leaves old rows unchanged;
   - self-exclusion prevents the current shared interval from blocking itself;
   - v2 social handler resolves and stages only successful updates.
3. Implement the minimal domain changes:
   - reusable interval overlap helpers;
   - repository support for syncing projection reminder rows;
   - social outcome/status facts for rescheduled vs conflict/no-op.
4. Wire turn and model surfaces:
   - `PARAM_KEY_SCHEMA`, planner action set, social handler dispatch;
   - Agno tool instructions and semantic action vocabulary;
   - v6 smoke cases and assertion vocabulary.
5. Update canonical product docs where they currently say shared reminders must
   be cancelled and recreated to change time.
6. Verify:
   - targeted unit tests first;
   - `zsh scripts/suggest-verification --base HEAD~1`;
   - `zsh scripts/review-trigger --base HEAD~1`;
   - suggested backend surface;
   - deploy to GCP;
   - real WeChat smoke for D3/E5/E6 one message at a time with DB row-effect
     assertions and cleanup.

## Acceptance

- D3 behavior becomes conflict/no-write instead of expected gap.
- E5 behavior becomes update existing shared reminder instead of cancel/create.
- E6 behavior becomes conflict/no-write with the old shared reminder still
  active at its previous time.
- Production deployment contains the implementation commit and real WeChat smoke
  evidence.
