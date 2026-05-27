---
title: Shared-reminder create loses timezone offset from structured intent args
kind: incident
date: 2026-05-26
status: resolved
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py
  - agent/agno_agent/runtime/focus.py
  - agent/agno_agent/runtime/semantic_interpreter.py
  - gateway/packages/api/src/scheduling/shared-reminder-service.ts
  - gateway/packages/api/src/routes/customer-scheduling-routes.ts
  - gateway/packages/api/src/routes/internal-scheduling-routes.ts
  - gateway/packages/api/src/lib/route-message.ts
  - tests/unit/agent/test_agent_runtime_construction.py
  - tests/unit/agent/test_focus_channel.py
  - tests/unit/agent/test_semantic_interpreter.py
  - gateway/packages/api/src/scheduling/shared-reminder-service.test.ts
  - gateway/packages/api/src/routes/customer-scheduling-routes.test.ts
  - gateway/packages/api/src/routes/internal-scheduling-routes.test.ts
  - gateway/packages/api/src/lib/route-message.test.ts
---

# Shared-reminder create loses timezone offset from structured intent args

## What happened

A production user asked to create a shared reminder with `eva` for
2026-05-26 22:30 local time. The invite delivery path succeeded, but the
stored shared reminder and invitee notification rendered the time as
2026-05-27 06:30 in `Asia/Shanghai`.

Live session evidence showed the interaction model had already supplied
`start_datetime=2026-05-26T22:30:00+08:00`, but the durable gateway row stored
`fire_at=2026-05-26T22:30:00.000Z`.

## Why it matters

Shared reminder creation must preserve the user's wall-clock intent. Losing
the offset creates a valid-looking invite at the wrong time, so the requester
sees success while the invitee receives misleading scheduling information.

## Root cause

`agent_runtime._normalize_scheduling_intent(...)` preserved nested
`create_shared_reminder` arguments as a normalized intent string, including
aliases such as `start_datetime -> fire_at`.

Immediately after that, `_split_scheduling_intent_args(...)` treated
`create_shared_reminder` as a special case and returned `forced_args=None`.
That discarded the already-structured args and caused the scheduling execution
worker to reconstruct the create payload instead of calling the capability with
the original offset-bearing datetime.

## Fix

Remove the `create_shared_reminder` split special case. Complete structured
create args are now passed as normalized `forced_args`, so the capability sees
the original `fire_at` value and the execution worker only handles incomplete
or ambiguous cases.

Follow-up hardening on the same incident closed the remaining system forks:

- Gateway now interprets offsetless shared-reminder `fireAt` values in the
  provided `timezone` instead of the Node process timezone.
- Customer scheduling shared-reminder create now forwards `durationMinutes`.
- `list_friend_calendar_facts` now fails closed when timezone is absent instead
  of silently defaulting to UTC.
- Product notification reply context now carries multiple pending candidates as
  `multi_pending` instead of binding the next short reply to only the latest
  delivered notification.
- Agent focus preserves product notification candidate lists, and the semantic
  interpreter now requires an LLM client for semantic classification. If that
  client is unavailable, focused accept/reject replies fail closed instead of
  being classified by a deterministic confirmation/rejection word list.

## Production Cleanup

On 2026-05-26, the five stale pending shared-reminder requests for
`ck_oO6k7XiefS3SePj8fsdUs` were cleared after backing up the rows under the
production `ops_cleanup` schema. The two future requester runtime reminders were
cancelled through the bridge first; the three older runtime reminder ids were no
longer valid for cancellation. The SQL delete then removed the shared reminder
requests and cascaded their product notifications, events, and projections.

Three failed smoke-account product notifications from 2026-05-25 were also
backed up under `ops_cleanup.failed_product_notifications_20260526` and
deleted. The production `product_notifications` table was left with only
`delivered` rows.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_forces_complete_shared_reminder_create_args tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_delegates_tool_key_create_args_to_worker tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_delegates_start_datetime_alias_to_worker tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_delegates_common_create_aliases_to_worker -q`
  now passes.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_scheduling_capability.py -q`
  passed.
- `zsh scripts/verify-surface repo-os-docs worker-runtime` passed.
- Production `coke-agent` and `gateway` were rebuilt and restarted with
  `docker compose -f docker-compose.prod.yml up -d --no-deps --build coke-agent gateway`.
- Production container verification confirmed the same structured
  `create_shared_reminder` intent now resolves to
  `forced_args.fire_at=2026-05-26T22:30:00+08:00`.
- Production compose status and gateway/bridge health endpoints were healthy
  after deployment.
- Post-cleanup production SQL checks showed zero remaining stale shared
  reminder requests for the invitee, zero remaining rows for the deleted bad
  request ids, and `product_notifications` contained only `delivered` rows.
- Gateway, agent, and bridge logs from the deploy window contained no matching
  `error`, `exception`, `traceback`, `invalid_body`, or
  `create_shared_reminder` failures.
- `pnpm --dir gateway/packages/api test src/scheduling/shared-reminder-service.test.ts src/routes/customer-scheduling-routes.test.ts src/routes/internal-scheduling-routes.test.ts src/lib/route-message.test.ts`
  passed after the hardening changes.
- `pnpm --dir gateway/packages/api build` passed.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_focus_channel.py tests/unit/agent/test_semantic_interpreter.py -q`
  passed.
