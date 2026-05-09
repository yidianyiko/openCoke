# Execution Plans

This directory is the canonical home for execution plans in `coke`. It stays
flat on purpose because the `superpowers:writing-plans` skill saves plans to:

`docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`

Do not create lifecycle subdirectories such as `active/`, `completed/`, or
`archived/` under this path. See
`docs/adr/0003-consolidate-plans-to-superpowers.md` for the consolidation
history (the predecessor `docs/exec-plans/` was retired and its contents
merged here on 2026-05-09).

## Purpose

Execution plans translate a task into concrete, reviewable steps so a new agent
or human can continue without reconstructing the whole problem from memory.

## When To Write A Plan

Write a plan when work is:

- multi-step
- risky
- cross-cutting
- likely to span multiple sessions
- likely to involve more than one worktree or role

Small isolated edits do not need a formal plan.

## Naming

Use:

`YYYY-MM-DD-short-topic.md`

## Lifecycle

Lifecycle is file metadata, not directory placement.

For ad-hoc plans, include this block near the top:

```md
**Plan Status:** draft | active | verified | completed | superseded
**Status Date:** YYYY-MM-DD
**Freshness Check:** Verify against current `main`, `docs/ARCHITECTURE.md`,
and touched code before execution.
```

For `superpowers:writing-plans` output, preserve the skill-required header
exactly. Add the status block immediately after the required header separator
(`---`) or in the first handoff/status update after the plan is created.

When a plan ships or is abandoned, update `Plan Status` instead of moving it to
a lifecycle directory.

## Freshness

Plans accumulate over time; not every file here is current. Before relying on
any plan, verify it against current `main`, `docs/ARCHITECTURE.md`, and the
touched code.

## Template

Use [`_template.md`](./_template.md) for ad-hoc plans. For
`superpowers:writing-plans`-driven work, follow the skill's required header
and TDD task format instead.
