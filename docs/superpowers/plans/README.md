# Execution Plans

This directory is the canonical home for execution plans in `coke` — both
active and archived. It matches the `superpowers:writing-plans` skill default
path. See `docs/adr/0003-consolidate-plans-to-superpowers.md` for the
consolidation history (the predecessor `docs/exec-plans/` was retired and its
contents merged here on 2026-05-09).

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

1. Drafted
2. Active
3. Verified
4. Archived or superseded

## Freshness

Plans accumulate over time; not every file here is current. Before relying on
any plan, verify it against current `main`, `docs/architecture.md`, and the
touched code.

## Template

Use [`_template.md`](./_template.md) for ad-hoc plans. For
`superpowers:writing-plans`-driven work, follow the skill's required header
and TDD task format instead.
