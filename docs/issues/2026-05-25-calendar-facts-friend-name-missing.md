---
title: list_friend_calendar_facts has no friend_name fuzzy lookup — feature unreachable
kind: incident
date: 2026-05-25
status: fix_implemented_pending_verification
fix_commit: a3e4a83c
affected_surfaces:
  - gateway/packages/api/src/routes/internal-scheduling-routes.ts (handler at line 450)
  - agent/agno_agent/runtime/scheduling_types.py (scheduling args)
  - agent/agno_agent/runtime/execution_agents.py (scheduling worker prompt)
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-badminton-20260525t045815Z.json (T07)
---

# Calendar facts friend_name fuzzy lookup missing — Bug G

## What happened

Real-user badminton scenario batch `badminton-20260525t045815Z`. Alice
became friends with Bob, then asked Coke:

> 看看 Bob 这周哪些时间空？我想约他一起打羽毛球。

Coke replied:

> 哎呀，目前日程功能暂时用不了，没法直接查看 Bob 的空档时间。看来得先问问他这周啥时候方便了，或者过会儿再试试看。

The entire reason Alice opened the conversation was to find a free time. The
calendar feature failed to surface. The assistant fell back honestly (no
hallucination), but the feature is unreachable from real user perspective.

## Why it matters

Calendar-facts negotiation is **the core mechanic** for "约朋友 X 时间一起 Y"
flows — exactly the use case the assistant's onboarding prompt advertises
("帮你约课，使用日历或预约能力，帮用户预约和彭教练的课程"). Without it, every
shared-reminder scheduling becomes blind guessing.

## Root cause

`gateway/packages/api/src/routes/internal-scheduling-routes.ts` line 450
exposes `list_friend_calendar_facts` requiring `target_account_id` only. No
`friend_name` fallback exists.

```ts
if (toolName === 'list_friend_calendar_facts') {
  return runCustomerTool(c, body, (customerId) =>
    listFriendCalendarFacts(
      db as never,
      { listRuntimeCalendarFacts },
      {
        requesterAccountId: customerId,
        targetAccountId: stringField(body, 'target_account_id'),
        ...
      },
    ),
  );
}
```

The agent has the friend's display name "Bob" (from the conversation) but no
way to obtain the friend's `account_id` short of calling `list_friends` first.
Every other scheduling tool that's been fixed (`accept_friend_request`,
`reject_friend_request`, `cancel_friend_request`, `accept_shared_reminder`,
`reject_shared_reminder`, `cancel_shared_reminder`, `remove_friendship`,
`create_shared_reminder`) accepts a `friend_name` / `invitee_name` /
`requester_name` argument and resolves it server-side via fuzzy lookup over
the actor's friend graph. `list_friend_calendar_facts` was missed.

## Minimal repro

```bash
# Friendship between Alice and Bob already active.
curl -sS -X POST http://127.0.0.1:4041/api/internal/scheduling/tools/list_friend_calendar_facts \
  -H "Authorization: Bearer $CLAWSCALE_IDENTITY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"<alice>","friend_name":"Bob"}'
# → {"ok":false,"error":"invalid_account"}

curl ... -d '{"customer_id":"<alice>","target_account_id":"<bob>"}'
# → ok=true with busy_intervals  ← works only with explicit account_id
```

## Suggested fix layer

Pattern is the same as `resolveInviteeAccountId` already in
`internal-scheduling-routes.ts`:

1. Add a `resolveFriendAccountId(body, requesterAccountId)` helper that:
   - returns `target_account_id` if explicitly set
   - otherwise reads `friend_name` (also accept aliases `target_name`, `name`)
   - looks up friendships for the actor, filters by display name match
   - fails closed with `friend_not_found` or `friend_name_ambiguous`
2. Use it in the `list_friend_calendar_facts` handler.
3. Add `friend_name` (and aliases) to `SharedReminderSchedulingArgs` in
   `agent/agno_agent/runtime/scheduling_types.py` if not already present.
4. Update the scheduling-worker system prompt in
   `agent/agno_agent/runtime/execution_agents.py` to mention: "for
   list_friend_calendar_facts without a known account_id, pass friend_name
   with the other person's name."
5. Regression test under
   `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`
   covering: explicit account_id (works), friend_name resolves (works),
   missing both (fails), ambiguous name (fails).

## Out of scope here

Bug I (personal reminders have no `duration_minutes`) is documented
separately. Once both Bug G and Bug I are fixed, calendar facts will actually
be useful — until then, even with G fixed, Alice will only see shared
reminders as busy slots.
