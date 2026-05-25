---
title: "Status query for shared reminder triggers empty fallback (我跟 X 那个 Y 现在是什么状态？)"
kind: incident
date: 2026-05-25
status: fix_implemented_pending_verification
fix_commit: 71bfd02e
affected_surfaces:
  - agent/agno_agent/runtime/chat_response_instructions.py (delegation boundary — status-query routing)
  - agent/agno_agent/runtime/agent_runtime.py (intent inference for status queries)
  - agent/agno_agent/capabilities/scheduling.py (list_pending_shared_reminders + possibly a new "lookup_shared_reminder_status" tool path)
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-badminton-20260525t045815Z.json (T11+T12)
---

# Bug B residual — shared-reminder status query gets empty fallback

## What happened

Batch `badminton-20260525t045815Z`, post-accept verification turns.

- T11 (Alice): `我跟 Bob 那个羽毛球的共享提醒现在是什么状态？` → 兜底
  `我没接住你刚才的意思。你可以换个说法再说一次吗？`
- T12 (Bob): `我跟 Alice 那个羽毛球的共享提醒现在是什么状态？` → 同兜底

Postgres shows the shared reminder is in `status=accepted`, mongo shows both
parties have active reminders. So the data exists; the assistant simply can't
route the query to read it.

## Why it matters

After Alice and Bob complete the entire booking flow, the most natural
follow-up question is "what's the status?". Every shared-reminder UX flow
ends here. Returning `我没接住你刚才的意思` undermines confidence in
everything the system just confirmed.

This is the same Bug B family that the v2 codex loop already addressed in
several other shapes (empty greeting, empty friend list, empty friend request
list, missing Agno content). The "status query" phrasing was not in the
training set / pattern covered.

## Suggested fix layer

There is no `get_shared_reminder_status(request_id)` tool currently; the
agent has only `list_pending_shared_reminders` (limited to invitee, pending
status). Status queries for ACCEPTED / REJECTED / CANCELLED reminders need
a path.

Options (in increasing scope):

1. **Prompt-only:** in `chat_response_instructions.py::_DELEGATION_BOUNDARY`,
   teach the chat persona that "status of my shared reminder with X" maps to
   `scheduling_domain(intent="list_shared_reminders_with_friend")` or similar.
   But the tool doesn't exist.
2. **New read tool:** add `list_shared_reminders` (parameterized by
   `friend_name` and an optional `status` filter). Wire through scheduling.py
   + execution_agents.py + gateway internal-scheduling-routes.ts. Update the
   chat persona prompt to route status queries to it.
3. **Fallback wording:** at minimum, extend
   `agent/runner/output_delivery.py::_chat_response_timeout_fallback` to
   recognize "状态" / "怎么样了" / "status" + "共享提醒" / "shared reminder"
   patterns and produce a more honest fallback like "我查不到当前共享提醒的
   状态，可能要先加上这项查询能力。"

Option 2 is the right product fix. Option 1+3 is a stopgap.

## Severity

Medium. Doesn't break the closed loop, but it's a natural follow-up the
user just successfully completed — silence here is jarring.

## Verification

After fix, replay T11/T12 from a fresh batch where the shared reminder is
accepted; expect responses naming the friend, title, time, and status
(`accepted`).
