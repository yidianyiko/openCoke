---
title: Shared-reminder real-user smoke routes friend invite wording to reminder detector
kind: incident
date: 2026-05-27
status: resolved
resolved_at: 2026-05-27T04:53:08Z
fix_commits:
  - 34b290f9
  - 8e3b5c20
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

## Resolution

Implemented a two-layer fix:

- The prompt/tool contract now explicitly routes `帮我约/邀请 <friend>` with a
  concrete appointment time/title/duration to `scheduling_domain` as
  `create_shared_reminder`.
- The runtime now preselects `create_shared_reminder` for high-confidence
  direct friend-invite creates before the outer model can drift into friend
  availability or personal reminder paths.

The preselection deliberately stays narrow. It excludes personal contact
reminders such as `提醒我明天10点联系李梓豪约测试` and avoids treating
`预约一个活动` as a shared-reminder invite.

## Final Verification

Local verification:

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_preselects_friend_invite_with_concrete_time tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_does_not_preselect_personal_contact_reminder tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_does_not_preselect_activity_reservation_phrase -q`
  passed.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py::test_shared_reminder_invite_sent_claim_fails_closed_without_confirmed_write tests/unit/agent/test_agent_runtime_output_rules.py::test_shared_reminder_invite_sent_claim_requires_create_shared_reminder_write tests/unit/agent/test_agent_runtime_output_rules.py::test_shared_reminder_invite_sent_claim_allowed_after_create_write -q`
  passed.
- `zsh scripts/verify-surface repo-os-docs worker-runtime` passed:
  `scripts/check`, runner 67 tests, agent 528 tests, topology 7 tests.
- `git diff --check` passed.
- `zsh scripts/review-trigger --base HEAD~1` returned
  `human_review_required: no`.

Production deployment:

- `./scripts/deploy-compose-to-gcp.sh --restart` completed.
- Compose showed `coke-agent`, `coke-bridge`, and `gateway` running, with
  bridge/gateway healthy.
- Public `https://coke.keep4oforever.com/health` returned ok.
- Public `https://coke.keep4oforever.com/bridge/healthz` returned ok.

Real-user smoke:

- Marker: `server-smoke-20260527T044852Z`.
- Requester route: olivers, `ck_SXk_J0U0V5JKcK09QHEuo`, active route
  `bc_6a16459b790c7841638352b4`.
- Invitee route: 李梓豪, `ck_CsFu-A91jbCSBwtizPx1K`, active route
  `bc_6a1019b60fedec4719365fd5`.
- Friendship `cmpmw9gs60001ru1tc4y12851` was active.
- Requester bridge input:
  `帮我约李梓豪，上海时间2029年1月1日10:00，标题是验收测试-server-smoke-20260527T044852Z，持续5分钟。`
- Created request `cmpnl6hxz0001pl1tvmyyyhoq` with status
  `pending_invitee_confirmation`, fire_at `2029-01-01 02:00:00`,
  duration 5, requester reminder `6a167839e5522f8de29458d1`.
- B-side invite notification `shared_reminder_request` delivered to
  `ck_CsFu-A91jbCSBwtizPx1K`.
- Invitee bridge input with product notification focus:
  `确认这个系统测试邀约`.
- Accept response: `已接受共享提醒。`
- Final request status: `accepted`, requester reminder
  `6a167839e5522f8de29458d1`, invitee reminder
  `6a167884e5522f8de29458d3`, resolved at `2026-05-27 04:52:20.666`.
- A-side accepted notification `shared_reminder_accepted` delivered to
  `ck_SXk_J0U0V5JKcK09QHEuo` at `2026-05-27 04:52:21.258`.
- Both future runtime reminders were cancelled through bridge internal reminder
  API, then the exact marked shared request and its two product notifications
  were deleted. Follow-up counts for the marker and request notifications were
  both 0.

Evidence file:

- `artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-server-smoke-20260527T044852Z.md`
