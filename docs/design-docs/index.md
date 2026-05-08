# Design Docs Index

This directory is the canonical home for durable repository-level workflow
intent in `coke`.

Use these documents for rules that should stay true across many tasks and many
sessions.

## Canonical Documents

- [`core-beliefs.md`](./core-beliefs.md): the operating beliefs behind the
  repository control layer.
- [`golden-rules.md`](./golden-rules.md): day-to-day rules for documentation,
  delivery, and verification.
- [`human-ai-working-contract.md`](./human-ai-working-contract.md): critical
  collaboration rules for humans and AI agents, including verification trust
  levels and test skepticism.
- [`coke-working-contract.md`](./coke-working-contract.md): the Coke-specific
  work surfaces and planning contract.
- [`interface-contract.md`](./interface-contract.md): the canonical public and
  internal route namespace contract.

## Canonical Neighbors

These locations are also part of the repository operating system, but they
store different kinds of knowledge:

- [`../adr/`](../adr/README.md): durable workflow and structure decisions.
- [`../superpowers/plans/`](../superpowers/plans/README.md): canonical home
  for multi-step execution plans (active and dated). Matches the
  `superpowers:writing-plans` skill default.
- [`../superpowers/specs/`](../superpowers/specs/): canonical home for
  design specs (active and dated).
- [`../fitness/`](../fitness/README.md): verification rules and evidence model.
- [`../../artifacts/evidence/`](../../artifacts/evidence/): generated
  verification and eval evidence.

## Domain And History Docs

These paths stay important, but they are not the home for repository-level
rules:

- [`../roadmap.md`](../roadmap.md): product and platform direction.
- [`../architecture.md`](../architecture.md): runtime topology wired in code.
- [`../deploy.md`](../deploy.md): detailed deployment and operational steps.
- [`../clawscale_bridge.md`](../clawscale_bridge.md): bridge and personal
  channel rollout notes.

## Writing Rule

If a rule should outlive the current task, put it here or in an ADR instead of
leaving it only in chat, a plan file, or a one-off note.
