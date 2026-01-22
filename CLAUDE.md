# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Coke Project is a WeChat Bot virtual person solution built on the Agno framework (>=2.0.0). It implements an AI virtual character with memory, emotional understanding, and multi-modal capabilities (text, image, voice).

**Tech Stack:** Python 3.12+, Agno 2.x, DeepSeek LLM, MongoDB, Flask, Aliyun NLS (ASR), MiniMax (TTS), DashScope embeddings

## Build & Development Commands

```bash
# Environment setup
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Run the service
bash agent/runner/agent_start.sh [--force-clean]  # Main service (cleans stale locks with --force-clean)

# Testing
pytest -m "not integration"              # Quick suite (unit + pbt + e2e, no external deps)
pytest -m unit                           # Unit tests only
pytest -m integration                    # Integration tests (requires MongoDB)
pytest tests/unit/test_util_str.py::TestRemoveChinese  # Single test
pytest --cov --cov-report=html           # Coverage report (70% threshold)

# Code formatting
black . && isort .                       # Format (88-char lines, Black profile)
```

## Architecture

### Three-Phase Workflow Design

Messages are processed through three async phases with interruption detection between phases:

```
Phase 1: PrepareWorkflow (2-4s)
  ├─ OrchestratorAgent: semantic understanding + scheduling decisions
  ├─ context_retrieve_tool: direct function call for context retrieval
  └─ ReminderDetectAgent: optional, only when reminder intent detected

Phase 2: StreamingChatWorkflow (3-10s)
  └─ ChatResponseAgent: streaming multi-modal response generation

Phase 3: PostAnalyzeWorkflow (2-5s)
  └─ PostAnalyzeAgent: memory/relationship updates (can be skipped)
```

### Key Agents

- **OrchestratorAgent**: Scheduling brain - understands user intent, makes tool/agent dispatch decisions
- **ChatResponseAgent**: Response generation with multi-modal output
- **PostAnalyzeAgent**: Post-conversation analysis and memory updates
- **ReminderDetectAgent**: Reminder intent detection and creation

### Core Directories

- `agent/agno_agent/`: Agno agents (`agents/`), workflows (`workflows/`), tools (`tools/`), schemas (`schemas/`)
- `agent/runner/`: Message processing layer - `agent_handler.py` (main), `agent_background_handler.py` (background tasks)
- `agent/prompt/`: Prompt templates organized by type:
  - `agent_instructions_prompt.py`: All agent instruction prompts
  - `chat_taskprompt.py`: Task-specific prompts
  - `chat_contextprompt.py`: Context prompts (15+ types)
  - `chat_noticeprompt.py`: Attention/constraint prompts
- `dao/`: MongoDB data access layer with distributed lock management
- `connector/`: Platform connectors (ecloud for E云管家, terminal for testing)

### MongoDB Collections

`inputmessages`, `outputmessages`, `users`, `conversations`, `relations`, `embeddings`, `reminders`, `locks`

**GTD Support (P0):**
- `reminders` collection now supports GTD-style task collection
- `list_id` field: defaults to "inbox", supports task organization
- `trigger_time` field: can be `None` for tasks without specific time

### Ecloud Group Chat Support

**Configuration (conf/config.json):**
```json
"ecloud": {
  "group_chat": {
    "enabled": false,
    "context_message_count": 10,
    "whitelist_groups": ["xxx@chatroom"],
    "reply_mode": {
      "whitelist": "all",
      "others": "mention_only"
    }
  }
}
```

**Reply Modes:**
- `whitelist: "all"` - Respond to all messages in whitelist groups
- `others: "mention_only"` - Only respond when @mentioned in non-whitelist groups

**Message Types Supported:**
- 80001: Group text
- 80002: Group image
- 80004: Group voice
- 80014: Group reference/quote

### GTD Task System

**P0 Features (Completed):**
- Quick capture: Create tasks without trigger_time
- Inbox collection: Tasks default to `list_id="inbox"`
- Query differentiation: Displays scheduled vs inbox tasks separately

**P1 Roadmap:**
- Agent prompt adjustments for conversational task creation
- Daily inbox digest (8:30 AM summary)
- Custom list support beyond "inbox"
- Priority and tags

### Async/Concurrency Patterns

- Full async pipeline using `asyncio` with `agent.arun()` for LLM calls
- Distributed locks via `LockManager` with `acquire_lock_async()`
- Optimistic locking with safe lock release (only release own locks)
- Message interruption detection between workflow phases

## Coding Standards

- Black/Isort formatting (88 chars, 4-space indent)
- snake_case for modules/functions, PascalCase for classes
- Type hints on public functions
- Conventional commits: `type(scope): summary`
- Mark MongoDB-dependent tests with `@pytest.mark.integration`

## Configuration

- Secrets in `.env` file (DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, etc.)
- Runtime config in `conf/config.json`
- Test markers defined in `pyproject.toml`: unit, integration, slow, pbt, e2e

## Key Documentation

- `doc/architecture/detailed_architecture_analysis.md`: Comprehensive architecture document (v2.7)
- `doc/architecture/agent-prompt.md`: Agent prompt specification and standards
