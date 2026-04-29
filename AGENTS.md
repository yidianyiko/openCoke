# coke

`coke` is a ClawScale-backed supervision runtime. This repository also carries
its own repo-OS layer so agents can plan, verify, and hand off work from
repository state instead of chat memory.

## Reading Order

When starting work in this repository, read in this order:

1. This file (`AGENTS.md`) for routing and operating constraints.
2. `docs/design-docs/index.md` for the canonical repo-OS map.
3. `docs/roadmap.md` for product and platform direction.
4. `docs/architecture.md` for the runtime topology wired in code.
5. `docs/fitness/README.md` for verification expectations.
6. `docs/design-docs/coke-working-contract.md` for Coke-specific work surfaces.
7. `docs/fitness/coke-verification-matrix.md` for surface-to-command mapping.
8. Task-specific files in `tasks/`, `docs/exec-plans/`, or
   `docs/superpowers/`.
9. `docs/deploy.md` or `docs/clawscale_bridge.md` when touching deployment,
   bridge behavior, or operational flows.

## Repository Map

- `agent/`: Agno workflows, prompts, tools, and runner code.
- `connector/clawscale_bridge/`: Coke-specific bridge runtime and outbound
  dispatch.
- `gateway/`: web UI, channel-facing API, and shared platform surfaces.
- `dao/`, `entity/`, `util/`, `framework/`: Coke runtime state and helpers.
- `docs/design-docs/`: canonical repository-level beliefs and rules.
- `docs/design-docs/coke-working-contract.md`: the actual work surfaces inside
  Coke.
- `docs/adr/`: durable workflow and structure decisions.
- `docs/exec-plans/`: canonical home for new multi-step execution plans.
- `docs/fitness/`: verification rules and evidence model.
- `docs/fitness/coke-verification-matrix.md`: project-specific verification
  commands by surface.
- `docs/fitness/surfaces.yaml`: machine-readable surface and review-trigger
  map for Coke-native guardrail scripts.
- `tasks/`: task-local work state.
- `docs/roadmap.md`: product and platform direction.
- `docs/architecture.md`: runtime reference for the code that exists today.
- `docs/deploy.md`: operational deployment and smoke-check instructions.
- `docs/clawscale_bridge.md`: bridge and personal-channel rollout notes.
- `docs/superpowers/specs/` and `docs/superpowers/plans/`: dated design and
  implementation history that remains valid during the transition.

## Documentation Rules

- Keep this file as a routing layer, not a knowledge dump.
- Put durable repository workflow rules in `docs/design-docs/` or `docs/adr/`.
- Put new execution plans in `docs/exec-plans/` and task-local state in
  `tasks/`.
- Keep product, architecture, deployment, and bridge details in their domain
  docs.
- Preserve existing `docs/superpowers/` history unless a dedicated migration
  explicitly replaces it.

## Delivery Rules

- Every non-trivial task should have a task file in `tasks/`.
- Multi-step, risky, cross-cutting, or multi-session work should also have an
  execution plan in `docs/exec-plans/`.
- Prefer small, reviewable changes over broad speculative rewrites.
- If a workflow rule changes, update the canonical docs in the same change.
- Use isolated git worktrees when concurrent implementation is real.

## Validation

- Do not claim work is complete without fresh verification evidence.
- Run `scripts/check` when repository structure, templates, routing docs, or
  workflow rules change.
- Run the relevant runtime tests for the surfaces you touched.
- Use `docs/fitness/coke-verification-matrix.md` to choose the right command
  set for worker, bridge, gateway, deploy, and repo-OS changes.
- Follow `docs/deploy.md` for deployment-specific smoke checks.

## Common Commands

- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Local runtime: `./start.sh` or `bash agent/runner/agent_start.sh --force-clean`
- Unit tests: `pytest tests/unit/ -v`
- E2E tests: `pytest tests/e2e/ -v`
- Format: `black . && isort .`
- Repo-OS check: `zsh scripts/check`
- Surface verification: `zsh scripts/verify-surface <surface>`
- Verification suggestion: `zsh scripts/suggest-verification --base HEAD~1`
- Review escalation check: `zsh scripts/review-trigger --base HEAD~1`
- Production deploy: `./scripts/deploy-compose-to-gcp.sh --restart`
