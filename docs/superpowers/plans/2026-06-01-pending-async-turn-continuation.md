# Pending Async Turn Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Waiting replies keep slow turns visible without closing the original turn or allowing stale background work after a newer inbound message.

**Architecture:** Treat `pending_async_reply` as an intermediate, non-terminal disposition. It records the waiting output but leaves the interactive turn active until the final reply, failure, or supersession closes it. Repository active-turn queries must include pending async turns so a newer inbound can supersede them before any state-changing command materializes.

**Tech Stack:** Python domain services, SQLAlchemy repositories, pytest unit tests, Coke repo-OS verification.

---

### Task 1: Capture The Regression

**Files:**
- Modify: `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`
- Modify: `tests/unit/coke/worker/test_waiting_reply.py`

- [x] **Step 1: Add a failing conversation-runtime test**

Add a test that records an inbound, starts an interactive turn, marks
`pending_async_reply`, then stages and commits a shared-reminder command. Assert
that the command can be staged, materialized on final reply, and only then
advances `last_closed_inbound_seq`.

- [x] **Step 2: Add a stale-pending safety test**

Add a test that records an inbound, starts a turn, marks `pending_async_reply`,
records a newer inbound, and then attempts to stage a command on the old turn.
Assert the old turn becomes `superseded`, any staged commands are not
materialized, and the conversation window remains open for the replacement
turn.

- [x] **Step 3: Run the focused tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_pending_async_reply_allows_original_turn_to_stage_and_commit_final_reply tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_new_inbound_supersedes_pending_async_turn_before_state_change tests/unit/coke/worker/test_waiting_reply.py::test_waiting_reply_dispatches_after_budget_and_final_reply_can_still_close -q
```

Expected: at least one new test fails because `pending_async_reply` currently
sets `completed_at` and advances `last_closed_inbound_seq`.

### Task 2: Fix Pending Async Semantics

**Files:**
- Modify: `coke/domains/conversation_runtime/service.py`
- Modify: `coke/domains/conversation_runtime/repository.py`

- [x] **Step 1: Keep pending async non-terminal in service state**

Change `mark_pending_async_reply()` so it validates freshness and saves the
`pending_async_reply` disposition without materializing staged commands,
advancing `last_closed_inbound_seq`, or setting `turn.completed_at`.

- [x] **Step 2: Let pending turns remain interruptible**

Change both in-memory and Postgres `active_interactive_turns()` to include
interactive turns whose disposition is absent or `pending_async_reply`, while
still requiring `completed_at is null`.

- [x] **Step 3: Let newer inbound supersede pending turns**

Change `_record_superseded()` so an existing `pending_async_reply` disposition
can transition to `superseded`, mark staged commands `superseded`, set
`superseded_by_inbound_seq`, and close the old turn.

- [x] **Step 4: Keep final close guarded**

Ensure final `commit_reply()` from `pending_async_reply` still calls the same
freshness guard before materializing staged commands and delivering user-visible
final output.

- [x] **Step 5: Run focused tests and confirm GREEN**

Run the same focused pytest command from Task 1.

### Task 3: Delivery Observability And Docs

**Files:**
- Modify: `coke/worker/waiting_reply.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/issues/2026-06-01-pending-async-closes-stateful-turn.md`

- [x] **Step 1: Distinguish waiting dispatch from delivery success**

Keep the deterministic waiting idempotency key. Log whether the delivery return
status was `sent`, `delivered`, or `failed`. Do not add blind retries in this
change because the provider idempotency table already treats the first attempt
as authoritative and a retry design needs duplicate-message policy.

- [x] **Step 2: Update architecture wording**

Update `docs/ARCHITECTURE.md` so `pending_async_reply` is described as a
non-terminal intermediate disposition that does not close the input window by
itself. Final reply, no-reply, failure, or supersession closes the turn.

- [ ] **Step 3: Update issue status after verification**

Record the fix commit and verification commands in the issue after the commit
exists.

### Task 4: Verification And Commit

**Files:**
- Runtime and docs changed above.

- [x] **Step 1: Run focused tests**

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/unit/coke/worker/test_waiting_reply.py -q
```

- [x] **Step 2: Run diff-aware routing**

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [x] **Step 3: Run routed surface checks**

Run the backend and docs checks suggested by the routing output.

- [ ] **Step 4: Commit**

```bash
git add coke/domains/conversation_runtime/service.py coke/domains/conversation_runtime/repository.py coke/worker/waiting_reply.py tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/unit/coke/worker/test_waiting_reply.py docs/ARCHITECTURE.md docs/issues/2026-06-01-pending-async-closes-stateful-turn.md docs/superpowers/plans/2026-06-01-pending-async-turn-continuation.md
git commit -m "fix: keep waiting replies from closing active turns"
```
