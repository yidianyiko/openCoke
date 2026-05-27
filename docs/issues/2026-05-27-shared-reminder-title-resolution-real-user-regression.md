---
kind: progress_note
status: resolved
title: Shared reminder reject by title failed in real-user smoke
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - production-smoke
  - scheduling-domain
  - gateway
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-shared-smoke-20260527T085644Z.md
---

# Shared Reminder Title Resolution Regression

## Problem

Production real-user smoke with `olivers` and `李梓豪` exposed a shared
reminder reject failure.

- Marker: `happy-reject-20260527T112600Z`
- Requester input: `帮我约李梓豪，上海时间2029年1月30日10:00，标题是拒绝测试-happy-reject-20260527T112600Z，持续5分钟。`
- Create succeeded and sent an invite notification to `李梓豪`.
- Invitee input: `拒绝 拒绝测试-happy-reject-20260527T112600Z`
- User-visible reply: `找不到「拒绝测试-happy-reject-20260527T112600Z」这个共享提醒`
- Durable request stayed `pending_invitee_confirmation`.

The failed test row was cleaned up: the exact marked shared request was deleted
and the requester projection reminder `6a16d46524e5392f40e02904` was cancelled.

## Root Cause

The request reached the canonical gateway tool
`reject_shared_reminder`, so this was not a bridge delivery issue. Gateway
resolution for accept/reject/cancel shared reminders only matched pending
requests by counterparty display name, while the real invitee message identified
the pending invite by reminder title.

That made title-based reject/accept phrases fail whenever there was no request
id or focused notification context.

The first post-fix production rerun also exposed a requester notification gap:
the reject action correctly moved the durable request to `rejected` and
cancelled the requester projection, but no product notification was sent to the
requester. The accept path already had an idempotent
`shared_reminder_accepted` requester notification; reject lacked the symmetric
`shared_reminder_rejected` notification.

## Fix Direction

Keep the architecture domain-based:

- Preserve shared-reminder title as a canonical scheduling argument from the
  agent runtime.
- Teach the gateway shared-reminder resolver to filter pending requests by
  title, with the same fail-closed behavior on missing or ambiguous matches.
- Update the scheduling worker prompt to describe title as a supported entity
  identifier for accept/reject/cancel.
- Enqueue an idempotent `shared_reminder_rejected` product notification to the
  requester after a successful reject, and compensate it on rejected retries.

Do not add a Python natural-language phrase parser or case-specific Chinese
rule.

## Verification Plan

- Unit: agent runtime preserves `reminder_title` as `title` for shared reminder
  actions.
- Unit: gateway resolves `reject_shared_reminder` by title even when multiple
  pending invitee requests exist.
- Unit: shared reminder reject sends requester
  `shared_reminder_rejected` notification.
- Production: deploy and rerun a fresh `olivers -> 李梓豪` create plus invitee
  reject using a unique marker, then verify durable status, notifications, and
  cleanup.

## Verification Result

Local:

```bash
pnpm --filter @clawscale/api exec vitest run \
  src/scheduling/shared-reminder-service.test.ts \
  src/routes/internal-scheduling-routes.test.ts \
  src/scheduling/notification-service.test.ts
pnpm --filter @clawscale/api exec tsc -p tsconfig.json --noEmit
.venv/bin/python -m pytest \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_execution_agents.py \
  tests/unit/agent/test_agent_runtime_construction.py -q
```

Result:

- gateway related tests: `98 passed`
- TypeScript: passed
- Python scheduling tests: `115 passed`

Production:

- Deployed with `./scripts/deploy-compose-to-gcp.sh --restart`.
- Final passing marker: `happy-reject-fix2-20260527T115204Z`.
- Invitee reply confirmed rejection.
- Durable request `cmpo0any50001ns1u9xcd6gtr` became `rejected`.
- Requester reminder `6a16db6643dbe3c071262a82` was `cancelled`,
  `nextFireAt=null`.
- Invitee invite notification was delivered.
- Requester `shared_reminder_rejected` notification was delivered to `olivers`.
- Exact marked shared requests were deleted after verification.
