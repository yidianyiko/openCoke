# Human-AI Working Contract

This repository should be usable by humans and AI agents without relying on
private chat memory. The goal is not to make agents more confident; it is to
make their work easier to inspect, constrain, and verify.

## Operating Principles

1. Treat repository state as the authority, but treat every authority as
   fallible until it is checked against code and runtime behavior.
2. Prefer explicit boundaries over implicit ownership. A task should name the
   surfaces it touches before it claims verification is complete.
3. Do not optimize for green tests alone. A passing test suite can still be
   wrong when the test asserts stale behavior, mocks the wrong boundary, or
   skips the runtime path that matters.
4. Keep human judgment in the loop for architecture, product contract,
   deployment, evidence deletion, oversized diffs, and cross-boundary changes.
5. Preserve the product contract even when a test or eval is red. Do not add
   case-specific branches, parser shortcuts, compatibility fallbacks, or prompt
   examples just to satisfy a single gate.

## Required Work Shape

Every non-trivial task should leave these questions answerable from the repo:

- What surface changed?
- What behavior or contract changed?
- What evidence proves the change?
- What was intentionally not verified?
- Did the verification command exercise the real path or only a mock/stub?

For multi-step or risky work, write the execution plan in `docs/superpowers/plans/`.
For durable rules or decisions, use `docs/design-docs/` or `docs/adr/`.
For generated run evidence, use `artifacts/evidence/`.

## Verification Trust Levels

Use the strongest practical evidence for the surface changed:

- **Structure check**: verifies files, routing, and repo-OS shape. This is never
  enough for runtime behavior.
- **Unit or contract test**: verifies a focused behavior in-process. This is
  useful, but review whether mocks hide the integration boundary.
- **E2E or eval run**: verifies a user or corpus path. This is required for
  reminder behavior, agent runtime behavior, and other LLM-facing contracts
  when unit tests cannot prove the user-visible outcome.
- **Operational smoke**: verifies deployed or long-running service behavior.
  This is required for deployment and production-runtime claims.

If only a weaker level was run, state that limitation instead of promoting it
to a stronger claim.

## Critical Review Rules

- Before trusting a guardrail, inspect what it actually checks.
- Before trusting a test, identify the production path it represents and the
  dependencies it replaces with fakes.
- Before trusting generated evidence, verify that it is fresh for the current
  code and current runtime.
- Before deleting evidence, understand whether it is stale generated output or
  the only record supporting a recent claim.
- Before adding compatibility logic, prove that the compatibility contract is a
  product requirement rather than a way to pass a test.

## Agent Responsibilities

AI agents working in this repository must:

- read `AGENTS.md`, `docs/design-docs/index.md`, this file,
  `docs/ARCHITECTURE.md`, and the task-specific surface docs before broad work
- use `docs/fitness/surfaces.yaml` and `docs/fitness/coke-verification-matrix.md`
  as routing aids, not as unquestioned proof of correctness
- update the surface map and tests when code ownership moves
- keep root routing docs synchronized with durable workflow changes
- report verification gaps directly

Humans reviewing AI work should challenge:

- broad claims backed only by structure checks
- runtime changes without user-path or corpus evidence
- green tests that depend on stale fixtures, permissive mocks, or skipped E2E
  prerequisites
- diffs that change boundaries without an ADR or execution plan
