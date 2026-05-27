# Shared Reminder Scheduling Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Stop shared-reminder invite false success by enforcing the current `create_shared_reminder` / `fire_at` contract, fixing same-turn scheduling call semantics, and grounding invite success claims on real writes.

**Architecture:** Keep the immediate repair inside the Agent runtime boundary. Make the existing `scheduling_domain(intent=...)` wrapper strict for current payloads, replace whole-turn result caching with normalized-call tracking, and strengthen final-output durable-write detection. Do not change gateway unless verification shows the gateway receives a bad canonical payload.

**Tech Stack:** Python 3.12, pytest, Agno tool wrappers, Coke domain result model, Docker Compose deploy script.

**Status:** Completed on 2026-05-27. Production deploy passed via
`./scripts/deploy-compose-to-gcp.sh --restart`; follow-up issue closeout is
tracked in
`docs/issues/2026-05-27-shared-reminder-scheduling-contract-fail-closed.md`.

---

### Task 1: Confirm Review Direction

**Files:**
- Modify: `docs/issues/2026-05-27-shared-reminder-scheduling-contract-fail-closed.md`

- [x] **Step 1: Record xhigh and Claude Code review results**

Append a `## Review Synthesis` section with accepted findings and rejected findings.

- [x] **Step 2: Keep the issue status active**

Do not mark resolved until tests, deploy, and production log/DB verification complete.

### Task 2: Add Failing Runtime Tests

**Files:**
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
- Modify: `tests/unit/agent/test_agent_runtime_output_rules.py`
- Modify: `tests/unit/agent/test_execution_agents.py`

- [x] **Step 1: Add non-canonical create payload rejection tests**

Add tests proving these model-shaped create payloads fail closed instead of being normalized:

```python
await scheduling_domain(
    intent={
        "create_shared_reminder_request": {
            "invitee_name": "Eva",
            "title": "奇迹创坛",
            "fire_at": "2026-05-27T11:00:00+09:00",
        }
    }
)
```

and:

```python
await scheduling_domain(
    intent={
        "create_shared_reminder": {
            "invitee_name": "Eva",
            "title": "奇迹创坛",
            "start_time": "2026-05-27T11:00:00+09:00",
        }
    }
)
```

Expected behavior after implementation: the tool returns a scheduling failure result and does not call `run_scheduling_domain`.

- [x] **Step 2: Add same-turn read-then-write execution test**

Add a test where the outer interaction agent calls:

```python
await scheduling_domain(intent={"list_friends": {}})
await scheduling_domain(
    intent={
        "create_shared_reminder": {
            "invitee_name": "Eva",
            "title": "奇迹创坛",
            "fire_at": "2026-05-27T11:00:00+09:00",
            "duration_minutes": 60,
        }
    }
)
```

Expected behavior after implementation: `run_scheduling_domain` is called twice, first with `list_friends`, then with `create_shared_reminder` and canonical forced args.

- [x] **Step 3: Add different write duplicate test**

Add a test where `accept_shared_reminder: request_id=srr_1` is followed by `accept_shared_reminder: request_id=srr_2`.

Expected behavior after implementation: the first call executes, the second returns a failure with `safety_boundary=duplicate_call` or `multiple_write_intents`, and `run_scheduling_domain` is called once.

- [x] **Step 4: Add write-then-read fail-closed test**

Add a test where a successful `create_shared_reminder` write is followed by
`list_friends`.

Expected behavior after implementation: the second call fails closed and does
not execute because a different scheduling call after a write is unsafe in the
same turn.

- [x] **Step 5: Add exact duplicate idempotency test**

Add a test where the same normalized write call is repeated twice.

Expected behavior after implementation: both calls return the first result and `run_scheduling_domain` is called once.

- [x] **Step 6: Add preloaded scheduling misuse test**

Add a test where `preloaded_scheduling_domain_result` exists for a preselected
scheduling intent and the model calls `scheduling_domain` with a different
intent.

Expected behavior after implementation: the call returns a typed scheduling
failure instead of reusing the preloaded result.

- [x] **Step 7: Add invite claim output-guard test**

Add a test where the final text is:

```python
"搞定了！今天上午11点去奇迹创坛的邀请已经发给 eva 了，等他确认～"
```

Expected behavior after implementation: without a successful scheduling write result, runtime returns `unconfirmed_durable_write_promise`.

- [x] **Step 8: Add claim-specific unrelated-write guard test**

Add a test where final text claims an invite was sent but `domain_results`
contains only an unrelated successful write, such as `accept_friend_request`.

Expected behavior after implementation: runtime still returns
`unconfirmed_durable_write_promise` because invite-sent claims require
`create_shared_reminder`.

- [x] **Step 9: Add scheduling write visible-summary test**

Add a test where a scheduling domain result contains `ok=True`,
`effect=write`, but no operation `visible_summary`.

Expected behavior after implementation: runtime returns
`durable_write_missing_visible_summary`.

- [x] **Step 10: Run focused tests and verify red**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_construction.py \
  tests/unit/agent/test_agent_runtime_output_rules.py \
  tests/unit/agent/test_execution_agents.py \
  -q
```

Expected: the newly added tests fail for the current implementation.

### Task 3: Implement Strict Scheduling Semantics

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Modify: `agent/agno_agent/runtime/scheduling_types.py` only if needed for a small canonical helper

- [x] **Step 1: Remove stale create alias normalization from the outer runtime**

Delete create-path normalization for stale compatibility fields that are not current contract:

```python
friend_id
friend_name -> invitee_name
reminder_title -> title
reminder_time -> fire_at
time -> fire_at
scheduled_time -> fire_at
start_datetime -> fire_at
date_time -> fire_at
duration -> duration_minutes
activity/location -> title
```

Keep canonical args only: `invitee_account_id`, `invitee_name`, `friend_account_id`, `friendship_id`, `title`, `fire_at`, `duration_minutes`, `timezone`, `idempotency_key`.

- [x] **Step 2: Fail closed for incomplete forced create args**

When a model supplies keyed `create_shared_reminder` args that lack a canonical counterparty, title, or `fire_at`, return a scheduling failure instead of delegating to the inner worker with partial args.

- [x] **Step 3: Replace whole-turn scheduling cache**

Track scheduling calls by normalized intent and forced args. Reuse only exact
duplicates. Allow read-to-write progression. Fail any different call after a
write, including write-to-write and write-to-read.

- [x] **Step 4: Keep the execution worker canonical**

Remove forced-arg alias normalization in `execution_agents._normalize_forced_scheduling_call` for stale create fields. Keep operation alias handling for accept/reject/cancel only if it is current focus semantics.

- [x] **Step 5: Strengthen durable-write promise detection**

Add output guard patterns for invitation/request sent, submitted, created, and waiting-for-confirmation wording.

- [x] **Step 6: Require create-specific grounding for invite claims**

When final text claims an invitation/request was sent or is waiting for invitee
confirmation, require a successful scheduling operation with
`action=create_shared_reminder`, `effect=write`, and `ok=True`.

- [x] **Step 7: Extend durable-write summary contract to domain writes**

Scheduling domain write operations must provide `facts.visible_summary` or the
runtime fails closed with `durable_write_missing_visible_summary`.

- [x] **Step 8: Run focused tests and verify green**

Run the same focused pytest command from Task 2. Expected: all selected tests pass.

### Task 4: Verification And Deploy

**Files:**
- Modify: `docs/issues/2026-05-27-shared-reminder-scheduling-contract-fail-closed.md`

- [x] **Step 1: Run diff-aware verification routing**

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [x] **Step 2: Run worker runtime verification**

```bash
zsh scripts/verify-surface worker-runtime
```

- [x] **Step 3: Run repository diff checks**

```bash
git diff --check
```

- [x] **Step 4: Deploy production stack**

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

- [x] **Step 5: Verify production health and logs**

Check compose service status, gateway health, bridge health, and recent logs for:

```text
scheduling intent could not be resolved
invalid_body
traceback
exception
```

- [x] **Step 6: Verify production shared-reminder behavior**

Use controlled live evidence or DB/log evidence to confirm a canonical shared-reminder create writes one `shared_reminder_requests` row with `pending_invitee_confirmation`, and that non-canonical payload failures do not produce success text.

- [x] **Step 7: Update issue and commit**

Update the issue with review synthesis, fix summary, verification results, deploy result, production evidence, and mark it resolved. Commit all changed files.
