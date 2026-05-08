# coke

`coke` is a ClawScale-backed supervision runtime. This repository also carries
its own repo-OS layer so agents can plan, verify, and hand off work from
repository state instead of chat memory.

## Reading Order

When starting work in this repository, read in this order:

1. This file (`AGENTS.md`) for routing and operating constraints.
2. `docs/design-docs/index.md` for the canonical repo-OS map.
3. `docs/design-docs/human-ai-working-contract.md` for the critical
   human/AI collaboration contract.
4. `docs/ARCHITECTURE.md` for the canonical runtime topology and boundaries.
5. `docs/roadmap.md` for product and platform direction.
6. `docs/fitness/README.md` for verification expectations.
7. `docs/design-docs/coke-working-contract.md` for Coke-specific work surfaces.
8. `docs/fitness/coke-verification-matrix.md` for surface-to-command mapping.
9. Task-specific execution context in `docs/superpowers/specs/` (design)
   and `docs/superpowers/plans/` (execution). Both directories carry a mix
   of active and dated artifacts; verify any spec or plan against current
   `main`, `docs/ARCHITECTURE.md`, and the touched code before relying on
   it as truth.
10. `docs/deploy.md` or `docs/clawscale_bridge.md` when touching deployment,
   bridge behavior, or operational flows.

## Repository Map

- `agent/`: Agno workflows, prompts, tools, and runner code.
- `connector/clawscale_bridge/`: Coke-specific bridge runtime and outbound
  dispatch.
- `gateway/`: web UI, channel-facing API, and shared platform surfaces.
- `dao/`, `entity/`, `util/`, `framework/`: Coke runtime state and helpers.
- `docs/design-docs/`: canonical repository-level beliefs and rules.
- `docs/design-docs/human-ai-working-contract.md`: critical rules for
  human/AI collaboration, verification trust levels, and guardrail skepticism.
- `docs/design-docs/coke-working-contract.md`: the actual work surfaces inside
  Coke.
- `docs/adr/`: durable workflow and structure decisions.
- `docs/superpowers/plans/`: canonical home for multi-step execution plans (active and dated). Matches the `superpowers:writing-plans` skill default. See ADR 0003 for the consolidation history.
- `docs/superpowers/specs/`: canonical home for design specs (active and dated). Verify against current code before treating any individual spec as truth.
- `docs/fitness/`: verification rules and evidence model.
- `docs/fitness/coke-verification-matrix.md`: project-specific verification
  commands by surface.
- `docs/fitness/surfaces.yaml`: machine-readable surface and review-trigger
  map for Coke-native guardrail scripts.
- `docs/issues/`: local issue, incident, runbook, and investigation records.
- `docs/product-specs/FEATURE_TREE.md`: product, route, and API surface index.
- `docs/release-guide.md`: release and rollout workflow.
- `docs/RELEASE_CHECKLIST.md`: release closeout checklist.
- `artifacts/evidence/`: generated verification and eval evidence.
- `docs/roadmap.md`: product and platform direction.
- `docs/ARCHITECTURE.md`: canonical runtime reference for the code that exists
  today. `docs/architecture.md` is a compatibility symlink.
- `docs/deploy.md`: operational deployment and smoke-check instructions.
- `docs/clawscale_bridge.md`: bridge and personal-channel rollout notes.

## Documentation Rules

- Keep this file as a routing layer, not a knowledge dump.
- Put durable repository workflow rules in `docs/design-docs/` or `docs/adr/`.
- Put new design specs in `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`.
- Put new execution plans in `docs/superpowers/plans/YYYY-MM-DD-<topic>.md` (matches the `superpowers:writing-plans` skill default).
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
- Prefer small, reviewable changes over broad speculative rewrites.
- Preserve the product and architecture contract even when a test or eval gate
  is red. Do not add compatibility paths, parser fallbacks, heuristic
  shortcuts, or user-visible behavior changes just to make a test pass.
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
  `zsh scripts/review-trigger --base HEAD~1`.
- Run `scripts/check` when repository structure, templates, routing docs, or
  workflow rules change.
- Run the relevant runtime tests for the surfaces you touched.
- Use `docs/fitness/coke-verification-matrix.md` to choose the right command
  set for worker, bridge, gateway, deploy, and repo-OS changes.
- Follow `docs/deploy.md` for deployment-specific smoke checks.
- Follow `docs/release-guide.md` and `docs/RELEASE_CHECKLIST.md` for release
  or production rollout closeout.

## Common Commands

- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Local runtime: `./start.sh` or `bash agent/runner/agent_start.sh --force-clean`
- Unit tests: `.venv/bin/python -m pytest tests/unit/ -v`
- E2E tests: `.venv/bin/python -m pytest tests/e2e/ -v`
- Format: `black . && isort .`
- Repo-OS check: `zsh scripts/check`
- Surface verification: `zsh scripts/verify-surface <surface>`
- Verification suggestion: `zsh scripts/suggest-verification --base HEAD~1`
- Review escalation check: `zsh scripts/review-trigger --base HEAD~1`
- Production deploy: `./scripts/deploy-compose-to-gcp.sh --restart`
