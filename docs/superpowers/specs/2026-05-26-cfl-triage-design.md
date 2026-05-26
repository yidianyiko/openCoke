---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: smoke-triage-design
source_evidence: artifacts/evidence/shared-reminder-agent-smoke/cross-feature-long-20260526t023700Z.json
source_runner: tools/agent_smoke/_runner_phase_cross_feature_long_conversation.py
---
# Cross-feature long-conversation smoke triage design
## Scope
This spec triages the 10 CFL smoke findings from
`cross-feature-long-20260526t023700Z.json`. It does not propose product-code
changes, runner-code changes, compatibility shims, model swaps, or
`blockAccount` revival.
The dominant pattern is real user-visible failure under long conversation and
cross-feature pressure. Some runner logic also makes the report harder to read:
it collapses per-turn evidence into concatenated reply blobs, tags any fallback
token anywhere in a case as `B`, and can poll a non-final output row as a late
reply.
## Section 1: Per-case triage
### L1 - Reminder lifecycle full
Classification: REAL PRODUCT BUG.
Failing layers: context handling and reminder executor argument normalization;
secondary reply assembly drift.
Evidence:
- T3 (`刚才那个提醒晚 10 分钟`) did not resolve the just-created drinking
  reminder. `reminder_domain` received empty args, returned
  `AmbiguousReminderKeyword`, and the reply asked which reminder.
- T4 (`刚才那个提醒现在是什么状态`) called `reminder_domain` with list-style
  args and received `ReminderDetectInvalidDecision`; the visible reply said it
  could not find the previous reminder.
- T5 correctly modified the Mongo reminder (`delta.reminders.modified=1`) but
  the visible smoke reply was `已创建提醒...09:00`, while the agent trace final
  text says it was changed to daily 09:00. This is visible reply assembly drift.
- T9 and T11 lost the completed/cancelled backreference. T9 again produced
  `ReminderDetectInvalidDecision`; T11 produced the real empty fallback
  `我没接住...` with no placeholder timeout.
- T13 had `placeholder_received=true` and `late_reply_landed=true`; the final
  late reply still failed to summarize DB state, so this is not a late-poll
  placeholder artifact.
### L2 - Mixed reminder types
Classification: REAL PRODUCT BUG.
Failing layers: intent/list executor and reply assembly.
Evidence:
- T1-T4 created and listed one-shot, daily, and weekly reminders correctly.
- T5 modified the daily reminder in Mongo, but the smoke-visible reply was
  `已创建提醒...08:30` while the trace final says the daily reminder was changed.
- T9 (`每周三那个还在吗`) should have answered from the active weekly reminder.
  The first `reminder_domain` call used `operation=list, query=weekly`, returned
  `ReminderDetectInvalidDecision`, then duplicate-call errors followed.
- T10 (`喝水现在几点`) returned the real empty fallback with no placeholder.
- T12 (`最后列出我的提醒`) returned a list failure even though the final active
  title was `复盘`.
### L3 - Long context with backreference
Classification: MIXED.
Real failing layers: long-context backreference handling and reminder list
executor.
Runner artifact: the case observed string reports `tail_reply=` by joining the
last two replies with `_reply_text(ctx.turns[-2:])`. The suspicious text is not
one concatenated assistant response; it is T19 plus T20 collapsed by the runner.
Evidence:
- T1-T10 created 10 distinct reminders and T11 listed all 10, including first
  `浇花 07:00` and last `备份文件 16:00`.
- T19 (`我刚才设的第一个提醒是几点`) had `placeholder_received=true` and
  `late_reply_landed=true`; the late real reply still said no reminder record
  was found. The trace shows `reminder_domain operation=list from_date=2026-05-26
  to_date=2026-05-26`, then `ReminderDetectInvalidDecision`, even though all
  reminders were for 2026-05-27.
- T20 (`最后一个呢`) was a separate turn with no placeholder. It called
  `reminder_domain` with empty args, then attempted a bogus duplicate
  `title=test` call and asked what "last one" meant.
### L4 - Friend + shared reminder bootstrap
Classification: REAL PRODUCT BUG.
Failing layers: timezone rendering, shared-reminder modification routing, and
context handling.
Evidence:
- T4 created one `shared_reminder_requests` row and one requester reminder.
  The tool facts stored `fireAt=2026-05-27T01:00:00.000Z`, `timezone=UTC` for a
  user request phrased as local 10:00.
- T5 accepted the request; final storage had an accepted shared row and two
  Mongo reminders.
- T6 and T7 listed the accepted shared reminder through `scheduling_domain` but
  rendered it as Beijing 09:00 instead of user-visible 10:00.
- T8 attempted `modify_shared_reminder`, but scheduling execution failed with
  `no_tool_called`. The agent then modified the requester Mongo reminder via
  `reminder_domain`, not the shared request/projection pair, and used a wrong
  same-day `new_time=2026-05-26T10:30:00`.
- T9 Bob's backreference lost the shared-reminder context and fell into
  duplicate `reminder_domain` calls.
- T10 reported no pending shared reminders, which is technically true for an
  accepted row but not the requested final shared-reminder list.
### L5 - Three-way coordination
Classification: MIXED.
Real failing layers: multi-invitee shared-reminder cardinality, shared-reminder
list executor, and context handling.
Runner artifacts: `B` is an over-broad case tag caused by one fallback turn;
the real primary bug is `X5`. T14 also shows late-reply polling can attach a
pending/stale output row: `turn_evidence.reply_text` says `已创建提醒...
2026-05-26 15:00`, while the trace final says it changed to Sunday 2026-05-31.
Evidence:
- Setup produced two active friends; T6 listed both Bob and Carol.
- T7 sent `friend_names=["Bob","Carol"]` into `scheduling_domain`, but only one
  `shared_reminder_requests` row was created for Bob. The reply falsely said
  Carol needed to be added as a friend.
- T8 (`刚才发给几个人了`) could not answer the previous operation count and
  bounced across `reminder_domain`, unresolved `scheduling_domain`, and
  `url_context`.
- T9 and T10 pending-list checks failed in gateway Prisma
  `shared-reminder-service.ts:1326` rather than returning the pending request.
- T11 Bob accepted the only created request; T12 Carol correctly could not find
  a request, proving one invitee was dropped.
- T13 answered friend-request status instead of shared-reminder confirmation
  status.
- T14 modified a requester Mongo reminder, not the multi-party shared request;
  tool facts show `local_date=2026-05-26` despite the user saying Sunday.
### L6 - Friend remove mid-flow
Classification: MIXED.
Real failing layer: reply assembly raw envelope leak.
Runner artifact: the case did not exercise the intended pending-reminder
invalidation contract because T4 failed to create the shared reminder. The
runner should classify the invalidation path as blocked once the prerequisite
shared request is absent, while still recording the raw envelope leak.
Evidence:
- T4 (`约 Bob 明天 18:00 讨论方案`) called `scheduling_domain` with an
  unsupported wrapper shape (`intent_type=create_shared_reminder`) and returned
  `scheduling intent could not be resolved`; no shared row was created.
- T8 removed the friendship; final `active_friendships=0` is correct.
- T11 (`接受 Alice 刚才发来的方案提醒`) returned a raw serialized
  `MultiModalResponses` JSON array to the user instead of plain text.
- Because no pending request existed before removal, the reported
  `shared_statuses=[]` does not prove the friend-removal invalidation behavior.
### L7 - Friend vs shared reminder
Classification: REAL PRODUCT BUG.
Failing layers: timezone rendering, pending-list executor, and context routing.
Evidence:
- T5 correctly routed `约 Mei 明天 10 点` to `create_shared_reminder`; storage
  added one shared row and one requester reminder.
- The stored row uses `fire_at=2026-05-27T01:00:00`, `timezone=UTC`, and the
  Mongo reminder schedule is `local_time=01:00:00`, `timezone=UTC`. The user
  asked for 10:00 local.
- T6 (`刚才是加好友还是约提醒`) misread the previous successful create and asked
  whether the user meant friend-add or reminder.
- T7 Mei's pending-list check failed in gateway Prisma
  `shared-reminder-service.ts:1326`.
- T11 final shared list rendered the reminder as 01:00.
- T12 status routed to `reminder_domain` instead of `scheduling_domain` and
  asked for clarification even though one pending row existed.
### L8 - Reminder vs shared reminder
Classification: REAL PRODUCT BUG.
Failing layers: reminder list intent, shared-reminder pending/list executor,
and shared-reminder modification execution.
Evidence:
- T4 created a personal 14:00 reminder.
- T5 (`列出我的个人提醒`) called `reminder_domain operation=list,
  reminder_type=personal`; it returned `ReminderDetectInvalidDecision`.
- T6 created a shared 15:00 reminder with Bob, distinct from the personal
  reminder.
- T7 Bob's pending-list turn produced the real empty fallback with no tool call.
- T8 tried to verify the personal 14:00 reminder but interpreted it as today
  2026-05-26 instead of tomorrow 2026-05-27, then hit duplicate-call errors.
- T10 repeated the personal-list failure.
- T12 claimed the shared reminder was changed to 15:30, but deltas show no
  Mongo or Postgres modification. The trace repeatedly listed/cancelled/created
  intents against `scheduling_domain` and hit the tool-call limit.
- T13 could not confirm the two existing reminders.
### L9 - Capability boundary stretch
Classification: REAL PRODUCT BUG.
Failing layers: friend-name/entity resolution and unsupported-capability
intent filtering.
Evidence:
- T4 refused ticket booking correctly and T5 created the personal drinking
  reminder.
- T6 (`帮我点外卖`) returned the real empty fallback instead of a clear
  unsupported-capability refusal.
- T7 stock lookup refused, but only after unnecessary `url_context` and
  `reminder_domain` calls.
- T8 (`帮我约 Alex 教练明天 10 点`) should have resolved active friend Alex and
  created a shared reminder. Instead it sent `friend_name="Alex 教练"` to
  `create_shared_reminder` and failed with `friend_not_found`.
- T15 and later status/final-list turns could not recover because no shared row
  existed.
### L10 - Persona consistency
Classification: REAL PRODUCT BUG.
Failing layers: reply assembly and reminder list intent.
Evidence:
- T1 and T2 are user-visible fallback replies for basic persona questions.
  The T1 trace contains an attempted persona answer but malformed
  `MultiModalResponses` JSON; T2 trace contains a valid capability answer, but
  the delivered late reply is still `我没接住...`.
- T5 (`列出我的提醒`) failed with `ReminderDetectInvalidDecision` after a
  reminder existed.
- T6 modified the reminder in Mongo, but the visible smoke reply said
  `已创建提醒...08:30`; trace final says the reminder was changed.
- T7 and T11 generated useful capability/persona text in trace, but the
  delivered reply was the empty fallback.
- T8 ticket booking returned fallback instead of an unsupported-capability
  refusal.
- T10 and T12 could not list or confirm reminder state after successful create,
  update, and cancel operations.
## Section 2: Real-bug clusters
### Empty fallback in long conversations
Affected cases: L1, L2, L3, L5, L8, L9, L10.
This is not a single smoke placeholder artifact. Many fallback turns have
`placeholder_received=false`, and placeholder turns with `late_reply_landed=true`
still land real user-visible failures. The common product pattern is:
- The Interaction Agent often calls `reminder_domain` with empty, malformed, or
  list-shaped args for status/list/persona follow-ups.
- `ReminderDetectInvalidDecision` and duplicate-call guardrails then cascade.
- Reply assembly sometimes drops or replaces good final trace text with the
  generic fallback.
- Context handling loses the prior entity or prior operation after unrelated
  turns, especially for "刚才那个", "第一个", "最后一个", and "发给几个人".
Next investigation should separate three causes with the same captured turns:
model-side empty/fallback generation, domain executor rejecting list/status
shapes, and output assembly choosing fallback despite non-empty final text.
### Time / timezone rendering
Affected cases: L4 and L7, with related update-date drift in L5 and L8.
The strongest evidence is shared-reminder creation with local 10:00 producing
stored `fireAt=2026-05-27T01:00:00.000Z`, `timezone=UTC`, then visible replies
rendering that as Beijing 09:00 or raw 01:00 instead of the user's requested
10:00. The likely failure is split:
- Shared-reminder executor normalizes local input into UTC storage but loses
  the user/account display timezone in returned facts.
- Reply summary renders returned UTC facts directly or applies a hard-coded
  Beijing offset.
- Modification paths sometimes parse relative dates as same-day 2026-05-26
  even when the original reminder was tomorrow/Sunday.
### Raw envelope leak in friend-remove
Affected case: L6.
T11 returned a serialized `MultiModalResponses` list as the final visible
reply. The scheduling executor had failed cleanly with
`shared_reminder_name_not_found`; the leak is in reply assembly/output
normalization, not in the domain operation itself.
### Multi-invitee shared reminder
Affected case: L5.
The tool accepted `friend_names=["Bob","Carol"]`, but execution created one
request for Bob and then claimed Carol was not a friend despite setup/list
evidence showing two active friends. This is a real cardinality bug. The next
iteration should decide the product contract explicitly: either reject
multi-invitee requests before writes, or create one independent pending request
per invitee. It must not partially write one invite and describe the other as a
friendship problem.
### Shared-reminder pending/list executor
Affected cases: L5 and L7, related L8.
Pending shared-reminder list queries failed with a Prisma error in
`gateway/packages/api/src/scheduling/shared-reminder-service.ts:1326`. This is
an executor/backing API bug, not a smoke runner assertion. It blocks invitee
visibility and downstream accept/status verification.
## Section 3: Smoke runner fixes
These are runner assertion/reporting fixes, not product weakening:
- Report per-turn fallback evidence instead of appending
  `; empty fallback surfaced` to the case observed string. Include
  `fallback_turns=[...]`, placeholder flags, and whether each fallback was a
  sync placeholder, a late real reply, or a normal output.
- Move `BLOCKED-LATE-REPLY-TIMEOUT` classification ahead of blank/empty
  fallback checks in `_base_bug_pattern`. A true timeout should never become
  bug pattern `B`.
- Stop using `_reply_text()` for verdict-specific snippets such as L3
  `tail_reply`. Store `{turn, note, reply_text}` arrays so two turns are not
  presented as one reply blob.
- In `poll_late_reply_text`, do not accept non-final output rows. Require the
  matching causal output to be handled/final, or keep polling. L5 T14 shows a
  pending row can be treated as the late landed reply even though the trace has
  a different final assistant text.
- When a case prerequisite fails, mark the dependent contract path blocked
  while preserving independent findings. L6 should say "shared-reminder
  invalidation not exercised because create failed" plus "raw envelope leak at
  T11".
- Keep primary bug tags specific. If a case has a real `X5`, `X1`, or raw
  envelope leak plus an incidental fallback turn, the primary `bug_pattern`
  should remain the contract failure and fallback should be secondary evidence.
## Section 4: Recommended fix order
1. Fix shared-reminder timezone rendering and stored/display timezone facts
   (L4, L7). This is highly visible, small enough to verify through existing
   shared-reminder create/list turns, and likely unblocks several X1 cases.
2. Fix shared-reminder pending/list executor Prisma failure (L5, L7, L8). This
   blocks invitee visibility and makes accept/status flows unreliable.
3. Fix reply assembly/output normalization for empty fallback and raw envelope
   leaks (L1, L2, L6, L10). User-visible wrong output has broad impact, and the
   evidence shows good trace text can be lost before delivery.
4. Fix reminder list/status intent contract for read-only reminder queries
   (L1, L2, L3, L8, L10). This is systemic but should be tackled after reply
   assembly is trustworthy enough to read failures.
5. Fix shared-reminder modification routing so accepted/shared reminders update
   the shared request/projections coherently instead of only a requester
   personal reminder (L4, L8, L5).
6. Resolve multi-invitee shared-reminder contract (L5): either explicit refuse
   with no writes, or one pending request per invitee.
7. Improve entity resolution for role-qualified friend names such as
   `Alex 教练` (L9). This is useful but narrower than timezone/list/reply
   assembly failures.
8. Patch runner reporting and late-poll logic before rerunning the next hunt,
   so new evidence does not blur product bugs with reporting artifacts.
## Section 5: Reviewable summary
- The 10/10 FINDING result is not just a smoke artifact; most cases contain
  real user-visible product failures.
- L3's suspicious `tail_reply` is a runner concatenation artifact, but T19 and
  T20 are still two separate real backreference failures.
- L6 did not exercise pending-reminder invalidation because creation failed;
  its raw `MultiModalResponses` leak is still a real reply assembly bug.
- The `B` pattern is over-broad. It should become per-turn secondary evidence
  unless the case's primary contract failure is truly empty output.
- Shared-reminder time rendering is the highest-impact fix: local 10:00 becomes
  UTC 01:00 storage and is displayed as 01:00 or Beijing 09:00.
- Pending shared-reminder listing has a real gateway Prisma failure, blocking
  invitee status flows.
- The next iteration should fix runner reporting/polling, then rerun focused
  CFL slices after product fixes for timezone, shared pending lists, reply
  assembly, and reminder read-only list/status handling.
