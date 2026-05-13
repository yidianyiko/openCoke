# Project Coke

Coke is now deployed and operated as a ClawScale-backed runtime:

1. `agent/runner/agent_runner.py` runs the Coke workers and background tasks.
2. `connector/clawscale_bridge/app.py` handles Coke-specific auth, binding, and outbound dispatch.
3. `gateway/` provides the web UI and channel-facing API.

The repository now also carries a small repo-OS layer for planning,
verification, and handoff. That control layer lives alongside the runtime code
instead of only in chat history.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local worker runtime
./start.sh
```

## Production Deployment

Production on `gcp-coke` runs through Docker Compose, host Nginx, and a systemd wrapper.

Key files:

- `docker-compose.prod.yml`
- `deploy/config/coke.config.json`
- `deploy/env/coke.env.example`
- `deploy/nginx/coke.conf`
- `deploy/systemd/coke-compose.service`

Useful commands:

```bash
# Sync deployment files to gcp-coke
./scripts/deploy-compose-to-gcp.sh

# Reset the remote host runtime before a clean redeploy
./scripts/reset-gcp-coke.sh

# Start or rebuild the stack on the server
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans'
```

## Testing

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Run the suggested surface command instead of defaulting to the full unit or E2E
suite. For repository-structure or workflow-doc edits, `repo-os-docs` usually
means `zsh scripts/check`; runtime, deploy, and user-visible behavior still need
the stronger commands named by the guardrails.

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
