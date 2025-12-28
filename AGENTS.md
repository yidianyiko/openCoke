# Repository Guidelines

## Project Structure & Module Organization
- `agent/`: core logic for agents, workflows, prompts, tools, and runtime `runner/` (entrypoint scripts and background handlers).
- `dao/`: Mongo-backed data access (locks, reminders, users, conversations); `entity/`: shared schemas and value objects.
- `connector/`: external connectors (e.g., terminal, ecloud) built on `base_connector.py`.
- `conf/`: runtime configuration (`config.json`, `config.py`); `util/`: cross-cutting helpers.
- `scripts/`: maintenance and analysis utilities for reminders, content safety, and usage metrics.
- `tests/`: pytest suite organized by marker (`unit/`, `integration/`, `pbt/`, `e2e/`), with fixtures under `tests/fixtures/`.

## Setup, Build, and Development Commands
- Python 3.12+. Create a venv and install deps: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (runner scripts auto-install `agent/requirements.txt` when missing).
- Run the background service: `bash agent/runner/agent_start.sh [--force-clean]` (loads `.env` if present, manages locks, tails `agent/runner/agent.log`).
- Quick formatting pass: `black . && isort .` (88-char lines, Black profile).

## Coding Style & Naming Conventions
- Follow Black/Isort defaults (88 chars, 4-space indent); keep imports sorted and grouped; prefer type hints on public functions.
- Python naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE`.
- Keep prompts/workflows in `agent/prompt` and `agent/agno_agent/workflows` cohesive; co-locate tests alongside module area in `tests/<scope>/test_*.py`.

## Testing Guidelines
- Default quick suite: `pytest -m "not integration" -v`.
- Targeted runs: `pytest -m unit`, `pytest -m integration`, `pytest -m e2e`, or `pytest tests/unit/test_util_str.py::TestRemoveChinese`.
- Coverage: `pytest --cov --cov-report=html` outputs to `htmlcov/`; project threshold is 70%+ (see `pyproject.toml`), with higher expectations for `util` and `entity`.
- Use markers (`unit`, `integration`, `slow`, `pbt`, `e2e`) and fixtures from `tests/fixtures/`; mark Mongo-dependent tests with `integration`.

## Commit & Pull Request Guidelines
- Use conventional commits observed in history: `type(scope): summary` (e.g., `fix(reminder): remove time window and add limit`).
- PRs should include: concise summary, linked issue/requirement, testing notes (commands run), and any config or data migration steps; add logs or screenshots when behavior changes.
- Keep changes small and scoped; update relevant docs (`doc/` or `tests/README.md`) when altering workflows, prompts, or reminder logic.

## Configuration & Operational Notes
- Secrets and endpoints should live in `.env`; `agent_start.sh` exports `env=aliyun` by default and supports toggling background agents via `DISABLE_DAILY_AGENTS` and `DISABLE_BACKGROUND_AGENTS`.
- Logs default to `agent/runner/agent.log`; clean stale locks via `agent_start.sh --force-clean` if the runner was interrupted.
