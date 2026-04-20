# CLAUDE.md

This file provides concise guidance for coding agents working in this
repository.

## Read First

1. `AGENTS.md`
2. `docs/design-docs/index.md`
3. `docs/roadmap.md`
4. `docs/architecture.md`
5. `docs/fitness/README.md`
6. `docs/design-docs/coke-working-contract.md`
7. `docs/fitness/coke-verification-matrix.md`
8. Relevant files in `tasks/`, `docs/exec-plans/`, or `docs/superpowers/`
9. `docs/deploy.md` or `docs/clawscale_bridge.md` when the task touches those
   surfaces

## Current Runtime Summary

- Core turn pipeline:
  1. `PrepareWorkflow`
  2. `StreamingChatWorkflow`
  3. `PostAnalyzeWorkflow`
- Worker runtime: `agent/runner/agent_runner.py`
- Bridge runtime: `connector/clawscale_bridge/app.py`
- Web/API surface: `gateway/`

## Common Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

./start.sh
bash agent/runner/agent_start.sh --force-clean

pytest tests/unit/ -v
pytest tests/e2e/ -v
black . && isort .
zsh scripts/check
```

## Repo OS Conventions

- New task-local state lives in `tasks/`.
- New multi-step execution plans live in `docs/exec-plans/`.
- Durable workflow rules live in `docs/design-docs/` or `docs/adr/`.
- Use `docs/design-docs/coke-working-contract.md` to label touched surfaces.
- Use `docs/fitness/coke-verification-matrix.md` to choose verification
  commands.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` remain valid dated
  design and implementation history.
