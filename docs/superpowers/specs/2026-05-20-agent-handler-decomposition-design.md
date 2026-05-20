---
title: agent_handler.py Decomposition
date: 2026-05-20
status: draft
---

# agent_handler.py Decomposition Design

## Problem

`agent/runner/agent_handler.py` is 966 lines and carries seven distinct
responsibilities simultaneously: lock lifecycle, rollback detection, agent
runtime orchestration, output delivery, post-analyze scheduling, message
history storage, and the worker factory. No single file should be this wide;
a reader cannot understand one concern without scanning all 966 lines.

Goal: **职责清晰** — each file does one thing, and a new reader can understand
one stage of the pipeline by reading one file.

## Target Layout

All files live under `agent/runner/`.

```
agent/runner/
├── agent_handler.py        # orchestrator/factory (~550 lines)
├── output_delivery.py      # outbound send      (~135 lines)  NEW
├── runtime_lock.py         # lock lifecycle     ( ~90 lines)  NEW
├── message_history.py      # history storage    (~125 lines)  NEW
├── rollback_detection.py   # new-message guard  ( ~40 lines)  NEW
├── message_processor.py    # unchanged
└── agent_runner.py         # unchanged
```

## Module Contracts

### `output_delivery.py`

Owns everything that puts bytes on the wire for a single agent turn.

**Moved in:**
- `_OutboundSendInterrupted` (exception class)
- `_chat_response_timeout_fallback(input_message, context=None) -> str`
- `_send_chat_response_fallback(*, context, input_message, expect_output_timestamp, all_multimodal_responses) -> tuple[dict | None, int]`
- `_send_single_message(context, multimodal_response, expect_output_timestamp, is_first=False, interrupt_check=None) -> tuple[dict | None, int]`

**Public surface** (no leading underscore after move):
- `OutboundSendInterrupted` (exception)
- `chat_response_timeout_fallback(...)`
- `send_chat_response_fallback(...)`
- `send_single_message(...)`

**Dependencies:** `random`, `typing.Callable`, `typing.Optional`, `typing.Tuple`,
module logger, module `typing_speed`, `agent.tool.image.upload_image`,
`agent.tool.voice.character_voice`, `agent.util.message_util.send_message_via_context`.

---

### `runtime_lock.py`

Owns the in-turn lock heartbeat loop and ownership verification. The module
holds the singleton `lock_manager = MongoDBLockManager()` so nothing else
needs to instantiate it.

**Moved in:**
- `_agent_runtime_lock_heartbeat_interval_seconds() -> float`
- `_await_with_agent_runtime_lock_heartbeat(awaitable, *, lock_id, conversation_id, worker_tag) -> Any`
- `_verify_lock_ownership(conversation_id, lock_id) -> bool`
- Module-level: `lock_manager = MongoDBLockManager()`

**Public surface:**
- `agent_runtime_lock_heartbeat_interval_seconds(...)`
- `await_with_agent_runtime_lock_heartbeat(...)`
- `verify_lock_ownership(...)`
- `lock_manager` (re-imported where needed)

**Dependencies:** `asyncio`, `os`, `typing.Optional`, module logger,
module `LOCK_TIMEOUT`, `dao.lock.MongoDBLockManager`.

---

### `message_history.py`

Owns retrieval-storage writes and the in-memory chat-history extractor.

**Moved in:**
- `_embedding_executor = ThreadPoolExecutor(max_workers=4)`
- `_store_messages_for_retrieval_sync(context, resp_messages)`
- `store_messages_background(context, resp_messages)`
- `record_sent_messages_to_history(conversation, sent_messages) -> dict`
- `_extract_recent_chat_history(chat_history, limit) -> str`

**Public surface:**
- `store_messages_for_retrieval_sync(...)`
- `store_messages_background(...)`
- `record_sent_messages_to_history(...)`
- `extract_recent_chat_history(...)`

**Dependencies:** `copy`, `ThreadPoolExecutor`, module logger,
`agent.runner.identity.get_agent_entity_id`,
`util.embedding_util.store_chat_message`.

---

### `rollback_detection.py`

Owns the "is a new message racing in?" detection and pending-message merge.

**Moved in:**
- `is_new_message_coming_in(u_id, c_id, platform, current_message_ids) -> bool`
- `merge_pending_messages(current_messages, new_messages) -> list`

**Public surface:** both functions (already public in the original).

**Dependencies:** `entity.message.read_all_inputmessages`.

---

### `agent_handler.py` (after)

Orchestrator plus existing worker factory. The turn path should read as "call X
to do Y" with implementation details moved out.

**Keeps:**
- Module-level: `mongo` and `post_analyze_workflow` (used only here)
- `_run_agent_runtime_event(...)` — thin wrapper around
  `agent.agno_agent.runtime.event_adapter.run_agent_runtime_event`. Current
  production callers do not import this wrapper directly: `agent_runner.py`
  imports `run_agent_runtime_event` from the public `agent.agno_agent.runtime`
  re-export and injects it into reminder/deferred typed runtimes, while
  `handle_message()` calls the local wrapper and unit tests monkeypatch it
  through `agent_handler`. Direct import from
  `agent.agno_agent.runtime.event_adapter` can replace the wrapper in a
  follow-up.
- `_agent_runtime_should_skip_post_analyze() -> bool`
- `_run_post_analyze_background(context, conversation_id, worker_tag)` — stays
  because it is tightly wired to handle_message control flow and has no
  independent callers.
- `_latest_input_message_timestamp(context) -> int | None`
- `_derive_agent_runtime_user_turn_occurred_at(context) -> datetime`
- `handle_message(...)` — the pipeline orchestrator (unchanged signature)
- `create_handler(worker_id) -> Callable` — worker factory

**After refactor, handle_message reads as a sequence of well-named calls:**

```python
async def handle_message(context, input_message_str, ...):
    # setup
    # pre-runtime rollback check  (rollback_detection)
    # lock renew                  (runtime_lock)
    # agent runtime               (await_with_agent_runtime_lock_heartbeat)
    # post-runtime rollback check (rollback_detection)
    # send output                 (output_delivery)
    # history storage             (message_history)
    # post-analyze                (_run_post_analyze_background)
    # return
```

## Import Updates

All callers that currently import from `agent_handler` will be updated to the
new canonical source. No compatibility re-exports.

Files to audit for import changes:
- `agent/runner/agent_runner.py`
- `agent/runner/deferred_action_executor.py`
- `tests/unit/runner/test_agent_handler_inflight_interrupt.py`
- `tests/unit/agent/test_agent_handler.py`

## Verification

- `.venv/bin/python -m pytest tests/unit/runner/ tests/unit/agent/ -v`
- `.venv/bin/python -m pytest tests/e2e/ -v`
- `zsh scripts/check`
- `zsh scripts/suggest-verification --base HEAD~1` after each commit

## Non-Goals

- `message_processor.py` is not touched in this change.
- No behaviour changes. This is a pure structural refactor.
- No new tests beyond fixing broken import paths in existing tests.
- `_run_agent_runtime_event` wrapper removal is a follow-up, not in scope.

## Audit Notes

- Corrected target line estimates from the actual `agent_handler.py` function
  ranges: `agent_handler.py` remains about 550 lines after this narrow split,
  output delivery is about 135 lines, runtime lock about 90, message history
  about 125, and rollback detection about 40.
- Corrected output-delivery function signatures and added
  `chat_response_timeout_fallback(...)` to the public surface because it is a
  moved function and is directly imported by an existing unit test.
- Corrected output-delivery dependencies to the actual helpers used by
  `_send_single_message()` and fallback sending; removed unused DAO and `CONF`
  dependencies.
- Corrected runtime-lock public names to the actual names after dropping the
  leading underscore, including
  `await_with_agent_runtime_lock_heartbeat(...)`.
- Corrected runtime-lock dependencies to `asyncio`, `os`, `Optional`, logger,
  `LOCK_TIMEOUT`, and `MongoDBLockManager`; `CONF` is not used by these
  functions.
- Corrected message-history dependencies to the actual embedding, copy, thread
  pool, logger, and identity helpers, and added
  `store_messages_for_retrieval_sync(...)` to the moved public surface.
- Corrected rollback-detection dependencies to
  `entity.message.read_all_inputmessages`; it does not use `MongoDBBase` or
  `ConversationDAO`.
- Corrected the `agent_handler.py` retained module-level objects: `mongo` and
  `post_analyze_workflow` are used there, while `conversation_dao` and
  `user_dao` are currently unused after earlier extraction.
- Corrected the post-analyze helper signature and the runtime heartbeat helper
  name in the orchestrator sketch to match the actual code.
- Corrected the `_run_agent_runtime_event` wrapper note: production reminder
  and deferred typed runtimes receive `run_agent_runtime_event` from
  `agent_runner.py`, which imports the public `agent.agno_agent.runtime`
  re-export; the local wrapper itself calls
  `agent.agno_agent.runtime.event_adapter.run_agent_runtime_event`.
- Corrected the import audit list to the files returned by the required grep:
  `agent_runner.py`, `deferred_action_executor.py`,
  `tests/unit/runner/test_agent_handler_inflight_interrupt.py`, and
  `tests/unit/agent/test_agent_handler.py`.
