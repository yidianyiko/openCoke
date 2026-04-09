# Project Coke

Coke is now deployed and operated as a ClawScale-backed runtime:

1. `agent/runner/agent_runner.py` runs the Coke workers and background tasks.
2. `connector/clawscale_bridge/app.py` handles Coke-specific auth, binding, and outbound dispatch.
3. `gateway/` provides the web UI and channel-facing API.

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
```

## Documentation

- `AGENTS.md`: repository workflow and coding rules
- `docs/roadmap.md`: high-level status and migration direction
- `docs/architecture.md`: current runtime architecture
- `docs/deploy.md`: deployment and startup notes
