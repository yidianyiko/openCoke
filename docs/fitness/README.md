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
   - execution plan exists when the work is multi-step or risky
   - canonical docs were updated when workflow rules changed
   - generated evidence uses the `artifacts/evidence/` path

3. **Implementation checks**
   - unit tests
   - integration or E2E tests
   - lint/format/build
   - operational smoke checks when deployment surfaces changed

4. **Risk reporting**
   - diff inspected
   - assumptions called out
   - remaining risks stated

## Repository Default

For repository-structure and workflow-document changes, the minimum entrypoint
is:

- [`../../scripts/check`](../../scripts/check)

## Human Verification Checklist

Use this checklist when a task spans workflow docs, repository structure, and
runtime behavior:

- Structure: required files exist, canonical paths are valid, root routing docs
  point to the canonical locations, and `scripts/check` passes.
- Workflow: execution plans exist when the work is multi-step or risky,
  canonical docs were updated for workflow changes, and generated evidence is
  stored under `artifacts/evidence/`.
- Runtime: run the relevant targeted tests for touched code, run broader smoke
  or deployment verification when required, and record any intentionally
  unverified areas.
- Risk reporting: inspect the diff, note assumptions and remaining risks, and
  avoid claiming success without command evidence.

Use [`coke-verification-matrix.md`](./coke-verification-matrix.md) when you
need the repository-specific command mapping for worker, bridge, gateway, or
deploy changes. For docs-only repo-OS edits, prefer the `repo-os-docs` surface;
it keeps verification to structure/routing checks. Use the heavier `repo-os`
surface for guardrail scripts, `surfaces.yaml`, or verification tooling.

## Coke Guardrails

`surfaces.yaml` is the machine-readable surface and risk-trigger contract. It
keeps the Coke-specific boundaries close to the human-readable verification
matrix without replacing the existing command runner.

## Ownership Registry

`docs/fitness/ownership-registry.yaml` maps route and contract files to the
ownership systems defined in
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.
It complements planning surfaces; it does not replace `surfaces.yaml`.

Use these helpers from the repository root:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- `suggest-verification` maps changed files to Coke surfaces and prints the
  matching `scripts/verify-surface` dry-run command set.
- `review-trigger` reports risk triggers such as bridge/gateway cross-boundary
  changes, deployment changes, oversized diffs, or non-trivial changes without
  generated evidence. It is non-blocking, exits 0, and never requires human
  review.
