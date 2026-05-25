---
title: list_pending_shared_reminders reply leaks raw account_id instead of display name
kind: incident
date: 2026-05-25
status: fix_implemented_pending_verification
fix_commit: 7e7fbae0
affected_surfaces:
  - agent/agno_agent/runtime/execution_agents.py (scheduling worker reply summarizer)
  - agent/agno_agent/capabilities/scheduling.py (port reply post-processing)
  - gateway/packages/api/src/scheduling/shared-reminder-service.ts (listPendingSharedReminders projection)
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-badminton-20260525t045815Z.json (T09)
---

# Shared-reminder list leaks account_id to user — Bug H

## What happened

Batch `badminton-20260525t045815Z` T09. Bob asked Coke:

> 我有没有待处理的共享提醒？

Coke replied:

> 你有 1 个待处理的共享提醒：`ck_smoke_20260525t045815z_alice` 发来的"打羽毛球"。

The raw synthetic account id leaked into a user-visible message. Should have
been:

> 你有 1 个待处理的共享提醒：Alice Badminton 发来的"打羽毛球"。

## Why it matters

- Surfaces internal identifier shapes (`ck_smoke_...`, `ck_<base32>`) to end
  users. In production, that's the customer_id namespace — embarrassing UX
  papercut.
- Cross-platform pivot: a leaked id can be replayed via the public user-link
  surface to learn things about the requester. Low risk but real surface
  expansion.

## Root cause hypothesis

The `list_pending_shared_reminders` gateway response includes
`requesterAccountId` but does not project the requester's `displayName` into
the response payload (or the scheduling worker isn't substituting it). The
chat persona then has only the id to mention.

Check:
- `gateway/packages/api/src/scheduling/shared-reminder-service.ts::listPendingSharedReminders`
  — does it `include: { requester: { select: { displayName: true } } }` like
  the friendship_lookup helper does? If not, add it.
- `agent/agno_agent/runtime/execution_agents.py` scheduling worker — when
  building the user-facing summary, prefer `requester.displayName` over
  `requesterAccountId`.

## Suggested fix layer

1. Gateway: ensure the read projection includes `requester.displayName` and
   `invitee.displayName` for `list_pending_shared_reminders`.
2. Agent scheduling worker: substitute display_name in the
   `visible_summary` / `facts.summary` it returns to the chat persona.
3. Defense-in-depth: add a runtime check in
   `agent/agno_agent/runtime/agent_runtime.py` (or a util) that the final
   text emitted to the user does NOT contain a `ck_[a-zA-Z0-9_]{8,}` or
   `acct_[a-zA-Z0-9_]{8,}` pattern — fail the turn if it would have, and
   substitute or rephrase. Regression test covering the badminton T09 phrasing.

## Severity

Medium. UX-visible and a minor info-leak. Not blocking the closed loop.
