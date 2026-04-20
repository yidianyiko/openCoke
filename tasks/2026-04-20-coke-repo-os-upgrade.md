# Task: Establish Coke Repo OS Skeleton

- Status: Verified
- Owner: Codex
- Date: 2026-04-20

## Goal

Add the first canonical repo-OS structure to Coke without breaking the existing
runtime docs, `docs/superpowers` artifacts, or active development flow.

## Scope

- In scope:
  - add canonical repository-level homes for design docs, ADRs, execution
    plans, fitness rules, and task-local state
  - add a repository structure verification entrypoint
  - update root routing docs so new agents know where durable workflow knowledge
    belongs
  - define how the new canonical structure relates to existing
    `docs/superpowers/{specs,plans}` artifacts
- Out of scope:
  - migrating all historical `docs/superpowers` artifacts into the new
    directories
  - changing Coke runtime behavior
  - replacing existing product, deployment, or platform docs

## Acceptance Criteria

- Coke has canonical directories for design docs, ADRs, execution plans,
  fitness, and tasks.
- `AGENTS.md`, `CLAUDE.md`, and `README.md` route readers to the new structure.
- `scripts/check` validates the repo-OS skeleton.
- A focused automated test proves the new structure and check entrypoint are in
  place.

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Command: `zsh scripts/check`
- Expected evidence: the targeted test passes and `scripts/check` reports
  `check passed`.

## Notes

This task is the bootstrap layer for future Coke work. It must preserve the
current `docs/superpowers` history and clarify that those files remain valid
historical design and plan artifacts during the transition.

Verified on 2026-04-20 with:

- `pytest tests/unit/test_repo_os_structure.py -v`
- `zsh scripts/check`
