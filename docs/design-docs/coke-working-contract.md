# Coke Working Contract

This document defines Coke-specific work surfaces for agents. It complements
`docs/design-docs/human-ai-working-contract.md`.

## Clean-Rebuild Premise

Coke is in a destructive clean-rebuild track. Work should follow the current
requirements and target architecture instead of preserving old runtime shape.

Source documents:

- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`
- `docs/ARCHITECTURE.md`
- `docs/product-specs/FEATURE_TREE.md`
- `docs/design-docs/interface-contract.md`

## Future Clean-Rebuild Services

- `coke-api`: Python ingress/egress HTTP tier.
- `coke-worker`: Python Redis Stream turn workers.
- `coke-scheduler`: singleton Python reminder scheduler.
- `coke-outbox-relay`: Postgres outbox to Redis Stream relay.
- `coke-web`: Next.js thin client.
- `postgres`: product state, Agno session/history/memory/knowledge, pgvector.
- `redis`: wake-up stream, locks, reply pub/sub.

The standalone ClawScale bridge is superseded. ClawScale remains only as the
`wechat_personal` provider adapter behind Coke's canonical provider contract.

## Work Surfaces

- Product/API discovery: `docs/product-specs/FEATURE_TREE.md` and
  `docs/design-docs/interface-contract.md`.
- Runtime architecture: `docs/ARCHITECTURE.md`.
- Clean-rebuild service operations: `docs/deploy.md`.
- ClawScale adapter boundary: `docs/clawscale_bridge.md`.
- Verification routing: `docs/fitness/coke-verification-matrix.md` and
  `docs/fitness/surfaces.yaml`.
- Design specs and execution plans: `docs/superpowers/specs/` and
  `docs/superpowers/plans/`.

Legacy/current-checkout pointers that still help agents locate the surface they
are replacing or deleting:

- Worker runtime entry: `agent/runner/agent_runner.py`.
- Superseded bridge ingress: `connector/clawscale_bridge/app.py`.
- Superseded bridge egress: `connector/clawscale_bridge/output_dispatcher.py`.
- Superseded TypeScript API package: `gateway/packages/api`.
- Thin web package to repoint/de-brand: `gateway/packages/web`.
- Existing deploy regression script: `scripts/test-deploy-compose-to-gcp.sh`.

## Implementation Rules

- Keep product behavior in Python domain modules, not in route handlers or
  provider adapters.
- Treat TypeScript Gateway API and standalone bridge ownership as superseded
  unless the task is explicitly deleting, migrating, or documenting that legacy
  surface.
- Keep all durable state in Postgres and all coordination in Redis.
- Do not add Mongo-backed runtime state.
- Keep The Turn as the only normal chat/channel-visible product prose producer.
- Do not add legacy compatibility shims, parser fallbacks, alias routes, or
  duplicate old implementations without a current canonical requirement.
- Friendships and shared reminders are direct active product states; approval
  flows are out of scope.

## Verification Rules

For clean-rebuild docs, run:

```bash
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

For non-trivial changes, also run diff-aware routing:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

`review-trigger` is a risk report, not a human-review completion gate.
