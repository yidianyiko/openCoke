# ADR 0001: Adopt A Canonical Repo OS Structure

- Status: Accepted
- Date: 2026-04-20

## Context

By April 2026, `coke` had accumulated substantial execution history in
`docs/superpowers/specs/`, `docs/superpowers/plans/`, and the platformization
orchestration notes. The repository already contained strong design and
delivery signal, but it lacked a small canonical control layer for:

- repository-level beliefs and rules
- durable workflow decisions
- task-local work state
- new execution plans
- repository-structure verification

As a result, `AGENTS.md` and `CLAUDE.md` had started mixing routing,
development notes, and detailed operational guidance. New agents could find the
runtime docs, but not a clear answer to where new workflow knowledge belonged.

## Decision

Adopt a canonical repository operating-system skeleton in `coke`:

- `docs/design-docs/` for repository-level beliefs and rules
- `docs/adr/` for durable workflow and structure decisions
- `docs/exec-plans/` for new execution plans
- `docs/fitness/` for verification rules
- `tasks/` for task-local work state
- `scripts/check` as the repository-level structure verification entrypoint

At the same time:

- keep `AGENTS.md` as a routing layer
- keep `docs/roadmap.md`, `docs/architecture.md`, `docs/deploy.md`, and
  `docs/clawscale_bridge.md` as the authoritative product/runtime documents
- keep `docs/superpowers/specs/` and `docs/superpowers/plans/` as valid dated
  design and implementation history instead of mass-moving them in the same
  change

## Consequences

- New non-trivial work now has canonical homes for tasks, plans, and workflow
  rules.
- Root routing docs can stay shorter and more stable.
- The repository temporarily carries both new canonical directories and older
  `docs/superpowers` history; that is intentional.
- A later migration may move or archive selected `docs/superpowers` artifacts,
  but only with a dedicated task and explicit mapping.
