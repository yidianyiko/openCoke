# Design Docs Index

This directory is the canonical home for durable repository-level workflow
intent in `coke`.

Use these documents for rules that should stay true across many tasks and many
sessions.

## Canonical Documents

- [`human-ai-working-contract.md`](./human-ai-working-contract.md): critical
  collaboration rules for humans and AI agents, including repository beliefs,
  documentation rules, delivery rules, verification trust levels, and test
  skepticism.
- [`coke-working-contract.md`](./coke-working-contract.md): the Coke-specific
  work surfaces and planning contract.
- [`agent-capability-contract.md`](./agent-capability-contract.md): the design
  rule for agent-facing external capability contracts and their adapters.
- [`interface-contract.md`](./interface-contract.md): the canonical public and
  internal route namespace contract.
- [`data-retention-policy.md`](./data-retention-policy.md): retention policy
  identifiers, default durations, cleanup owners, and deletion evidence rules.
- [`channel-field-inventory.md`](./channel-field-inventory.md): frontend-safe
  and backend-only Channel field classification.
- [`agent-trace-feedback-loop.md`](./agent-trace-feedback-loop.md): durable
  loop for turning `AgentTurnTrace` evidence into routing, prompt,
  tool-interface, and runtime improvements.

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
- [`../issues/`](../issues/README.md): local issue, incident, runbook, and
  investigation records.
- [`../product-specs/FEATURE_TREE.md`](../product-specs/FEATURE_TREE.md):
  product, route, and API surface index.
- [`../../artifacts/evidence/`](../../artifacts/evidence/): generated
  verification and eval evidence.

## Domain And History Docs

These paths stay important, but they are not the home for repository-level
rules:

- [`../roadmap.md`](../roadmap.md): product and platform direction.
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md): canonical runtime topology and
  boundaries wired in code.
- [`../deploy.md`](../deploy.md): detailed deployment and operational steps.
- [`../clawscale_bridge.md`](../clawscale_bridge.md): bridge and personal
  channel rollout notes.
- [`../release-guide.md`](../release-guide.md): release and rollout workflow.
- [`../RELEASE_CHECKLIST.md`](../RELEASE_CHECKLIST.md): release closeout
  checklist.

## Writing Rule

If a rule should outlive the current task, put it here or in an ADR instead of
leaving it only in chat, a plan file, or a one-off note.
