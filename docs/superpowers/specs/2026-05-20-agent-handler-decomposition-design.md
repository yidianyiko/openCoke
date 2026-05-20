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
- Module-level constant: `typing_speed = 2.2` (moves with `_send_single_message`,
  which is its only caller).

**Public surface** (no leading underscore after move):
- `OutboundSendInterrupted` (exception)
- `chat_response_timeout_fallback(...)`
- `send_chat_response_fallback(...)`
- `send_single_message(...)`

**Dependencies:** `random`, `typing.Callable`, `typing.Optional`, `typing.Tuple`,
module logger, `agent.tool.image.upload_image`,
`agent.tool.voice.character_voice`, `agent.util.message_util.send_message_via_context`.

---

### `runtime_lock.py`

Owns the in-turn lock heartbeat loop and ownership verification. The module
holds the singleton `lock_manager = MongoDBLockManager()` so nothing else
needs to instantiate it, and owns the `LOCK_TIMEOUT` constant.

**Moved in:**
- `_agent_runtime_lock_heartbeat_interval_seconds() -> float`
- `_await_with_agent_runtime_lock_heartbeat(awaitable, *, lock_id, conversation_id, worker_tag) -> Any`
- `_verify_lock_ownership(conversation_id, lock_id) -> bool`
- Module-level: `lock_manager = MongoDBLockManager()`
- Module-level constant: `LOCK_TIMEOUT = 180` (currently in `agent_handler.py`
  line 60; runtime_lock is the only structural consumer).

**Public surface:**
- `agent_runtime_lock_heartbeat_interval_seconds(...)`
- `await_with_agent_runtime_lock_heartbeat(...)`
- `verify_lock_ownership(...)`
- `lock_manager`
- `LOCK_TIMEOUT`

`agent_handler.py` re-imports `lock_manager` and `LOCK_TIMEOUT` from
`runtime_lock` so existing references (e.g. `handle_message` calling
`lock_manager.renew_lock(...)` directly, and tests reading
`agent_handler.LOCK_TIMEOUT` / patching `agent_handler.lock_manager`) keep
working without an explicit re-export shim.

**Dependencies:** `asyncio`, `os`, `typing.Optional`, module logger,
`dao.lock.MongoDBLockManager`.

---

### `message_history.py`

Owns chat-history reads (extractor for prompt building) and writes
(embedding-storage background submission, sent-message append). Both
directions are grouped here because they share the conversation/chat_history
shape and nothing else touches them.

**Moved in:**
- `_embedding_executor = ThreadPoolExecutor(max_workers=4)`
- `_store_messages_for_retrieval_sync(context, resp_messages)`
- `store_messages_background(context, resp_messages)`
- `record_sent_messages_to_history(conversation, sent_messages) -> dict`
  (currently dead code — see Audit Notes; preserved on the move.)
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
  (currently dead code — see Audit Notes; preserved on the move.)

**Public surface:** both functions (already public in the original).

`agent_handler.py` re-imports `is_new_message_coming_in` from
`rollback_detection` so `handle_message` keeps calling it unqualified and
existing `monkeypatch.setattr(agent_handler, "is_new_message_coming_in", …)`
patches continue to take effect.

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

All callers that currently import a moved function from `agent_handler` will
be updated to its new canonical module. `agent_handler.py` keeps thin
re-imports only for the bindings that `handle_message` itself still calls
unqualified (`lock_manager`, `LOCK_TIMEOUT`, `is_new_message_coming_in`) — not
as backwards-compatibility shims for external callers.

Production callers (single source of truth: the new module):
- `agent/runner/agent_runner.py` — currently `from agent.runner.agent_handler
  import create_handler`. Stays on `agent_handler` (factory is not moving).
- `agent/runner/deferred_action_executor.py` — currently `from
  agent.runner.agent_handler import handle_message`. Stays on `agent_handler`
  (orchestrator is not moving).

### Test migration

The existing tests rely on `monkeypatch.setattr(agent_handler, "<name>", …)`
to swap moved helpers. After the split, the underscore-prefixed names
(`_send_single_message`, `_send_chat_response_fallback`,
`_chat_response_timeout_fallback`, `_verify_lock_ownership`) no longer exist
on `agent_handler`. The fix is **not just import paths**; the patches must
target the new modules at the call site. For each moved helper called by
`handle_message`, the option matrix is:

1. Patch the new module directly:
   `monkeypatch.setattr("agent.runner.output_delivery.send_single_message", …)`.
   Requires `handle_message` to call `output_delivery.send_single_message(...)`
   (or import-and-rebind the name on `agent_handler`).
2. Have `agent_handler.py` `from agent.runner.output_delivery import
   send_single_message` and call it unqualified; tests patch
   `agent_handler.send_single_message`.

This plan picks option (2) for the helpers `handle_message` calls directly,
because it preserves the existing test patch pattern with just a rename. The
following test files must be updated:

- `tests/unit/agent/test_agent_handler.py`
  - Replace `from agent.runner.agent_handler import _chat_response_timeout_fallback`
    with `from agent.runner.output_delivery import chat_response_timeout_fallback`.
  - Replace `monkeypatch.setattr(agent_handler, "_send_single_message", …)` with
    `monkeypatch.setattr(agent_handler, "send_single_message", …)`.
  - Replace `monkeypatch.setattr(agent_handler, "_send_chat_response_fallback", …)`
    with `monkeypatch.setattr(agent_handler, "send_chat_response_fallback", …)`.
  - Replace `monkeypatch.setattr(agent_handler, "_verify_lock_ownership", …)` with
    `monkeypatch.setattr(agent_handler, "verify_lock_ownership", …)`.
  - `agent_handler.lock_manager`, `agent_handler.LOCK_TIMEOUT`,
    `agent_handler.asyncio`, `agent_handler._run_agent_runtime_event`,
    `agent_handler._derive_agent_runtime_user_turn_occurred_at`,
    `agent_handler._agent_runtime_should_skip_post_analyze` remain valid
    after the refactor (re-imported or kept in place); no test change
    needed for these.
- `tests/unit/runner/test_agent_handler_inflight_interrupt.py` — same set of
  underscore-to-no-underscore patch target renames.

`tests/unit/test_clawscale_only_topology.py` reads `agent_handler.py` as text
to check it imports nothing from the legacy ClawScale surface; verify the
post-refactor file still satisfies that assertion.

## Verification

- `.venv/bin/python -m pytest tests/unit/runner/ tests/unit/agent/ -v`
- `.venv/bin/python -m pytest tests/e2e/ -v`
- `zsh scripts/check`
- `zsh scripts/suggest-verification --base HEAD~1` after each commit

## Non-Goals

- `message_processor.py` is not touched in this change.
- No behaviour changes. This is a pure structural refactor.
- No new test coverage. Existing tests get import-path updates and
  monkeypatch-target renames as described in **Test migration**; no new
  cases added.
- `_run_agent_runtime_event` wrapper removal is a follow-up, not in scope.
- Deleting dead code (`merge_pending_messages`,
  `record_sent_messages_to_history`) is out of scope. See **Audit Notes**.

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
  and `MongoDBLockManager`; `LOCK_TIMEOUT` is now owned by `runtime_lock.py`
  itself (see below), and `CONF` is not used by these functions.
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
- Flagged `merge_pending_messages` and `record_sent_messages_to_history` as
  having zero callers in the active tree (grep on the whole repo confirms
  only their own definitions in `agent_handler.py`). They are preserved on
  the move so this refactor stays purely structural; a follow-up should
  decide whether to delete them.
- Flagged that the existing test patch pattern (`monkeypatch.setattr(
  agent_handler, "_send_single_message", …)` and similar) breaks after the
  rename to public names. The **Test migration** subsection enumerates the
  required patch-target updates per file.
- Located `typing_speed = 2.2` (currently `agent_handler.py:63`); it is used
  only by `_send_single_message`, so it moves with that function into
  `output_delivery.py`.
- Located `LOCK_TIMEOUT = 180` (currently `agent_handler.py:60`); after the
  move it lives in `runtime_lock.py` and is re-imported by `agent_handler`
  so existing references — including the test assertion on
  `agent_handler.LOCK_TIMEOUT` — keep working.
