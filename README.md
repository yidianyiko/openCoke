Project Coke

- Overview
  - Production chat flow uses Orchestrator → Context Retrieve Tool → ReminderDetect (on demand) → Streaming Chat → PostAnalyze (background).
  - Agents, prompts, schemas follow the three‑layer pattern defined in `doc/architecture/agent-prompt.md`.

- Deprecated / Removed
  - Removed pre-created `query_rewrite_agent` and non‑streaming `chat_response_agent` from `agent/agno_agent/agents/__init__.py`.
    - Reason: Not used in production runs. Orchestrator covers query rewrite; chat uses the streaming agent inside `StreamingChatWorkflow`.
    - Impact: No production impact. Tests that referenced them were removed/updated.
  - Still in production:
    - `orchestrator_agent`, `reminder_detect_agent`, `post_analyze_agent`
    - Future message pipeline: `future_message_query_rewrite_agent`, `future_message_context_retrieve_agent`, `future_message_chat_agent`

For development and testing guidance, see AGENTS.md and `tests/README.md`.

