---
kind: verification_report
status: active
title: Real-user happy-path production smoke matrix
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - production-smoke
  - agent-runtime
  - reminder-runtime
  - scheduling-domain
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-realcase-corpus-smoke.md
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-server-smoke-20260527T044852Z.md
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-shared-smoke-20260527T085644Z.md
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-personal-crud-happy-path-smoke.md
---

# Real-User Happy-Path Production Smoke Matrix

## Scope

This matrix tracks happy-path scenarios that should be verified with real
repository case text, real production bridge input, real account identity, and
durable state checks. The current production test accounts are:

- `olivers` (`ck_SXk_J0U0V5JKcK09QHEuo`)
- `李梓豪` (`ck_CsFu-A91jbCSBwtizPx1K`)

Agent/local smoke evidence is useful for diagnosis, but it does not count as a
production real-user pass unless the row says the production bridge path was
used.

## Status Legend

- `passed-production`: verified through production `/bridge/inbound` with real
  account identity and durable state checks.
- `partial-production`: production bridge was used, but the row does not cover
  the whole happy path yet.
- `agent-local-only`: represented in local or agent smoke artifacts only.
- `missing-production`: no current production real-user evidence.

## Matrix

| Scenario | Source case or marker | Surface | Status | Evidence / Notes |
| --- | --- | --- | --- | --- |
| Shared reminder create, invite delivery, invitee accept, requester accepted notification, cleanup | `server-smoke-20260527T044852Z`, `shared-smoke-fix-20260527T092700Z` | production bridge, gateway scheduling domain, product notifications | passed-production | Create, invite notification, accept, requester accepted notification, projection route keys, and cleanup verified. |
| Shared reminder natural-language accept from corpus wording | `fix-shared-20260527T055525Z` | production bridge, scheduling domain | passed-production | Fixed after false-success regression; durable request became `accepted` and requester notification delivered. |
| Same-conversation rapid real messages | `fix-rapid-20260527T055333Z` | production bridge, worker acquisition | passed-production | Three concurrent real messages stayed isolated with `count=1` and produced three outputs. |
| Personal reminder create, delayed fire, outbound delivery route | `routefix-20260527T084358Z` | production bridge, reminder runtime, scheduler fire, gateway outbound | passed-production | Created reminder stored real route key; fire output became `handled`; gateway outbound returned `200`. |
| Personal reminder create then update | `crud-update-fix-20260527T072706Z` | production bridge, reminder runtime | passed-production | Create and update visible replies matched durable Mongo state; marked reminder was cleaned up. |
| Personal reminder cancel | `happy-cancel-20260527T093811Z` | production bridge, reminder runtime | passed-production | Create, cancel reply, durable cancelled state, and cleanup verified. |
| Personal reminder complete | `happy-complete-20260527T094118Z` | production bridge, reminder runtime | passed-production | Create, complete reply, durable completed state, and cleanup verified. |
| Personal reminder list/query | `happy-list-fix3-20260527T102900Z` | production bridge, reminder runtime | passed-production | Fixed schema query normalization and runtime list-summary grounding; list reply contained active marker, no technical issue text, no old cancelled markers, cleanup verified. |
| Batch personal reminders | `happy-batch-20260527T103200Z` | production bridge, reminder runtime | passed-production | Two future reminders were created, both durable `next_fire_at` values matched requested local times, and cleanup left `REMAINING_ACTIVE=0`. |
| Recurring personal reminder create/update/cancel | `happy-recurring-fix2-20260527T111900Z` | production bridge, reminder runtime | passed-production | Fixed missing recurring schedule authorization and inclusive end-date prompt contract; create/update/cancel all passed with durable RRULE and cleanup checks. |
| Shared reminder reject | `happy-reject-fix2-20260527T115204Z` | production bridge, gateway scheduling domain, product notifications | passed-production | Fixed title-based request resolution and requester `shared_reminder_rejected` notification; create, invite delivery, invitee reject, durable `rejected` state, requester rejection notification, projection cancellation, and cleanup verified. |
| Shared reminder cancel/status/list | `happy-shared-cancel-fix-20260527T120556Z` | production bridge, gateway scheduling domain, product notifications | passed-production | Fixed invitee `shared_reminder_cancelled` notification; create, invite delivery, list/status reply, requester cancel, durable `cancelled` state, projection cancellation, invitee cancellation notification, and cleanup verified. |
| Friend availability query | `happy-availability-fix4-20260527T124245Z` | production bridge, gateway scheduling domain | passed-production | Fixed timezone injection, required tool schema, explicit agent arguments, and date-only normalization; production bridge reply confirmed 李梓豪 was free, gateway returned `200`, and marker checks found no shared-reminder or notification side effects. |
| Friend/user-link happy path | `happy-friend-link-20260527T124508Z` | production bridge, gateway scheduling domain | passed-production | Production bridge returned olivers user-link and 李梓豪 friend list confirmed olivers; existing active friendship and active user links verified with no destructive cleanup needed. |
| Coach-booking unsupported/decline happy path | `happy-coach-decline-fix3-20260527T130832Z` | production bridge, reminder intent boundary, runtime output contract | passed-production | Fixed external booking boundary as a reminder-domain rejection with authoritative visible summary; production bridge reply declined direct booking, no visible reminder/shared request/product notification was created, and PostAnalyze logged no internal follow-up. |

## Next Queue

Run one production case at a time. Stop on the first product or harness bug,
preserve evidence, fix the root cause, deploy if needed, then rerun the same
case before continuing.

All queued happy-path production cases in this matrix are now
`passed-production`.
