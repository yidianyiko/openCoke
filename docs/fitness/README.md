# Fitness Rulebook

This directory defines what evidence counts as verification in `coke`.

## Core Rule

Do not claim work is complete without fresh verification evidence.

## Verification Layers

Use the smallest useful layer for the task:

1. **Structure checks**
   - canonical files exist
   - routing docs point to the right places
   - templates are present

2. **Workflow checks**
   - task artifact exists when work is non-trivial
   - execution plan exists when the work is multi-step or risky
   - canonical docs were updated when workflow rules changed

3. **Implementation checks**
   - unit tests
   - integration or E2E tests
   - lint/format/build
   - operational smoke checks when deployment surfaces changed

4. **Review checks**
   - diff reviewed
   - assumptions called out
   - remaining risks stated

## Repository Default

For repository-structure and workflow-document changes, the minimum entrypoint
is:

- [`../../scripts/check`](../../scripts/check)

Use [`verification-checklist.md`](./verification-checklist.md) when a task
needs a human-readable evidence list.

Use [`coke-verification-matrix.md`](./coke-verification-matrix.md) when you
need the repository-specific command mapping for worker, bridge, gateway, or
deploy changes.

## Coke Guardrails

`surfaces.yaml` is the machine-readable surface and review-trigger contract.
It keeps the Coke-specific boundaries close to the human-readable verification
matrix without replacing the existing command runner.

Use these helpers from the repository root:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- `suggest-verification` maps changed files to Coke surfaces and prints the
  matching `scripts/verify-surface` dry-run command set.
- `review-trigger` flags changes that should receive human review, such as
  bridge/gateway cross-boundary changes, deployment changes, oversized diffs,
  or non-trivial changes without `tasks/` evidence.
