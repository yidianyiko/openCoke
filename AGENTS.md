# coke

`coke` is a clean-rebuild supervision runtime. This repository also carries
its own repo-OS layer so agents can plan, verify, and hand off work from
repository state instead of chat memory.

## Reading Order

Do staged reading. Do not open every canonical document by default.

For every task, read only:

1. This file (`AGENTS.md`) for routing and operating constraints.
2. `docs/design-docs/index.md` for the canonical repo-OS map.
3. `docs/design-docs/human-ai-working-contract.md` for the critical
   human/AI collaboration contract.

Then add the smallest task-specific slice:

- Runtime or boundary work: `docs/ARCHITECTURE.md` and
  `docs/design-docs/coke-working-contract.md`.
- Product/API/route discovery: `docs/product-specs/FEATURE_TREE.md`, then
  `docs/roadmap.md` only when product direction matters.
- Verification routing: start with `zsh scripts/suggest-verification --base
  HEAD~1`; open `docs/fitness/README.md`,
  `docs/fitness/coke-verification-matrix.md`, or
  `docs/fitness/surfaces.yaml` only if the suggested command needs review.
- Deployment, provider-adapter operations, or rollout: `docs/deploy.md` and/or
  `docs/clawscale_bridge.md`.
- Task-specific execution context in `docs/superpowers/specs/` (design)
  and `docs/superpowers/plans/` (execution) only when the task names that
  context or is multi-step/risky. Both directories carry a mix of active and
  dated artifacts; verify any spec or plan against current `main`,
  `docs/ARCHITECTURE.md`, and the touched code before relying on it as truth.
  Keep `docs/superpowers/plans/` flat for `superpowers:writing-plans`
  compatibility; plan lifecycle belongs in file status metadata, not
  `active/` or `completed/` subdirectories.

## Repository Map

- Runtime code: `coke/`, `migrations/`, and `web/`.
- Repo-OS map: `docs/design-docs/index.md`; collaboration contract:
  `docs/design-docs/human-ai-working-contract.md`; Coke work surfaces:
  `docs/design-docs/coke-working-contract.md`; ADRs: `docs/adr/`.
- Current runtime truth: `docs/ARCHITECTURE.md`
  (`docs/architecture.md` is a compatibility symlink); product direction:
  `docs/roadmap.md`; deployment/bridge operations: `docs/deploy.md`,
  `docs/clawscale_bridge.md`.
- Verification: `docs/fitness/README.md`,
  `docs/fitness/coke-verification-matrix.md`, `docs/fitness/surfaces.yaml`;
  generated evidence: `artifacts/evidence/`.
- Work records: `docs/issues/`, `docs/superpowers/specs/`,
  `docs/superpowers/plans/`.
- Product and release surfaces: `docs/product-specs/FEATURE_TREE.md`,
  `docs/release-guide.md`, `docs/RELEASE_CHECKLIST.md`.

## Documentation Rules

- Keep this file as a routing layer, not a knowledge dump.
- Put durable repository workflow rules in `docs/design-docs/` or `docs/adr/`.
- Put new design specs in `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`.
- Put new execution plans in `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`
  (matches the `superpowers:writing-plans` skill default). Do not create
  lifecycle subdirectories under `docs/superpowers/plans/`.
- Put local issue, incident, one-off repair, and historical runbook records in
  `docs/issues/`, not as loose top-level docs.
- Keep route and API discoverability in `docs/product-specs/FEATURE_TREE.md`.
- Keep release workflow in `docs/release-guide.md` and the release closeout
  checklist in `docs/RELEASE_CHECKLIST.md`.
- Keep product, architecture, deployment, and bridge details in their domain
  docs.
- `docs/superpowers/` is the canonical home for specs and plans, not a
  history-only archive. But individual files vary in freshness — always
  verify a spec or plan against current `main`, `docs/ARCHITECTURE.md`,
  and the actual code before using it as evidence.

## Issue Feedback Loop

- Before creating a new issue, search `docs/issues/` for existing incident or
  investigation context.
- For non-trivial failures, create or update
  `docs/issues/YYYY-MM-DD-short-description.md` first. Capture what happened,
  why it mattered, affected surfaces, current status, and evidence.
- Use one canonical active local tracker per problem. Supporting investigation
  material should use `kind: progress_note`, `kind: verification_report`, or
  `kind: runbook` instead of becoming another active tracker.
- Use `kind: github_mirror` only for GitHub-synced mirrors. Include
  `github_issue`, `github_state`, and `github_url` when a local record tracks
  GitHub.
- When resolved, update the local issue record with the fix commit and final
  verification.
- Run issue hygiene at least once every seven days and update
  `docs/issues/issue-gc-state.yaml`.

## Delivery Rules

- Multi-step, risky, cross-cutting, or multi-session work should also have an
  execution plan in `docs/superpowers/plans/`.
- Prefer small, coherent commits over broad speculative rewrites.
- Every completed repository change must be committed before handoff, including
  docs, tests, generated workflow records, and guardrail updates. Do not wait
  for human review because a diff is large, cross-boundary, deployment-related,
  or otherwise sensitive; record the risk and verification evidence in the
  handoff instead. The only exceptions are an explicit user instruction not to
  commit or an unresolved blocker that makes a correct commit impossible.
- Preserve the product and architecture contract even when a test or eval gate
  is red. Do not add compatibility paths, parser fallbacks, heuristic
  shortcuts, or user-visible behavior changes just to make a test pass.
- Code must carry only the current product and architecture contract. Do not
  keep compatibility code, legacy shims, alias routes, fallback parsers,
  duplicate old implementations, or retired workflow branches unless a current
  canonical spec explicitly names that behavior as an active requirement.
  Otherwise delete the implementation and update callers, tests, and docs in
  the same change.
- When verification fails, classify the failure before editing: product/runtime
  bug, test/eval bug, environment instability, or plan gap. Fix the matching
  layer only; if the correct layer is unclear, stop and record the blocker
  instead of forcing the gate green.
- If a workflow rule changes, update the canonical docs in the same change.
- If a code migration changes runtime behavior, architecture boundaries,
  protocol shape, deployment flow, or surface ownership, update the
  corresponding canonical docs in the same change. Do not leave stale docs
  behind as "historical context" unless they are explicitly marked dated or
  superseded.
- Do not duplicate volatile current-state facts across README files, routing
  docs, architecture docs, and feature indexes. Put the fact in its canonical
  home and link to it from local docs.
- Use isolated git worktrees when concurrent implementation is real.

## Validation

- Do not claim work is complete without fresh verification evidence.
- Passing tests are evidence, not the goal. A change that passes tests by
  weakening the real contract is a failed change and must be reverted or
  redesigned.
- Structure checks do not prove runtime behavior.
- Unit tests with mocks do not prove user-visible paths.
- Runtime, eval, or deployment claims need user-path, corpus, or smoke evidence.
- For non-trivial changes, run diff-aware routing before hand-picking tests:
  `zsh scripts/suggest-verification --base HEAD~1`, then
  `zsh scripts/review-trigger --base HEAD~1`. `review-trigger` is a
  non-blocking risk report; it must not require human review or block a commit.
- For docs-only repo-OS edits, prefer the lighter `repo-os-docs` surface
  suggested by the guardrails. Use the heavier `repo-os` surface when changing
  guardrail scripts, `docs/fitness/surfaces.yaml`, or verification tooling.
- Run `scripts/check` when repository structure, templates, routing docs, or
  workflow rules change.
- Run the relevant runtime tests for the surfaces you touched.
- Use `docs/fitness/coke-verification-matrix.md` to choose the right command
  set for backend, web, deploy, and repo-OS changes.
- Follow `docs/deploy.md` for deployment-specific smoke checks.
- Follow `docs/release-guide.md` and `docs/RELEASE_CHECKLIST.md` for release
  or production rollout closeout.

## Common Commands

- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Backend unit tests: `.venv/bin/python -m pytest tests/unit/coke -v`
- Web tests: `cd web && pnpm test`
- Web build: `cd web && pnpm build`
- Format: `black . && isort .`
- Repo-OS check: `zsh scripts/check`
- Surface verification: `zsh scripts/verify-surface <surface>`
- Verification suggestion: `zsh scripts/suggest-verification --base HEAD~1`
- Risk trigger report: `zsh scripts/review-trigger --base HEAD~1`
- Production deploy: follow `docs/deploy.md` and run the deploy surface checks.
