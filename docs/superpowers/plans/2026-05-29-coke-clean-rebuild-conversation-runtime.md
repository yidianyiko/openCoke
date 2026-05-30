# Conversation Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** verification_blocked

**Verification Blocker:** Task 6 focused tests pass, and the broader
`clean-rebuild-backend` surface passed inside `zsh scripts/verify-surface
clean-rebuild-backend repo-os-docs`; however the same surface command failed in
`repo-os-docs` because `scripts/check` requires files under the empty `gateway`
and `memo-runtime` gitlinks. Attempting `git submodule update --init
--recursive gateway memo-runtime` started a network clone for `gateway` and was
stopped after it hung. No ownership-registry or legacy-domain files were edited
because Task 6 scope does not allow that.

**Goal:** Build the clean-rebuild conversation spine: durable inbound ordering, turn replay idempotency, freshness-safe outbound commits, outbox relay contracts, stream consumption, and Redis conversation locks.

**Architecture:** The domain service wraps a repository interface and exposes only typed conversation runtime operations. The in-memory repository is the self-contained unit-test adapter; it mirrors schema constraints from `coke/schema.py` without inventing tables. Outbox relay and stream consumer are infrastructure adapters over the durable `outbox` ledger; Redis is only a wake signal.

**Tech Stack:** Python 3.12, dataclasses, Protocol repositories, pytest, SQLAlchemy schema metadata, Redis-compatible client protocols.

---

## Files

- Create: `coke/domains/conversation_runtime/__init__.py`
- Create: `coke/domains/conversation_runtime/models.py`
- Create: `coke/domains/conversation_runtime/repository.py`
- Create: `coke/domains/conversation_runtime/service.py`
- Create: `coke/worker/__init__.py`
- Create: `coke/worker/outbox_relay.py`
- Create: `coke/worker/stream_consumer.py`
- Create: `coke/turn/__init__.py`
- Create: `coke/turn/locks.py`
- Create: `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`
- Create: `tests/unit/coke/conversation_runtime/test_outbox_relay.py`
- Create: `tests/unit/coke/conversation_runtime/test_schema_contract.py`
- Create: `tests/unit/coke/conversation_runtime/test_locks.py`

### Task 1: Write Failing Domain Tests

**Files:**
- Create: `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`
- Create: `tests/unit/coke/conversation_runtime/test_schema_contract.py`

- [x] **Step 1: Add service tests before implementation**

Write tests importing `ConversationRuntimeService`, `InMemoryConversationRuntimeRepository`, `InboundMediaInput`, and `ConversationRuntimeError`. Cover:

```python
def test_inbound_messages_increment_durable_latest_seq_and_preserve_media_reference():
    result1 = service.record_inbound(...)
    result2 = service.record_inbound(...)
    assert result1.message.seq == 1
    assert result2.message.seq == 2
    assert repository.get_conversation(result1.conversation.id).latest_inbound_seq == 2
    assert result1.media[0].agent_reference == {"type": "image", "label": "[image]"}

def test_turn_records_based_on_inbound_seq_and_replay_reconciles_existing_turn():
    first = service.start_turn(...)
    replay = service.start_turn(...)
    assert replay.turn.id == first.turn.id
    assert replay.replayed is True
    assert len(repository.turns_by_trigger_id) == 1

def test_stale_outbound_commit_records_superseded_and_never_no_reply_or_failed():
    stale_turn = service.start_turn(...)
    service.record_inbound(...)
    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.commit_reply(...)
    assert service.get_disposition(stale_turn.turn.id).disposition == "superseded"

def test_no_reply_is_only_intentional_and_not_failure_or_supersession():
    disposition = service.commit_no_reply(...)
    assert disposition.disposition == "no_reply"
    assert disposition.reason_code == "intentional_no_reply"

def test_outbound_segments_are_unique_by_turn_id_and_segment_index():
    service.commit_reply(..., segments=["one", "two"])
    with pytest.raises(ConversationRuntimeError, match="duplicate_outbound_segment"):
        service.repository.add_outbound_message(existing_segment)
```

Add schema-contract assertions against `coke.schema.metadata` that `message` has unique constraint `uq_message_turn_segment`, `turn` has unique `uq_turn_trigger_id`, `conversation` has `latest_inbound_seq`, `output_disposition` has one row per turn, `inbound_media.agent_reference` exists, and `outbox.status/processed_at/acked_at` exist.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime -v
```

Expected: fail during import because `coke.domains.conversation_runtime` and worker/turn modules do not exist yet.

### Task 2: Implement Conversation Runtime Domain

**Files:**
- Create: `coke/domains/conversation_runtime/models.py`
- Create: `coke/domains/conversation_runtime/repository.py`
- Create: `coke/domains/conversation_runtime/service.py`
- Create: `coke/domains/conversation_runtime/__init__.py`

- [x] **Step 1: Add dataclasses and literals**

Define `OutputDispositionState = Literal["replied", "no_reply", "pending_async_reply", "failed", "superseded"]`, `TERMINAL_DISPOSITIONS`, `NON_TERMINAL_DISPOSITIONS`, `Conversation`, `Message`, `InboundMedia`, `OutputDisposition`, `Turn`, `OutboxRecord`, `InboundMediaInput`, `InboundRecordResult`, `TurnStartResult`, and `ConversationRuntimeError`.

- [x] **Step 2: Add repository protocol and in-memory adapter**

Implement `ConversationRuntimeRepository` and `InMemoryConversationRuntimeRepository` with dictionaries keyed like the schema. Enforce unique `conversation.account_id`, unique `turn.trigger_id`, unique `output_disposition.turn_id`, unique `outbox.idempotency_key`, and unique outbound `(turn_id, segment_index)`.

- [x] **Step 3: Add service methods**

Implement:

```python
record_inbound(account_id, channel_identity_id, causal_inbound_event_id, text, payload, media, traceparent)
start_turn(conversation_id, trigger_id, trigger_type, mode)
commit_reply(turn_id, based_on_inbound_seq, segments, reason_code="reply_ready")
commit_no_reply(turn_id, based_on_inbound_seq, reason_code="intentional_no_reply")
mark_pending_async_reply(turn_id, based_on_inbound_seq, reason_code="sync_timeout")
mark_failed(turn_id, reason_code)
guard_state_change(turn_id, based_on_inbound_seq)
get_disposition(turn_id)
```

`record_inbound` increments `conversation.latest_inbound_seq` before storing the inbound message and appends one durable outbox row in the same repository operation. `start_turn` reconciles existing `trigger_id` and records `based_on_inbound_seq` from the current conversation. `commit_reply`, `commit_no_reply`, `mark_pending_async_reply`, and `guard_state_change` compare `based_on_inbound_seq` to the current conversation value before any state-changing commit; stale turns record `superseded` and raise `ConversationRuntimeError("turn_superseded")`. `commit_no_reply` accepts only `reason_code="intentional_no_reply"`.

- [x] **Step 4: Run domain tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/unit/coke/conversation_runtime/test_schema_contract.py -v
```

Expected: all selected tests pass.

### Task 3: Implement Outbox Relay, Stream Consumer, And Locks

**Files:**
- Create: `coke/worker/outbox_relay.py`
- Create: `coke/worker/stream_consumer.py`
- Create: `coke/worker/__init__.py`
- Create: `coke/turn/locks.py`
- Create: `coke/turn/__init__.py`
- Create: `tests/unit/coke/conversation_runtime/test_outbox_relay.py`
- Create: `tests/unit/coke/conversation_runtime/test_locks.py`

- [x] **Step 1: Add failing infrastructure tests**

Outbox tests should verify that unprocessed outbox rows are published to Redis with `event_id == outbox.id`, are not marked processed at publish time, become processed only after `ack_processed(event_id)`, and replay publishing is idempotent by event id.

Lock tests should verify `SET NX PX` acquisition with an ownership token, heartbeat extension only by owner, lock-loss instrumentation on failed heartbeat, and release only deletes when the owner token still matches.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_outbox_relay.py tests/unit/coke/conversation_runtime/test_locks.py -v
```

Expected: fail because `coke.worker` and `coke.turn` modules are not implemented.

- [x] **Step 3: Implement relay and consumer contracts**

Implement `OutboxRelay` with `publish_unprocessed(limit=100)` and `ack_processed(event_id)`. The relay calls repository methods to list wakeable rows, mark `published_at`, and mark `processed_at/acked_at` only after ack. Implement `StreamConsumer` as a small Redis consumer-group wrapper that reads messages and calls a handler with the durable event id; it must not own business rules.

- [x] **Step 4: Implement conversation lock**

Implement `ConversationLockManager.acquire(conversation_id)`, `ConversationLock.heartbeat()`, and `ConversationLock.release()`. Use Redis `set(key, token, nx=True, px=ttl_ms)`, compare the stored token before extending/deleting, and call the injected instrumentation callback with `{"event": "lock_loss", "conversation_id": ..., "token": ...}` when ownership is lost.

- [x] **Step 5: Run infrastructure tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_outbox_relay.py tests/unit/coke/conversation_runtime/test_locks.py -v
```

Expected: all selected tests pass.

### Task 4: Final Verification And Commit

**Files:**
- Modify this plan file to set all checkboxes complete and `Plan Status: complete`.
- Commit all task files.

- [x] **Step 1: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and confirm the focused conversation runtime tests are the relevant gate; `review-trigger` is non-blocking risk output.

- [x] **Step 2: Run full focused test command**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime -v
```

Expected: all conversation runtime tests pass.

- [ ] **Step 3: Update plan status after verification**

Only after the focused pytest command passes, change all checkboxes to `[x]` and set `Plan Status: complete`.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-conversation-runtime.md coke/domains/conversation_runtime coke/worker coke/turn tests/unit/coke/conversation_runtime
git commit -m "feat: implement turn ledger and outbox runtime"
```

Expected: one commit on `rebuild/t6-conversation-runtime`.

## Self-Review

- Spec coverage: durable inbound ordering, `based_on_inbound_seq`, stale commit rejection, `superseded` vs `no_reply`/`failed`, same-trigger replay, outbound uniqueness, inbound media references, outbox source-of-truth, and Redis locks all have direct test steps.
- Placeholder scan: no implementation step depends on unspecified tables, legacy imports, or fallback behavior.
- Type consistency: service and test method names match across tasks.
