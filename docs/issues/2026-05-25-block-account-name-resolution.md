---
title: Block and unblock account did not resolve friend name
status: blocked
kind: incident
affected_surfaces:
  - agent_runtime
  - gateway/packages/api/src/routes/internal-scheduling-routes.ts
---

# Block and unblock account did not resolve friend name

## What happened

Batch `20260525t050650Z` reached an active Alice/Bob friendship. Alice said
`屏蔽 Bob 的账号。`

The assistant replied with a friend-list summary instead of blocking Bob, and
Postgres showed no `account_blocks` row. A follow-up `把 Bob 的屏蔽解除。`
reported that Bob could not be found.

## Why it mattered

Users name people, not internal account ids. The block/unblock scheduling tools
must resolve a clear friend name to the target account before calling the
gateway service.

## Root cause

The model supplied `block_friend` with `friend_name=Bob`, but the runtime did
not normalize that alias to `block_account`. The internal gateway route also
only accepted `blocked_account_id`, so even a name-bearing tool call could not
resolve Bob.

## Fix

The runtime now normalizes `block_friend` and `unblock_friend` to the active
scheduling tools, including `action=block_user` / `action=unblock_user` payloads.
The gateway internal route resolves `friend_name` through active friendships
for blocking, and through existing account blocks for unblocking after the
friendship has already been removed.

Fix commit: not committed yet; live verification is blocked because the gateway
process is still serving the pre-fix route and gateway restart is outside this
dispatch's authorization.

## Verification

- `pnpm --dir gateway/packages/api test src/routes/internal-scheduling-routes.test.ts -- --runInBand`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_scheduling_intent_normalizes_block_friend_alias tests/unit/agent/test_agent_runtime_construction.py::test_scheduling_intent_normalizes_action_block_user_alias_with_args -q`

Blocked live check:

- Batch `20260525t051449Z` still failed user-path block/unblock after
  `pm2 restart coke-agent`.
- Direct POST to `/api/internal/scheduling/tools/block_account` with
  `customer_id=ck_smoke_20260525t051449Z_alice` and `friend_name=Bob`
  returned `400 invalid_account`, which matches the old route behavior that
  reads only `blocked_account_id`.
