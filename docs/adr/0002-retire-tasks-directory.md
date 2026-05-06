# ADR 0002: Retire The Tasks Directory

- Status: Accepted
- Date: 2026-05-06

## Context

The original repo-OS skeleton used `tasks/` for task-local work state. In
practice, that directory accumulated historical notes and generated evidence in
the same namespace. The result made the repository harder to scan and created a
risk that agents would treat stale task notes as current product or runtime
truth.

The repository already has better durable homes:

- `docs/adr/` for long-lived decisions
- `docs/exec-plans/` and `docs/superpowers/plans/` for implementation plans
- `docs/superpowers/specs/` for dated design artifacts
- `artifacts/evidence/` for generated verification and eval output

## Decision

Retire `tasks/` as a canonical repo-OS directory.

Use these homes instead:

- Durable decisions: `docs/adr/`
- New execution plans: `docs/exec-plans/`
- Existing Superpowers plans and specs: `docs/superpowers/`
- Generated verification evidence: `artifacts/evidence/`

Repo-OS checks and guardrails should no longer require a task file for
non-trivial work. Review-trigger evidence checks should look for generated
evidence under `artifacts/evidence/`.

## Consequences

- The repository loses a noisy task-local history surface.
- New agents have fewer places to search before finding the current operating
  contract.
- Generated eval evidence remains available without mixing with planning notes.
- Historical references to deleted task files in dated plans are treated as
  historical context, not active links.
