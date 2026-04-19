# ClawScale Platformization Orchestration

## Purpose

This document is the control-plane summary for the ClawScale platformization follow-up work.
It exists for a supervising AI or human operator that needs one place to answer:

- which plan depends on which other plan
- what has already been implemented
- what can run in parallel
- which worktree should own each unfinished plan

This document is intentionally not a replacement for the plan files. It sits above them and
defines execution order and current status.

This document tracks the state of the current local checkout as of `2026-04-18`.
When this document says `main`, it means the local branch in this repository checkout, not
necessarily `origin/main`.

## Source Plans

- Plan 1: `docs/superpowers/plans/2026-04-16-clawscale-identity-schema-migration-plan.md`
- Plan 1a: `docs/superpowers/plans/2026-04-16-clawscale-stranded-model-resolution-plan.md`
- Plan 2: `docs/superpowers/plans/2026-04-16-clawscale-auth-ownership-migration-plan.md`
- Plan 4: `docs/superpowers/plans/2026-04-16-clawscale-customer-frontend-relocation-plan.md`
- Plan 5: `docs/superpowers/plans/2026-04-16-clawscale-admin-backend-mvp-plan.md`
- Plan 7: `docs/superpowers/plans/2026-04-16-clawscale-shared-channel-auto-provisioning-runtime-plan.md`
- Plan 3: `docs/superpowers/plans/2026-04-16-coke-auth-collection-retirement-plan.md`
- Plan 6: `docs/superpowers/plans/2026-04-16-clawscale-dashboard-deprecation-plan.md`

The umbrella spec is:

- `docs/superpowers/specs/2026-04-15-clawscale-platformization-design.md`

## Status Legend

- `completed-local-main`: implementation has been merged into the current local `main`
- `in-progress`: worktree exists and implementation is underway but not yet merged
- `not-started`: plan exists but no active implementation should be assumed

`completed-local-main` does not imply the work has been pushed to `origin/main`.

## Tracking Legend

- `tracked`: the referenced plan/spec file is already tracked by Git in the current local `main`
- `local-untracked`: the referenced plan/spec file exists only as an untracked local file in the
  current checkout

Implementation state and document tracking state are different things.
Code may already be merged into local `main` even if the plan/spec Markdown file itself is still
`local-untracked`.

## Direct Dependencies

The hard direct dependencies are:

- Plan 1: no direct dependency
- Plan 1a: depends on Plan 1
- Plan 2: depends on Plan 1 and Plan 1a
- Plan 4: depends on Plan 2
- Plan 5: depends on Plan 2
- Plan 7: depends on Plan 2, Plan 4, and Plan 5
- Plan 3: depends on Plan 2 and Plan 7
- Plan 6: depends on Plan 5

These are direct dependencies only, not the full transitive closure.

## Recommended Execution Order

The recommended execution order is:

`1 -> 1a -> 2 -> (4 || 5) -> 7 -> 3 -> 6`

Interpretation:

- Plan 2 must land before any new parallel wave starts.
- Plans 4 and 5 may run in parallel, but only after Plan 2 has merged to local `main`.
- Plan 7 should not start before both Plans 4 and 5 have landed.
- Plan 3 is destructive retirement work and should not start before Plan 7 lands.
- Plan 6 is final cleanup and should be the last plan in the sequence.

## Current Implementation Status

| Plan | File | Implementation status | Local `main` merge state | File tracking state | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | `2026-04-16-clawscale-identity-schema-migration-plan.md` | `completed-local-main` | Implemented and already represented in the current local `main` through the current `gateway/main` lineage | `tracked` | The implementation is in local `main`, and this plan file is now tracked for controller visibility. |
| 1a | `2026-04-16-clawscale-stranded-model-resolution-plan.md` | `completed-local-main` | Merged into the current local `main` | `tracked` | Both the implementation and the plan file are in the current local `main`. |
| 2 | `2026-04-16-clawscale-auth-ownership-migration-plan.md` | `completed-local-main` | Merged into the current local `main` at `8e03dde` | `tracked` | Gateway task 5 landed at `f733ecf`; the outer repo merged the completed worktree back into local `main`. |
| 4 | `2026-04-16-clawscale-customer-frontend-relocation-plan.md` | `completed-local-main` | Merged into the current local `main` at `ebe7828` | `tracked` | Gateway frontend relocation now rides the local `gateway/main` lineage at `34319b1`; the outer repo merged the completed worktree back into local `main`. |
| 5 | `2026-04-16-clawscale-admin-backend-mvp-plan.md` | `completed-local-main` | Merged into the current local `main` at `dc90a50` | `tracked` | Admin backend + frontend MVP is merged into local `main`; its gateway lineage is also present in local `gateway/main` at `34319b1`. |
| 7 | `2026-04-16-clawscale-shared-channel-auto-provisioning-runtime-plan.md` | `completed-local-main` | Merged into the current local `main` at `24e5bc7` | `tracked` | Shared-channel runtime is merged into local `main`; its gateway lineage is present in local `gateway/main` at `925e981`. The plan closeout note still records manual disposable-environment verification as an explicit exclusion. |
| 3 | `2026-04-16-coke-auth-collection-retirement-plan.md` | `not-started` | No local merge yet | `tracked` | Destructive cutover plan. Must wait for Plans 2 and 7. |
| 6 | `2026-04-16-clawscale-dashboard-deprecation-plan.md` | `not-started` | No local merge yet | `tracked` | Cleanup plan. Must wait for Plan 5. |

## Spec and Plan File Caveats

The platformization spec, Plan 1 Markdown file, and this orchestration document are intended to be
tracked together so a supervising agent can reason from repository state instead of local-only
files.

Implementation state and document history still remain different concepts.
Even after these Markdown files are tracked, `completed-local-main` only means the implementation
has landed in the current local `main`; it still does not imply the work has been pushed to
`origin/main`.

## Existing and Planned Worktrees

### Completed-plan worktrees

- Plan 1 implementation lineage: `.worktrees/platformization-schema-migration`
- Plan 1a implementation lineage: `.worktrees/stranded-model-resolution`
- Plan 2 implementation lineage: `.worktrees/auth-ownership-migration`
- Plan 4 implementation lineage: `.worktrees/customer-frontend-relocation`
- Plan 5 implementation lineage: `.worktrees/admin-backend-mvp`
- Plan 7 implementation lineage: `.worktrees/shared-channel-runtime`

These worktrees may still exist locally for inspection, but their outputs are already merged into
the current local `main`.

### Active unfinished-plan worktrees

There is no active unfinished-plan worktree at this moment.

### Recommended future worktree mapping

- Plan 3: `.worktrees/coke-auth-retirement`
- Plan 6: `.worktrees/dashboard-deprecation`

## Controller Rules

The supervising AI should follow these rules:

1. One unfinished plan per worktree.
2. Do not open a dependent plan from `origin/main`; branch it from the current local `main`.
3. Merge a completed prerequisite back into local `main` before starting its dependents.
4. Only Plans 4 and 5 are allowed to run in parallel under the current dependency graph.
5. Before merge, each worktree must run the verification commands listed in its own plan file.
6. After rebasing onto the latest local `main`, each worktree must rerun its verification.
7. If implementation discovers a missing contract or plan contradiction, update the affected plan
   or this orchestration document before continuing.

## Immediate Next Action

The next plan to execute is:

- Plan 6: `docs/superpowers/plans/2026-04-16-clawscale-dashboard-deprecation-plan.md`

Plans 3, 4, 5, and 7 are merged. Plan 6 is now the last remaining dependency-safe step from the current local `main`.
