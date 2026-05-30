# RR2 Redis Outbox Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Build the real Redis coordination layer for locks, worker wake streams, reply pub/sub, and the outbox relay ack contract.

**Architecture:** Postgres outbox remains the durable source of truth; Redis is only coordination and wake-up state. The relay XADDs unprocessed outbox rows idempotently by `event_id`, the worker consumes with a Redis Stream consumer group, and durable outbox processing happens only after handler success. Conversation locks use token-owned Redis operations so release and heartbeat cannot affect a lock owned by another worker.

**Tech Stack:** Python, redis-py 5, fakeredis for unit tests, pytest, Coke clean-rebuild schema and conversation-runtime outbox models.

---

## File Structure

- Modify `requirements.txt`: add `fakeredis` under test dependencies only.
- Modify `coke/infra/redis.py`: create the real `Redis` client factory, `RedisLockAdapter`, stream client, reply pub/sub helpers, and JSON-safe field encoding.
- Modify `coke/turn/locks.py`: tighten `RedisLockPort` to ownership-aware `extend_if_owned` and `release_if_owned` methods while preserving `ConversationLockManager` behavior.
- Modify `coke/worker/stream_consumer.py`: add consumer group setup, blocking reads, durable ack after injected turn handler success, and pending reclaim via `XAUTOCLAIM`.
- Modify `coke/worker/outbox_relay.py`: publish unprocessed outbox rows to Redis with deterministic IDs and dedup, but mark processed only through the worker ack callback.
- Add/modify tests under `tests/unit/coke/conversation_runtime/`: fakeredis-backed tests for lock ownership, stream produce-consume-ack, pending reclaim, reply pub/sub, and outbox replay idempotency.

### Task 1: Test Dependencies And Lock Adapter

**Files:**
- Modify: `requirements.txt`
- Modify: `coke/infra/redis.py`
- Modify: `coke/turn/locks.py`
- Modify: `tests/unit/coke/conversation_runtime/test_locks.py`

- [x] **Step 1: Write failing fakeredis lock tests**

Add tests that import `fakeredis` and `RedisLockAdapter`, then verify:

```python
redis = fakeredis.FakeRedis(decode_responses=True)
adapter = RedisLockAdapter(redis)
manager = ConversationLockManager(adapter, ttl_ms=30_000, token_factory=lambda: "owner-1")
lock = manager.acquire("conversation_1")
assert manager.acquire("conversation_1") is None
redis.set(lock.key, "owner-2", xx=True)
assert lock.heartbeat() is False
assert lock.release() is False
assert redis.get(lock.key) == "owner-2"
```

- [x] **Step 2: Run lock tests and confirm RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_locks.py -q`

Expected: fail because `fakeredis` or `RedisLockAdapter` is missing.

- [x] **Step 3: Implement minimal Redis lock adapter**

Implement `RedisLockAdapter.acquire()`, `get_token()`, `extend_if_owned()`, and `release_if_owned()` using `SET name token NX PX`, Lua compare-and-`PEXPIRE`, and Lua compare-and-`DEL`.

- [x] **Step 4: Run lock tests and confirm GREEN**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_locks.py -q`

Expected: all lock tests pass.

### Task 2: Stream Consumer And Reply Pub/Sub

**Files:**
- Modify: `coke/infra/redis.py`
- Modify: `coke/worker/stream_consumer.py`
- Add/modify: `tests/unit/coke/conversation_runtime/test_stream_consumer.py`

- [x] **Step 1: Write failing stream and pub/sub tests**

Add fakeredis tests that verify:

```python
stream = RedisWorkStream(redis, stream_name="coke.work", group_name="workers")
stream.ensure_group()
stream.publish(StreamEventInput(event_id="outbox_1", topic="turn.inbound", idempotency_key="inbound:outbox_1", traceparent=TRACEPARENT, payload={"trigger_id": "inbound:outbox_1"}))
consumer = StreamConsumer(redis_stream=stream, stream_name="coke.work", group_name="workers", consumer_name="worker-1", ack_callback=ack_processed)
assert consumer.poll_once(handler) == 1
assert acked == ["outbox_1"]
```

Also add a crash simulation where worker-1 reads without acking and worker-2 reclaims with `XAUTOCLAIM`, and a reply pub/sub round-trip keyed by a causal inbound event id.

- [x] **Step 2: Run stream tests and confirm RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_stream_consumer.py -q`

Expected: fail because real stream and pub/sub helpers are missing.

- [x] **Step 3: Implement stream and pub/sub helpers**

Implement group creation, `XADD`, `XREADGROUP`, `XACK`, `XAUTOCLAIM`, and reply publish/subscribe helpers in `coke/infra/redis.py`; update `StreamConsumer` to use them without importing `coke.turn.runner`.

- [x] **Step 4: Run stream tests and confirm GREEN**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_stream_consumer.py -q`

Expected: all stream and pub/sub tests pass.

### Task 3: Outbox Relay Ack Contract

**Files:**
- Modify: `coke/worker/outbox_relay.py`
- Modify: `tests/unit/coke/conversation_runtime/test_outbox_relay.py`

- [x] **Step 1: Write failing outbox replay tests**

Add tests that publish the same unprocessed outbox record twice and assert Redis receives only one stream entry for the same `event_id`, while the repository record remains unprocessed until the injected worker ack callback runs.

- [x] **Step 2: Run relay tests and confirm RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_outbox_relay.py -q`

Expected: fail because the relay still double-XADDs replays or lacks the new stream dedup contract.

- [x] **Step 3: Implement idempotent relay publishing**

Use the stream publisher's deterministic dedup key for `event_id`; mark `published_at` on publish attempts; mark `processed_at` and `acked_at` only from `ack_processed()`.

- [x] **Step 4: Run relay tests and confirm GREEN**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_outbox_relay.py -q`

Expected: relay tests pass.

### Task 4: Full Verification And Commit

**Files:**
- Modify: this plan file

- [x] **Step 1: Run full unit verification**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`

Expected: the full unit suite passes.

- [x] **Step 2: Update plan status**

Set `Plan Status` to `complete` only after the full verification command passes and all previous checkboxes are checked.

- [x] **Step 3: Commit coherently**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-rr2-redis-outbox.md requirements.txt coke/infra/redis.py coke/turn/locks.py coke/worker/stream_consumer.py coke/worker/outbox_relay.py tests/unit/coke/conversation_runtime
git commit -m "feat: add redis outbox runtime"
```
