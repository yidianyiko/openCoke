---
title: agent_handler.py Decomposition
date: 2026-05-20
status: complete
spec: docs/superpowers/specs/2026-05-20-agent-handler-decomposition-design.md
---

# Execution Plan

## Steps

### Step 1 — Create rollback_detection.py
**Action:** Extract the new-message race helpers from `agent/runner/agent_handler.py` into `agent/runner/rollback_detection.py`. Keep the public names `is_new_message_coming_in(u_id, c_id, platform, current_message_ids)` and `merge_pending_messages(current_messages, new_messages)`. This module must be the smallest extraction and must not import from any other new module.
**Files:** Create `agent/runner/rollback_detection.py`; modify `agent/runner/agent_handler.py`.
**Verify:** Run `.venv/bin/python -c "import agent.runner.agent_handler"` and fix import errors before continuing.

### Step 2 — Create runtime_lock.py
**Action:** Extract lock lifecycle code into `agent/runner/runtime_lock.py`. Move `LOCK_TIMEOUT = 180`, `lock_manager = MongoDBLockManager()`, `_agent_runtime_lock_heartbeat_interval_seconds`, `_await_with_agent_runtime_lock_heartbeat`, and `_verify_lock_ownership`. Strip leading underscores in the new public module as `agent_runtime_lock_heartbeat_interval_seconds`, `await_with_agent_runtime_lock_heartbeat`, and `verify_lock_ownership`. Update `agent_handler.py` to import the public names it still calls.
**Files:** Create `agent/runner/runtime_lock.py`; modify `agent/runner/agent_handler.py`.
**Verify:** Run `.venv/bin/python -c "import agent.runner.agent_handler"` and fix import errors before continuing.

### Step 3 — Create message_history.py
**Action:** Extract message history and retrieval-storage helpers into `agent/runner/message_history.py`. Move `_embedding_executor = ThreadPoolExecutor(max_workers=4)`, `_store_messages_for_retrieval_sync`, `store_messages_background`, `record_sent_messages_to_history`, and `_extract_recent_chat_history`. Strip leading underscores in the new public module as `store_messages_for_retrieval_sync` and `extract_recent_chat_history`. Update `agent_handler.py` to import the public names it still calls.
**Files:** Create `agent/runner/message_history.py`; modify `agent/runner/agent_handler.py`.
**Verify:** Run `.venv/bin/python -c "import agent.runner.agent_handler"` and fix import errors before continuing.

### Step 4 — Create output_delivery.py
**Action:** Extract outbound delivery helpers into `agent/runner/output_delivery.py`. Move `typing_speed = 2.2`, `_OutboundSendInterrupted`, `_chat_response_timeout_fallback`, `_send_chat_response_fallback`, and `_send_single_message`. Strip leading underscores in the new public module as `OutboundSendInterrupted`, `chat_response_timeout_fallback`, `send_chat_response_fallback`, and `send_single_message`. Update `agent_handler.py` to import and call the public names.
**Files:** Create `agent/runner/output_delivery.py`; modify `agent/runner/agent_handler.py`.
**Verify:** Run `.venv/bin/python -c "import agent.runner.agent_handler"` and fix import errors before continuing.

### Step 5 — Slim agent_handler.py
**Action:** Remove the moved definitions from `agent/runner/agent_handler.py`, add imports from all four new modules, and update every local call site from the old private helper names to the new public names. Keep `handle_message`, `create_handler`, `_run_agent_runtime_event`, post-analyze helpers, timestamp helpers, `mongo`, and `post_analyze_workflow` in `agent_handler.py`.
**Files:** Modify `agent/runner/agent_handler.py`.
**Verify:** Run `.venv/bin/python -c "import agent.runner.agent_handler"` and use `rg` to confirm `agent_handler.py` no longer defines the moved symbols.

### Step 6 — Update import callers
**Action:** Audit and update imports or monkeypatch targets in `agent/runner/agent_runner.py`, `tests/unit/runner/test_agent_handler_inflight_interrupt.py`, and `tests/unit/agent/test_agent_handler.py`. Skip production caller files that only import unmoved `create_handler` or `handle_message`. In tests, only update import paths or renamed monkeypatch targets; do not change test behavior.
**Files:** Modify `agent/runner/agent_runner.py` if needed; modify `tests/unit/runner/test_agent_handler_inflight_interrupt.py`; modify `tests/unit/agent/test_agent_handler.py`.
**Verify:** Run `.venv/bin/python -c "import agent.runner.agent_handler"` and fix import errors before final testing.

### Step 7 — Run focused unit suite and fix broken imports
**Action:** Run the required focused unit suite. If it fails, change only broken imports or renamed patch targets caused by the extraction; do not change production behavior or test logic. Commit the refactor after the suite is passing or only failing for a clearly pre-existing unrelated reason.
**Files:** Modify only `agent/runner/rollback_detection.py`, `agent/runner/runtime_lock.py`, `agent/runner/message_history.py`, `agent/runner/output_delivery.py`, `agent/runner/agent_handler.py`, `agent/runner/agent_runner.py`, `tests/unit/runner/test_agent_handler_inflight_interrupt.py`, and `tests/unit/agent/test_agent_handler.py`.
**Verify:** Run `cd /data/projects/coke && .venv/bin/python -m pytest tests/unit/runner/ tests/unit/agent/ -v 2>&1 | tail -30`. Then run `git add agent/runner/rollback_detection.py agent/runner/runtime_lock.py agent/runner/message_history.py agent/runner/output_delivery.py agent/runner/agent_handler.py agent/runner/agent_runner.py tests/` and commit with the required refactor message.
