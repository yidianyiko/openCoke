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
pytest tests/unit/ -v
pytest tests/e2e/ -v
zsh scripts/check
zsh scripts/verify-surface repo-os
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

## Repository Structure

```
AGENTS.md                  # routing layer for agents
tasks/                     # task-local work state
docs/design-docs/          # durable repository workflow intent
docs/design-docs/coke-working-contract.md
                           # Coke-specific work surfaces and planning contract
docs/adr/                  # durable workflow and structure decisions
docs/exec-plans/           # canonical home for new execution plans
docs/fitness/              # verification rulebook
docs/fitness/coke-verification-matrix.md
                           # project-specific verification commands by surface
docs/fitness/surfaces.yaml # machine-readable surface and review trigger map
docs/roadmap.md            # product and platform direction
docs/architecture.md       # runtime architecture
docs/deploy.md             # deployment and smoke checks
docs/clawscale_bridge.md   # bridge and channel rollout notes
docs/superpowers/          # dated design and implementation history
scripts/check              # repository structure verification entrypoint
scripts/suggest-verification
                           # diff-aware verification suggestion entrypoint
scripts/review-trigger     # diff-aware review escalation entrypoint
```

## Documentation

- `AGENTS.md`: routing layer and reading order
- `docs/design-docs/index.md`: canonical repo-OS map
- `docs/design-docs/coke-working-contract.md`: project-specific work surfaces
- `docs/roadmap.md`: high-level status and migration direction
- `docs/architecture.md`: current runtime architecture
- `docs/deploy.md`: deployment and startup notes
- `docs/fitness/README.md`: verification expectations
- `docs/fitness/coke-verification-matrix.md`: what to run for worker, bridge,
  gateway, deploy, and repo-OS changes
- `docs/fitness/surfaces.yaml`: machine-readable surface and review-trigger
  map used by the guardrail scripts
- `docs/exec-plans/`: canonical home for new execution plans
- `tasks/`: task-local work state
- `docs/superpowers/`: dated design and implementation history
