---
kind: issue
status: resolved
title: Friend availability production query violated gateway argument contract
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - production-smoke
  - agent-runtime
  - scheduling-domain
  - gateway
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-shared-smoke-20260527T085644Z.md
---

# Friend Availability Production Query Violated Gateway Argument Contract

## What Happened

The isolated production real-user friend availability query failed for marker
`happy-availability-20260527T121038Z`.

User input from `olivers`:

`看看李梓豪2029年1月1日上午有没有空？我想约他一起打羽毛球。测试编号happy-availability-20260527T121038Z。`

The production bridge returned a visible failure:

`查询李梓豪的空闲时间遇到了点问题，暂时无法完成。要不要我再试一次，或者你可以直接发个邀请给他？`

## Why It Matters

Friend availability is a read-only happy path. It should answer from
privacy-safe busy intervals and must not create reminders, shared reminder
requests, or product notifications. A 400 from the scheduling tool blocks the
real user path even though the gateway domain service can answer the same query
when called with the complete contract.

## Evidence

- Production logs showed `POST /api/internal/scheduling/tools/list_friend_calendar_facts`
  returning `400`.
- Postgres marker checks found no `shared_reminder_requests` or
  `product_notifications` for the marker.
- A direct production gateway call with `friend_name=李梓豪`,
  `from_date=2029-01-01`, `to_date=2029-01-01`, and `timezone=Asia/Tokyo`
  returned `200` with empty privacy-safe `busy_intervals`.
- The same direct gateway call without `timezone` returned
  `{"ok":false,"error":"invalid_body"}`.

## Root Cause

The production path exposed three contract gaps between the chat agent, the
scheduling worker, and the gateway:

- The capability adapter did not inject the viewer timezone for
  `list_friend_calendar_facts`.
- The worker tool schema allowed an empty `list_friend_calendar_facts` call
  instead of requiring `from_date`, `to_date`, and `timezone`.
- The outer `scheduling_domain` call did not expose friend/date/timezone
  arguments directly, so the first worker call could still lose the range.
- After those were fixed, live history showed one more payload mismatch:
  `from_date` and `to_date` reached gateway as ISO datetimes
  (`2029-01-01T00:00:00`, `2029-01-01T12:00:00`) while the internal route
  requires date-only `YYYY-MM-DD` fields.

The gateway behavior was correct: direct canonical calls with complete
date-only payloads returned `200`, and invalid bodies returned `400`.

## Fix

- Treat `list_friend_calendar_facts` as a viewer-timezone scheduling tool in
  the capability adapter.
- Give the worker a specialized required-argument
  `list_friend_calendar_facts` function schema.
- Expose `friend_name`, `target_account_id`, `from_date`, `to_date`, and
  `timezone` as explicit outer scheduling arguments.
- Normalize structured `from_date` / `to_date` values to date-only strings in
  the capability adapter before calling the internal gateway route.
- Keep all changes at structured tool/protocol boundaries; no natural-language
  case rules were added.

## Verification

Local regression tests:

- `.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_chat_response_scheduling_instructions.py -q`
  - `112 passed`

Deployment:

- `./scripts/deploy-compose-to-gcp.sh --restart`
  - remote health and public site checks passed

Production real-user retest:

- Marker: `happy-availability-fix4-20260527T124245Z`
- Input from `olivers`:
  `这是全新的独立测试，请不要参考前面失败次数。看看李梓豪2029年1月1日上午有没有空？我想约他一起打羽毛球。测试编号happy-availability-fix4-20260527T124245Z。`
- Bridge reply:
  `好消息，这次查成功了！李梓豪2029年1月1日上午是空的，没看到有其他安排。想约他几点打羽毛球？告诉我具体时间，我帮你发邀请给他。`
- Production logs showed
  `POST /api/internal/scheduling/tools/list_friend_calendar_facts` returning
  `200`.
- Postgres marker checks found no `shared_reminder_requests` and no
  `product_notifications` for the marker.

Result: resolved.
