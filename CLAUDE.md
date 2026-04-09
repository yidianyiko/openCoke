# CLAUDE.md

This file provides concise guidance for Claude Code when working in this repository.

## Project Overview

Coke is a Python 3.12+ chat agent system built on Agno, MongoDB, Redis, and several platform connectors.

The main runtime path is:

1. `PrepareWorkflow`
2. `StreamingChatWorkflow`
3. `PostAnalyzeWorkflow`

## Build And Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Main startup entrypoint
./start.sh

# Python workers only
bash agent/runner/agent_start.sh [--force-clean]

# Tests
pytest tests/unit/ -v
pytest tests/e2e/ -v
pytest --cov --cov-report=html

# Formatting
black . && isort .
```

## Runtime Architecture

### Core Workflows

- `agent/agno_agent/workflows/prepare_workflow.py`: intent parsing, context retrieval, reminder detection, optional web search
- `agent/agno_agent/workflows/chat_workflow_streaming.py`: streaming chat generation
- `agent/agno_agent/workflows/post_analyze_workflow.py`: post-turn analysis and memory updates

### Pre-Created Agents

The module-level agents in `agent/agno_agent/agents/__init__.py` are:

- `orchestrator_agent`
- `reminder_detect_agent`
- `post_analyze_agent`

The streaming chat agent is instantiated inside `StreamingChatWorkflow`.

### Key Directories

- `agent/agno_agent/`: agents, schemas, tools, workflows
- `agent/prompt/`: prompt templates and personality/context/task prompts
- `agent/runner/`: message handling, background tasks, access gate, payment providers
- `connector/channel/`: channel base abstractions
- `connector/adapters/`: Telegram, Discord, and terminal adapters kept in this repository
- `connector/clawscale_bridge/`: Coke-specific ClawScale bridge runtime
- `connector/gateway/`: gateway helper server and config
- `dao/`: MongoDB DAOs
- `entity/`: shared message/entity structures
- `framework/tool/`: media and search integrations
- `util/`: logging, time, redis, embedding, file, and OSS helpers

## Queue And Storage

- Redis stream mode uses `coke:input` with consumer group `coke-workers`
- Polling mode reads from MongoDB `inputmessages`
- Common MongoDB collections: `inputmessages`, `outputmessages`, `users`, `conversations`, `relations`, `embeddings`, `reminders`, `locks`, `orders`, `usage_records`

## Current Docs

- `docs/architecture.md`
- `docs/deploy.md`
- `AGENTS.md`
