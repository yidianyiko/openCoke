# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Coke Project is a WeChat Bot virtual person solution built on the Agno framework (>=2.0.0). It implements an AI virtual character with memory, emotional understanding, and multi-modal capabilities (text, image, voice).

**Tech Stack:** Python 3.12+, Agno 2.x, DeepSeek LLM, MongoDB, Redis, Flask, Aliyun NLS (ASR), MiniMax (TTS), DashScope embeddings

## Build & Development Commands

```bash
# Environment setup
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Run the service
bash agent/runner/agent_start.sh [--force-clean]  # Main service (cleans stale locks with --force-clean)

# Testing
pytest tests/unit/                               # Unit tests (no markers needed)
pytest tests/e2e/ -m e2e                         # E2E tests (requires LLM API access)
pytest tests/unit/test_context_timezone.py       # Single test file
pytest --cov --cov-report=html                   # Coverage report (70% threshold)

# Code formatting
black . && isort .                               # Format (88-char lines, Black profile)
```

Test markers (defined in `pyproject.toml`): `e2e`, `slow`. Unit tests in `tests/unit/` use no markers.

## Architecture

### Three-Phase Workflow Design

Messages are processed through three async phases with interruption detection between phases:

```
Phase 1: PrepareWorkflow (2-6s)
  ├─ OrchestratorAgent: semantic understanding + scheduling decisions
  ├─ context_retrieve_tool: direct function call for context retrieval
  ├─ web_search_tool: optional, when need_web_search=true (Bocha Search API)
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

Production agents in `agent/agno_agent/agents/__init__.py`: `orchestrator_agent`, `reminder_detect_agent`, `post_analyze_agent`, plus `future_message_*` agents for scheduled messages.

### Core Directories

- `agent/agno_agent/`: Agno agents (`agents/`), workflows (`workflows/`), tools (`tools/`), schemas (`schemas/`)
- `agent/runner/`: Message processing layer - `agent_handler.py` (main), `agent_background_handler.py` (background tasks), `access_gate.py` (access control), `payment/` (Stripe/Creem providers)
- `agent/prompt/`: Prompt templates - `agent_instructions_prompt.py` (all agent instructions), `chat_taskprompt.py`, `chat_contextprompt.py` (15+ context types), `chat_noticeprompt.py`
- `dao/`: MongoDB data access layer with distributed lock management
- `connector/`: Platform connectors — see Connector Architecture below
- `framework/tool/`: Multimodal processing tools (`image2text/`, `text2image/`, `text2voice/`, `voice2text/`, `search/`)
- `entity/message.py`: Shared message schemas
- `util/`: Cross-cutting helpers (log, time, redis, embedding, OSS)

### Connector Architecture

Multi-layer platform integration:

```
connector/
  channel/          # Abstract base classes (ChannelAdapter, StandardMessage, DeliveryMode)
  adapters/         # Platform-specific implementations
    ecloud/         # E云管家 WeChat adapter
    telegram/       # Telegram adapter
    discord/        # Discord adapter
    whatsapp/       # WhatsApp via Evolution API (webhook + polling modes)
  ecloud/           # Legacy direct ecloud connector (Flask app with /message, /webhook/stripe, /webhook/creem)
  gateway/          # GatewayServer: manages Gateway-mode adapters, routes messages to MongoDB inputmessages
  terminal/         # Terminal connector for local testing
```

**Adapter delivery modes** (defined in `connector/channel/types.py`): `POLLING`, `GATEWAY`, `HYBRID`

**Flask app** (`connector/ecloud/ecloud_input.py`): Hosts `/message` (ecloud webhook), `/webhook/creem`, `/webhook/stripe` routes.

### Message Queue

`agent_runner.py` supports two modes (auto-detected from config):
- **Redis stream mode**: Messages arrive via Redis stream (`coke:input`, consumer group `coke-workers`)
- **Polling mode**: Polls MongoDB `inputmessages` collection directly

### MongoDB Collections

`inputmessages`, `outputmessages`, `users`, `conversations`, `relations`, `embeddings`, `reminders`, `locks`, `orders`, `usage`

### Access Control (Gate System)

Platform-agnostic. Configuration in `conf/config.json`:

```json
"access_control": {
    "enabled": false,
    "provider": "creem",          // "creem" or "stripe"
    "platforms": { "wechat": false },
    "creem": { "product_id": "...", "success_url": "..." },
    "stripe": { "price_id": "...", "success_url": "..." },
    "deny_message": "..{checkout_url}..",
    "expire_message": "..{checkout_url}..",
    "success_message": "..[System] Subscription active until {expire_time}"
}
```

- Orders stored in `orders` collection, bound 1:1 to users via `users.access`
- Admin user (configured via `admin_user_id` in config) is exempt
- Payment providers in `agent/runner/payment/`: `stripe_provider.py`, `creem_provider.py`

### Ecloud Group Chat Support

```json
"ecloud": {
  "group_chat": {
    "enabled": false,
    "context_message_count": 10,
    "whitelist_groups": ["xxx@chatroom"],
    "reply_mode": { "whitelist": "all", "others": "mention_only" }
  }
}
```

Message types: 80001 (text), 80002 (image), 80004 (voice), 80014 (reference/quote)

### GTD Task System

`reminders` collection supports GTD-style tasks:
- `list_id`: defaults to `"inbox"`, supports task organization
- `trigger_time`: can be `None` for tasks without a specific time
- Scheduled vs inbox tasks displayed separately

### Async/Concurrency Patterns

- Full async pipeline using `asyncio` with `agent.arun()` for LLM calls
- Distributed locks via `LockManager` with `acquire_lock_async()`
- Optimistic locking with safe lock release (only release own locks)
- Message interruption detection between workflow phases

## Coding Standards

- Black/Isort formatting (88 chars, 4-space indent)
- snake_case for modules/functions, PascalCase for classes, UPPER_SNAKE for constants
- Type hints on public functions
- Conventional commits: `type(scope): summary`

## Configuration

- Secrets in `.env` file (DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, BOCHA_API_KEY, STRIPE_*, CREEM_*, etc.)
- Runtime config in `conf/config.json` — values support `${ENV_VAR}` substitution
- `DISABLE_DAILY_AGENTS`, `DISABLE_BACKGROUND_AGENTS` env vars toggle background agent tasks
- `AGENT_WORKERS` env var controls worker count (default 3)

## Key Documentation

- `docs/architecture.md`: Architecture reference — layers, key design patterns, config
- `docs/schema.md`: MongoDB collection schemas
- `docs/deploy.md`: Deployment guide
- `docs/agent-prompt.md`: Agent prompt specification and standards
