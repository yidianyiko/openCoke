# Execution Plans

This directory holds active and archived implementation plans for new
multi-step work in `coke`.

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

## Relationship To `docs/superpowers/plans/`

`docs/superpowers/plans/` remains a valid record of historical and transitional
plans created before this canonical directory existed. New repository-wide
plans should default to `docs/exec-plans/` unless a specific subsystem still
requires the legacy location.

## Template

Use [`_template.md`](./_template.md) for new plans.
