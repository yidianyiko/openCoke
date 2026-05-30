# Project Coke

Coke is a clean-rebuild supervision runtime centered on the Python `coke/`
package, Alembic migrations, and a standalone top-level `web/` client. The
repository also carries a repo-OS layer for planning, verification, and
handoff, so durable project state lives in files instead of chat history.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/check
```

## Production Deployment

Production targets Docker Compose services:

- `coke-api`
- `coke-worker`
- `coke-scheduler`
- `coke-outbox-relay`
- `coke-web`
- `postgres`
- `redis`

Key files:

- `Dockerfile`
- `docker-compose.prod.yml`
- `deploy/config/coke.config.json`
- `deploy/env/coke.env.example`
- `deploy/nginx/coke.conf`
- `deploy/systemd/coke-compose.service`

See `docs/deploy.md` for the current deployment contract.

## Testing

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Run the suggested surface command instead of defaulting to the full suite. For
repository-structure or workflow-doc edits, `repo-os-docs` usually means
`zsh scripts/check`; runtime, deploy, and user-visible behavior still need the
stronger commands named by the guardrails.

## Documentation

Use `AGENTS.md` for staged reading rules and `docs/design-docs/index.md` for
the canonical repo-OS map. Keep current-state details in their canonical homes
instead of copying them into this README:

- Runtime topology: `docs/ARCHITECTURE.md`
- Verification: `docs/fitness/README.md`,
  `docs/fitness/coke-verification-matrix.md`, `docs/fitness/surfaces.yaml`
- Product/API surfaces: `docs/product-specs/FEATURE_TREE.md`
- Issues and runbooks: `docs/issues/`
- Specs and plans: `docs/superpowers/specs/`, `docs/superpowers/plans/`
- Release and rollout: `docs/release-guide.md`, `docs/RELEASE_CHECKLIST.md`
- Evidence: `artifacts/evidence/`
