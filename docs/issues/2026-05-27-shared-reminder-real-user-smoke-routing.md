---
title: Shared-reminder real-user smoke routes friend invite wording to reminder detector
kind: incident
date: 2026-05-27
status: active
affected_surfaces:
  - agent/agno_agent/runtime/chat_response_instructions.py
  - agent/agno_agent/runtime/agent_runtime.py
  - tests/unit/agent/test_chat_response_scheduling_instructions.py
  - tests/unit/agent/test_agent_runtime_construction.py
  - .agents/skills/production-real-user-flow-smoke/SKILL.md
---

# Shared-reminder real-user smoke routes friend invite wording to reminder detector

## Problem

Production real-user smoke on 2026-05-27 showed that not every natural
friend-invite wording reliably reaches shared-reminder creation.

The sentence `帮我约李梓豪，上海时间2029年1月1日10:00，标题是验收测试-...，持续5分钟。`
entered the interaction agent with both `reminder_domain` and
`scheduling_domain` available, then drifted into the reminder detector. The
reminder detector failed structured parsing with
`non-crud reminder decisions must not include executable fields`, no
`shared_reminder_requests` row was created, and the invitee received no invite.

## Background

The gateway/domain path is healthy. The same production accounts succeeded
through the canonical gateway tool: create returned a pending shared-reminder
request, invitee notification was delivered, accept returned `accepted`, and
the requester received a `shared_reminder_accepted` notification.

The remaining failure is therefore the natural-language agent routing surface,
not shared-reminder persistence, projection creation, or product notification
delivery.

## Initial Analysis

The active product contract is that a user can naturally ask Coke to schedule
with a friend. The wording does not have to contain the literal phrase
`shared reminder` when the target is a named friend and the appointment has a
concrete time/title/duration.

The current delegation boundary only clearly names `create / accept / reject /
cancel a shared reminder`. It does not explicitly define `帮我约/邀请 <friend>`
with a concrete appointment time as a `create_shared_reminder` directive. That
leaves the outer model room to choose the personal `reminder_domain`, where the
one-person reminder detector correctly rejects mixed non-crud executable
fields.

This is not a reason to reintroduce stale payload aliases such as
`start_time`, `scheduled_time`, or `friend_id`. The strict current
`create_shared_reminder` contract should stay intact.

## Proposed Fix

1. Add a repository skill that captures the production real-account smoke
   method so future verification starts from live route context, marked test
   data, product notification rows, and cleanup evidence.
2. Update the chat delegation boundary: `帮我约/邀请 <friend>` plus a concrete
   appointment time, title/activity, or duration is a
   `create_shared_reminder` directive even if the user does not say
   `shared reminder`.
3. Update the model-facing `scheduling_domain` tool description with the
   canonical create fields: `invitee_name`, `title`, `fire_at`, `timezone`,
   and `duration_minutes`.
4. Keep ordinary personal reminders such as "remind me to contact X tomorrow"
   on `reminder_domain`.
5. Deploy and rerun the real-user flow through `/bridge/inbound`, then verify
   the create row, invite notification, invitee accept, requester acceptance
   notification, and exact marked-data cleanup.

## Verification Plan

- Targeted unit tests for prompt/tool contract changes.
- Worker-runtime verification suggested by diff-aware routing.
- Production deploy with compose restart.
- Real-user olivers -> 李梓豪 create/accept smoke using a unique marker and
  cleanup through runtime reminder cancellation plus exact marked Postgres
  deletion.
