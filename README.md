# Project Coke

Coke is a multi-channel chat agent system built around a three-phase workflow:

1. `PrepareWorkflow` parses intent, retrieves context, and runs reminder detection when needed.
2. `StreamingChatWorkflow` generates the user-facing reply.
3. `PostAnalyzeWorkflow` performs memory and relationship updates in the background.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Main startup entrypoint
./start.sh
```

Useful commands:

```bash
# Directly start only the Python workers
bash agent/runner/agent_start.sh

# Run unit tests
pytest tests/unit/ -v

# Run E2E tests
pytest tests/e2e/ -v
```

## Documentation

- `AGENTS.md`: repository workflow and coding rules
- `docs/roadmap.md`: high-level status, migration direction, and next milestones
- `docs/architecture.md`: current runtime architecture
- `docs/deploy.md`: deployment and startup notes
