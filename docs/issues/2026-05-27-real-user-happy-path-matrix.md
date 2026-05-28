---
kind: verification_report
status: active
title: Real-user happy-path production smoke matrix
created_at: 2026-05-27
updated_at: 2026-05-28
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

## Evidence Standard Update - 2026-05-28

The previous matrix was too coarse for shared-reminder/product-notification
flows. A shared-reminder happy path now requires separate evidence for:

- requester synchronous Interaction Agent reply for the original user turn,
  with no `fallback_kind=system_failure`;
- durable shared-reminder row and both runtime projections;
- structured `product_notifications.payload.facts` plus `facts_hash`, with no
  stored final prose `text`;
- worker product-notification `outputmessages` row with matching
  `notification_id`, matching facts, and `status` not `failed`;
- Gateway/provider reconciliation to `product_notifications.status='delivered'`;
- cleanup by Scheduling cancellation, not manual deletion.

Provider failures such as `wechat_send_failed ret=-2`, only failed Mongo
output rows for a notification, or notification rows stuck at
`pending_delivery` do not count as delivery passes, even if the domain row was
created. A notification with both successful and failed output rows is not
clean happy-path evidence; record it as partial and investigate the duplicate
or retry path. For recently changed shared-reminder paths, use at least two
marked natural-language phrasings: one machine-like smoke title and one normal
chat title. Record each marker as `passed-production`, `partial-production`, or
`failed-production` by layer.

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
| Direct active shared reminder receiver delivery/cleanup after direct-friendship migration | `server-smoke-20260528T072443Z` | production bridge, gateway scheduling domain, product notifications, provider outbound | partial-production | Post-deploy create wrote active `shared_reminders` row `sr_a0315788583d121c33986771b885bee5c3f78b79`; receiver `shared_reminder_created` notification `cmpp66ybn0007nv1uob2cfqb0` had `facts/facts_hash`, no payload `text`, worker output `6a17ee5082acc95e8d838c96`, and reconciled `delivered`; cleanup cancel succeeded and receiver cancellation notification `cmpp68hvc000env1uf66hpfys` delivered. The requester sync reply was fallback, so this is receiver-delivery evidence only, not a full shared-reminder happy-path pass. |
| Direct active shared reminder normal-title requester reply | `zhsmoke073047` | production bridge, gateway scheduling domain, requester interaction LLM, provider outbound | partial-production | Normal chat title created and requester got non-fallback LLM reply output `6a17efbb82acc95e8d838e38`; durable shared reminder `sr_c56e8a3b2864163d9d15eb5bdba7ad7632fe8a3c` was created and then cancelled through Scheduling. Receiver notification output `6a17efbb82acc95e8d838e3d` failed at provider with `wechat_send_failed ret=-2`, leaving notification rows pending, so this does not count as receiver delivery evidence. |
| Direct active shared reminder reverse direction with normal phrasing | `dirsmoke074102` | production bridge, gateway scheduling domain, requester interaction LLM, product notifications, provider outbound | partial-production | `olivers -> 李梓豪` created `sr_3ff9d3cf41a1c05ae354ceda8f5e3001052bd15c` and cleanup cancellation succeeded. Receiver create and cancel notification rows delivered with facts/hash and no payload `text`. The requester output `6a17f22482acc95e8d8390d6` was system fallback, the create notification output `6a17f22a82acc95e8d8390e1` was generic onboarding text instead of facts-derived reminder text, and `duration_minutes` was null despite the user saying `持续5分钟`. Cancellation also produced mixed output rows for the same notification, including one failed row, so this is not clean happy-path evidence. |
| Direct active shared reminder alternate receiver route | `multismoke075200` | production bridge, gateway scheduling domain, requester interaction LLM, product notifications, provider outbound | partial-production | Interrupted smoke still reached production. `李梓豪 -> eva` created `sr_094f735558746f6aed1af28df14058a87b05481e` with correct `duration_minutes=5`; cleanup cancellation succeeded. The requester output `6a17f30382acc95e8d8391ee` was system fallback. Receiver create notification `cmpp6wrwh001pnv1uuzoddfk2` and cancel notification `cmpp7vb1h001wnv1ufnfwy90s` stayed `pending_delivery`; create output `6a17f30a82acc95e8d8391fb` failed and gateway logs showed `wechat_send_failed ret=-2`. This proves durable creation/cancel but not requester reply or receiver delivery. |

## Next Queue

Run one production case at a time. Stop on the first product or harness bug,
preserve evidence, fix the root cause, deploy if needed, then rerun the same
case before continuing.

The 2026-05-28 direct shared-reminder path is not a single blanket pass. The
newer stricter checks split requester reply, durable creation, facts payload,
worker text generation, provider delivery, and cleanup. More marked cases have
already found requester fallback, facts-to-text drift, a dropped duration in
one direction, mixed output rows for one notification, and provider `ret=-2`.
Continue running one case at a time under the stricter evidence standard, and
do not promote the direct shared-reminder path to full happy-path pass until a
single marker satisfies every required layer.
