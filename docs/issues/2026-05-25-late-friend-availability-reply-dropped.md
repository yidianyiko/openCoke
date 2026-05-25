---
kind: incident
status: resolved
owner: agent-runtime
created: 2026-05-25
resolved: 2026-05-25
---

# Late Friend Availability Reply Dropped

## What Happened

A user asked for friend availability:

> 嗯， eva 有什么时间有空吗？我想和他约一个共同时间去运动

Gateway accepted the inbound WeChat message at 2026-05-25 03:08:03 UTC, but
logged `No reply returned for message` after the bridge synchronous reply
window elapsed. The worker wrote a visible reply at 03:09:29 UTC, outside the
25 second request/response window. Bridge then attempted late reply promotion
and failed on `/api/internal/coke-delivery` with HTTP 409, leaving the output
message pending instead of dispatchable.

## Why It Matters

User-visible replies generated after the synchronous response window must still
be sent through the async push path. They must not be stranded because route
binding is already present, stale, or temporarily unavailable.

The same turn also showed the scheduling worker called `list_friends` but did
not reach `list_friend_calendar_facts`, so the assistant did not actually read
the friend's privacy-preserving calendar facts before replying.

## Current Evidence

- `inputmessages._id=6a13bd1377c9fa7c81c4d460`, `status=handled`
- `outputmessages._id=6a13bd695274073dc13ee6cb`, `status=pending`
- bridge log: `late_clawscale_reply_delivery_route_bind_failed`
- gateway log: `POST /api/internal/coke-delivery 409`
- gateway log: `POST /api/internal/scheduling/tools/list_friends 200`

## Root Cause

Three issues combined:

1. Late reply promotion treated delivery-route bind failure as a hard stop. If
   the worker produced a reply after the synchronous request/response window,
   a 409 from `/api/internal/coke-delivery` could leave the output in the old
   request/response pending shape instead of promoting it to async push.
2. Gateway delivery-route binding was not idempotent when the conversation was
   already bound to the requested Coke account and business conversation key.
3. The scheduling worker prompt allowed `list_friends` followed by
   `list_friend_calendar_facts`, but the execution guard allowed only one
   scheduling tool call, so unresolved friend availability could stop after
   `list_friends`.

## Fix

- Bridge late reply promotion now continues to mark the generated reply as an
  async push candidate even if delivery-route bind preflight fails.
- Gateway `bindBusinessConversation` now treats an already-bound
  conversation/key pair as idempotent and upserts the exact delivery route.
- Scheduling execution now allows the read-only sequence
  `list_friends -> list_friend_calendar_facts` while preserving the duplicate
  guard for other extra tool calls and write actions.

## Verification

- `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py -q`
- `pnpm --filter @clawscale/api test -- business-conversation.test.ts`
