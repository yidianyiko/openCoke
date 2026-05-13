# Human-AI Working Contract

This repository should be usable by humans and AI agents without relying on
private chat memory. The goal is not to make agents more confident; it is to
make their work easier to inspect, constrain, and verify.

## Repository Beliefs

1. The repository is the system of record. If an agent cannot find a durable
   rule, plan, or verification step in the repo, it is operationally missing.
2. Each kind of knowledge should have one canonical home:
   - repository workflow rules: `docs/design-docs/` or `docs/adr/`
   - design specs: `docs/superpowers/specs/`
   - execution plans: `docs/superpowers/plans/`
   - local issues, incidents, and runbooks: `docs/issues/`
   - product/API surface index: `docs/product-specs/FEATURE_TREE.md`
   - verification rules: `docs/fitness/`
   - generated verification evidence: `artifacts/evidence/`
   - product direction and runtime docs: `docs/roadmap.md`,
     `docs/ARCHITECTURE.md`, `docs/deploy.md`, and
     `docs/clawscale_bridge.md`
3. Specs and plans live together, and freshness is per-file. Verify any
   individual spec or plan against current `main`, `docs/ARCHITECTURE.md`, and
   touched code before treating it as truth.
4. Methodology must be visible to new agents. Routing files should explain
   where to read, where to write, and what counts as complete without requiring
   chat reconstruction.
5. Verification must be stronger than confidence. Completion requires fresh
   evidence: tests, checks, smoke commands, or reviewed outputs.

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

## Documentation And Delivery Rules

1. Keep `AGENTS.md` as a routing layer, not a knowledge dump.
2. Put local issue, incident, one-off repair, and investigation records in
   `docs/issues/`.
3. Keep product/API surface discovery in
   `docs/product-specs/FEATURE_TREE.md`.
4. Keep release workflow in `docs/release-guide.md` and
   `docs/RELEASE_CHECKLIST.md`.
5. If a workflow rule changes, update the canonical docs in the same change.
6. If a code migration changes runtime behavior, architecture boundaries,
   protocol shape, deployment flow, or surface ownership, update the
   corresponding canonical docs in the same change. Do not leave stale docs
   behind as "historical context" unless they are explicitly marked dated or
   superseded.
7. Prefer short, focused docs over sprawling catch-all notes. Add structure only
   when it reduces ambiguity, improves handoff, or strengthens verification.
8. Avoid duplicating the same current-state fact across multiple documents.
   Put volatile lists, route inventories, runtime topology, and product/API
   surfaces in their canonical homes, and let local README files link there
   instead of copying details that will drift.
9. Prefer staged reading over exhaustive startup reading. Agents should load
   the common routing contract first, then only the surface-specific docs
   needed for the current task.

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
  and the task-specific surface docs before broad work
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
