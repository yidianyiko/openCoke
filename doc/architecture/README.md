# Coke Architecture Overview

This document is the single source of truth for the current runtime architecture. Older, redundant documents have been removed to reduce drift and confusion.

## Overview
- Runtime is a background service started by `agent/runner/agent_start.sh`, which launches:
  - Multiple message workers handling user messages
  - A background loop for periodic tasks (reminders, proactive messages, housekeeping)
- Core Workflows (Agno-based):
  - `PrepareWorkflow` – gathers context, orchestrates prerequisite steps
  - `StreamingChatWorkflow` – generates responses with streaming output
  - `PostAnalyzeWorkflow` – updates relation, future message planning, and metadata

## Unified Message Pipeline
All message types (user, reminder, proactive/future) reuse the same workflow chain via the unified entrypoint:
1) `agent/runner/agent_background_handler.py` calls `handle_pending_future_message()` for due proactive messages.
2) `handle_message(..., message_source='future')` runs:
   - PrepareWorkflow → StreamingChatWorkflow → PostAnalyzeWorkflow
3) PostAnalyzeWorkflow can set `conversation.conversation_info.future` (timestamp/action), increment `proactive_times`, or expire future plans per limits.

Key files:
- `agent/runner/agent_background_handler.py`
- `agent/runner/agent_handler.py` (defines `handle_message`)
- `agent/agno_agent/workflows/{prepare_workflow,chat_workflow_streaming,post_analyze_workflow}.py`

## Proactive Messages (Future)
Production uses the unified pipeline above; there is no separate “FutureMessageWorkflow” on the runtime path.
- Future planning lives in `conversation.conversation_info.future`.
- Background loop triggers when `future.timestamp` is due, respecting limits and statuses.
- Chat generation uses future-specific prompt templates and personality inside `StreamingChatWorkflow`.

## Removed Components
To simplify the system and avoid duplication:
- Removed: `FutureMessageWorkflow`
- Removed: `ProactiveMessageTriggerService`
- Rationale: production already uses the unified `handle_message` pipeline for proactive messages; keeping parallel code paths caused drift.

Migration/Tests:
- Tests referencing the removed workflow or service have been pruned or rewritten to validate schemas and prompts without invoking deprecated paths.
- E2E tests that require real network or MongoDB are environment-dependent and are not part of the quick local suite.

## Testing
- Quick suite: `pytest -m "not integration" -v` (note: E2E that require network/DB may fail in sandboxed environments)
- Coverage target: 70%+
- Integration/E2E rely on configured API keys and accessible MongoDB when executed in CI/real envs.

## Notes
- Agents for “FutureMessage” (query rewrite, context retrieve, chat) remain defined for reuse and prompts, but the system no longer orchestrates them via a dedicated workflow.
- For future changes, update this file and keep it authoritative.

