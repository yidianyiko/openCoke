# Repository Guidelines

## Project Structure & Module Organization
- `agent/`: agents, workflows, prompts, tools, and runtime handlers under `agent/runner/`.
- `dao/`: Mongo-backed data access for locks, reminders, users, conversations, orders, and usage records.
- `connector/`: channel abstractions, ClawScale bridge code, gateway helpers, and terminal tooling.
- `conf/`: runtime configuration in `config.json` and loader logic in `config.py`.
- `util/`: shared helpers for logging, time, redis, files, embeddings, and OSS.
- `tests/`: unit tests in `tests/unit/` and E2E tests in `tests/e2e/`.

## Setup, Build, and Development Commands
- Python 3.12+. Create a venv and install deps: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (runner scripts auto-install `agent/requirements.txt` when missing).
- Start the full local stack with `./start.sh`; start only the Python workers with `bash agent/runner/agent_start.sh [--force-clean]`.
- Quick formatting pass: `black . && isort .` (88-char lines, Black profile).

## Coding Style & Naming Conventions
- Follow Black/Isort defaults (88 chars, 4-space indent); keep imports sorted and grouped; prefer type hints on public functions.
- Python naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE`.
- Keep prompts/workflows in `agent/prompt` and `agent/agno_agent/workflows` cohesive; co-locate tests alongside module area in `tests/<scope>/test_*.py`.

## Testing Guidelines
- 运行单元测试: `pytest tests/unit/ -v`
- 运行 E2E 测试: `pytest tests/e2e/ -v` 或 `pytest -m e2e -v`
- Coverage: `pytest --cov --cov-report=html` 输出到 `htmlcov/`

## Commit & Pull Request Guidelines
- Use conventional commits observed in history: `type(scope): summary` (e.g., `fix(reminder): remove time window and add limit`).
- PRs should include: concise summary, linked issue/requirement, testing notes (commands run), and any config or data migration steps; add logs or screenshots when behavior changes.
- Keep changes small and scoped; update relevant docs in `docs/` when altering workflows, prompts, or reminder logic.

## Configuration & Operational Notes
- Secrets and endpoints should live in `.env`; `agent_start.sh` exports `env=aliyun` by default and supports toggling background agents via `DISABLE_DAILY_AGENTS` and `DISABLE_BACKGROUND_AGENTS`.
- Logs default to `agent/runner/agent.log`; clean stale locks via `agent_start.sh --force-clean` if the runner was interrupted.
