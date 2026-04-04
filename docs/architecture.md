# Architecture Reference

## Runtime Flow

```text
External Platforms
  -> connector layer
  -> queue/input persistence
  -> agent runner
  -> three-phase workflow
  -> outputmessages / platform delivery
```

The main message path is:

1. Connectors normalize inbound messages.
2. Messages are stored in `inputmessages` and optionally pushed to Redis stream `coke:input`.
3. `agent/runner/agent_runner.py` consumes work through Redis stream mode or Mongo polling mode.
4. `agent/runner/agent_handler.py` runs:
   - `PrepareWorkflow`
   - `StreamingChatWorkflow`
   - `PostAnalyzeWorkflow`
5. Replies are emitted as `outputmessages` or sent back through the active connector.

## Main Components

### Connector Layer

- `connector/channel/`: shared adapter interfaces and message types
- `connector/adapters/`: platform-specific adapters
- `connector/ecloud/`: direct ecloud webhook/input/output flow
- `connector/gateway/`: gateway-side adapter management helpers
- `connector/terminal/`: local terminal test tooling

### Runner Layer

- `agent/runner/agent_runner.py`: worker entrypoint and background loops
- `agent/runner/agent_handler.py`: main turn handling
- `agent/runner/agent_background_handler.py`: reminders, hold recovery, background tasks
- `agent/runner/access_gate.py`: subscription/access checks

### Workflow Layer

- `PrepareWorkflow`: orchestration, retrieval, reminders, optional web search
- `StreamingChatWorkflow`: chat generation with streaming tag parsing
- `PostAnalyzeWorkflow`: post-turn analysis and memory updates

### Agent Layer

Pre-created agents in `agent/agno_agent/agents/__init__.py`:

- `orchestrator_agent`
- `reminder_detect_agent`
- `post_analyze_agent`

The chat agent used for streaming replies is created inside `chat_workflow_streaming.py`.

## Queue Modes

- Redis stream mode: uses `coke:input` and consumer group `coke-workers`
- Polling mode: reads pending work directly from MongoDB `inputmessages`

## Message State

### `inputmessages.status`

- `pending`: waiting to be processed
- `handled`: finished successfully
- `failed`: processing failed
- `hold`: temporarily paused because the conversation is busy or interrupted

Some tooling may still write `canceled`, but the main runtime path centers on the four states above.

### `outputmessages.status`

- `pending`
- `handled`
- `failed`

## Current Design Notes

- Locks are stored in MongoDB and used per conversation.
- `session_state` is the shared context bus across all three workflow phases.
- Reminder handling is split between preparation-time detection and background triggering.
- Web search and URL understanding are optional features controlled by workflow decisions and config flags.
