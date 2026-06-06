---
kind: investigation
status: open
title: Eva 2026-06-06 chat root-cause analysis
created_at: 2026-06-06
updated_at: 2026-06-06
surface:
  - clean-rebuild
  - conversation-runtime
  - reminder
  - social-scheduling
  - channel-reachability
  - wechat-personal
related:
  - docs/issues/2026-06-01-waiting-reply-not-parallel.md
  - docs/issues/2026-06-01-pending-async-closes-stateful-turn.md
  - docs/issues/2026-06-02-shared-reminder-fire-undelivered-no-auto-retry.md
  - docs/issues/2026-05-31-notification-turn-recipient-suppression.md
---

# Eva 2026-06-06 Chat RCA

## What Happened

On `2026-06-06 Asia/Shanghai`, Eva had 17 inbound messages and 34 outbound
messages in production. The core user-visible failures were:

- slow turns repeatedly appeared silent because every waiting-message provider
  delivery failed with `provider_network_error`;
- shared-reminder copy implied approval or confirmation even though the current
  product contract makes shared reminders active immediately;
- three reminder-fire messages rendered the wrong reminder content or wrong time;
- a friend-name correction (`zihao就是olivers`) did not recover the previous
  failed scheduling request;
- friend availability output leaked inferred activity detail (`你们约了散步`) after
  a prior refusal to expose another friend's schedule details;
- the first friendship-created notification for Eva remained pending, while later
  shared-reminder notifications delivered.

This report is RCA only. It does not change production behavior.

## Why It Matters

These failures are high-impact because the assistant looked unreliable on the
main product promise: coordinating reminders and friend availability. The worst
failure was not a missing database write; it was a trusted reminder fire being
rendered with unrelated recent chat context, which makes an already-created
reminder look semantically wrong at the exact moment it matters.

## Affected Surfaces

- `coke-worker` / `TurnRunner`: render turns, waiting reply lifecycle, turn
  supersession, lock handling.
- `AgnoInteractionAgent`: render prompt context, shared-reminder reply contract,
  state-change reply validation, friend correction handling.
- `ReminderFireTurn`: current render input contains only underspecified trigger
  payload facts.
- `ChannelReachabilityService` and provider adapter: waiting-message delivery
  failures are recorded but not recovered as a product-visible state.
- `SocialSchedulingService`: durable shared-reminder and availability facts are
  mostly correct; the observed issues are in response/render contracts around
  those facts.
- `coke-web` Friends page and friendship APIs: friend-link handoff and direct
  join are mostly implemented, but user-visible success feedback is still
  generic and does not include the friend's display name.
- Identity activation / onboarding: first-guidance state exists, but the
  configured onboarding prompt is not yet injected or marked as sent at runtime.

## Production Evidence

Live runtime:

- host: `gcp-coke`
- compose root: `/home/whoami/coke-clean`
- running stack: `coke-clean-coke-api-1`, `coke-clean-coke-worker-1`,
  `coke-clean-coke-scheduler-1`, `coke-clean-coke-outbox-relay-1`,
  `coke-clean-postgres-1`, `coke-clean-redis-1`
- database timezone: `UTC`
- evidence window: `2026-06-05 16:00:00+00` to
  `2026-06-06 16:00:00+00` (`2026-06-06 Asia/Shanghai`)

Eva runtime identity:

- account: `94566791-4d39-4b28-9d9f-367c1ed0be2c`
- conversation: `50425626-97b2-4056-b493-99aa738ba171`
- profile timezone: `Asia/Shanghai`
- conversation sequence closed through inbound seq `17`

Message and delivery counts:

- inbound: `17`
- outbound: `34`
- reply delivery attempts: `24 sent`
- waiting-message delivery attempts: `10 failed`, all with
  `provider_network_error`

Important local timeline:

- `10:51:34` Eva: `帮我和zihao约个一个11:40的午饭呗`
- `10:52:15` Eva: `hey？`
- `10:52:33` assistant: `你的好友列表里没有叫 zihao 的，目前只有 olivers 一个好友哦`
- `10:52:54` Eva: `zihao就是olivers`
- `10:54:28` assistant: `我没法查看 olivers 的日程哦，只能看和管理你自己的`
- `11:28:41` assistant: `好，已经帮你和 olivers 约了下午两点的咖啡，等他确认~`
- `11:31:07` reminder fire: `和 olivers 的咖啡快到啦，11:40 见~`
- `13:35:45` availability reply included:
  `14:00-14:15忙`, `15:00-15:15忙（你们约了散步）`
- `13:38:21` assistant: `下午3点和 Oliver 喝咖啡在你可约范围内，没问题~`
- `14:01:17` reminder fire: `还有1小时就是你和 Oliver 喝咖啡的时间啦，别忘了~`
- `15:00:56` reminder fire: `到时间啦，你和 Oliver 的咖啡局现在开始☕`

Reminder facts versus rendered text:

| Due time | Durable reminder/shared-reminder fact | Rendered outbound text |
| --- | --- | --- |
| `2026-06-06 11:30 Asia/Shanghai` | `和eva约11:30的午饭` | `和 olivers 的咖啡快到啦，11:40 见~` |
| `2026-06-06 14:00 Asia/Shanghai` | `和Olivers约下午两点喝咖啡` | `还有1小时就是你和 Oliver 喝咖啡的时间啦，别忘了~` |
| `2026-06-06 15:00 Asia/Shanghai` | `约olivers下午三点散步` | `到时间啦，你和 Oliver 的咖啡局现在开始☕` |

Turn and command materialization facts:

- Eva's `10:51:34` turn was superseded by `10:52:15`; no shared-reminder command
  materialized.
- Eva's `10:52:54` correction turn was superseded by `10:53:33`; no command
  materialized.
- Eva's `10:55:18` 11:40 coffee request was superseded by the `11:28:08`
  message; no command materialized.
- The `11:28:08` 14:00 coffee turn materialized one shared reminder.
- The `13:28:06` 15:00 walk turn materialized one shared reminder.
- Eva's `13:35:57` 15:00 coffee turn was superseded by `13:37:50`; no coffee
  shared reminder materialized.

Notification facts:

- Eva's `friendship_created` notification at `2026-06-06 10:46:43
  Asia/Shanghai` remained `pending` with no recipient turn attached.
- Later shared-reminder notifications for Eva were `delivered`.

## Root Causes

### RC1: Reminder-fire render turns are missing trusted reminder facts

This is the primary root cause for the most severe user-visible failures.

The database facts were correct: shared reminders, projections, reminder content,
and trigger times matched the intended durable state. The wrong content appeared
only when `ReminderFireTurn` rendered user-visible text.

The render input path is underspecified:

- `coke/turn/runner.py` builds render context with `ToolProfile.render(...)`,
  so the agent cannot call mutation or lookup tools during render.
- `coke/llm/agno_interaction_agent.py` tells render mode not to call tools.
- `_render_trigger_input_block()` only serializes the raw trigger payload:
  `account_id`, `due_at`, `fire_ids`, and `trigger_id`.
- `_notification_domain_result()` builds a structured `domain_result` for
  `NotificationTurn`, but there is no equivalent domain-result builder for
  `ReminderFireTurn`.

The Agno run evidence confirms the missing-fact failure mode. Reminder-fire runs
received a current input payload with only `account_id`, `due_at`, `fire_ids`,
and `trigger_id`. One run even produced a serialized attempt to call
`social_scheduling_tool` with `operation="query_reminder"`, an operation that is
not present in the current composition layer. The final rendered texts then
borrowed content from recent conversation history (`11:40 coffee`, `Oliver
coffee`) instead of the durable reminder fact.

Correct layer: render context assembly and render validation. The fix should not
be in reminder persistence, because the persisted facts were already correct.

### RC2: Waiting-message delivery failure is recorded but not recovered

Eva saw silence during slow turns because all ten waiting-message attempts failed
with `provider_network_error`.

The code path records a runtime-owned waiting message and attempts provider
delivery:

- `coke/worker/waiting_reply.py` marks the turn `pending_async_reply`, records
  `WAITING_TEXT`, and calls `outbound_delivery.deliver(...)`.
- if delivery status is `failed`, it logs `waiting_reply_delivery_failed` but
  still returns `True` from `_dispatch_one()`;
- `coke/turn/runner.py` has a sync-timeout waiting path with the same product
  assumption: once the waiting text is recorded and delivery is attempted, the
  turn returns a visible waiting state.

That means the product lifecycle treats the waiting message as visible even when
the provider did not send it. The later final replies may still arrive, but the
user has already experienced an unexplained dead zone and may interrupt with a
new inbound message.

Correct layer: channel reachability and waiting lifecycle. A failed waiting send
needs retry, downgrade, or a visible failure/recovery path; it should not be
counted as successful user-facing progress.

### RC3: Shared-reminder response copy is not hard-bound to the active-immediate contract

The product contract says shared reminders are active immediately and are not an
approval, invitation, accept/reject, or pending-confirmation workflow. The agent
instructions contain that rule, but production output still said:

- `等他确认~`
- `邀约`
- `下午3点和 Oliver 喝咖啡在你可约范围内，没问题~`

The durable state did not create a 15:00 coffee reminder; the 15:00 durable
shared reminder was a walk. So this is not only wording drift. It is a response
contract gap where the final assistant text can imply a successful or pending
state that the domain layer did not materialize.

The existing guard `_state_change_reply_without_tool_call()` is too narrow for
this incident. It catches some direct success claims without tool calls, but it
does not cover approval/pending wording, `邀约`, or soft success language like
`没问题`. It also does not validate final text against the specific
shared-reminder tool result.

Correct layer: response contract enforcement after tool results and before
delivery.

### RC4: Friend alias/correction recovery is too narrow

Eva corrected the failed friend name with `zihao就是olivers`. The assistant did
not treat that as a correction to the previous failed scheduling request.

The current path can list active friends and ask clarification, but the recovery
logic is oriented around explicit clarification turns. It does not handle a user
declaring that an unmatched name is an alias for an existing active friend, and
it does not re-open the prior failed scheduling intent with that correction.

Correct layer: reference resolution and follow-up intent handling. The system
needs an explicit correction pattern for `X就是Y` / `X is Y`, then either apply it
to the immediately preceding failed request or ask one concise confirmation.

### RC5: Availability privacy is enforced in data, but not in generated wording

The availability service returns busy/free windows and intentionally strips
detail identifiers:

- `build_busy_free_windows()` copies busy intervals with `detail_id=None`;
- `_availability_facts()` exposes only `friend_account_id` and public windows.

So the backend did not expose the friend's private reminder titles through the
availability tool. The phrase `15:00-15:15忙（你们约了散步）` was generated from
conversation context, not from the availability facts.

This creates an inconsistent privacy boundary: the assistant first says it
cannot inspect Olivers's schedule details, then later labels a busy window with a
specific activity. Even if Eva was a participant in that shared reminder, the
availability response format should stay within the busy/free contract unless a
separate product rule explicitly allows participant-owned labels.

Correct layer: availability reply contract and post-generation validation.

### RC6: First-use notification handling left onboarding state pending

Eva's `friendship_created` notification remained `pending` while subsequent
shared-reminder notifications delivered. The `NotificationTurn` around that time
completed in the conversation timeline, but the recipient row was not settled.

This is a secondary contributor, not the main reminder bug. It likely weakened
the first-use experience and may help explain why Eva later asked `你是谁`.

Correct layer: notification recipient lifecycle. A render turn that fails to
settle a recipient should mark it failed with structured facts or retry; it
should not remain indefinitely pending.

## Ruled Out

- Durable reminder content was not the source of the wrong reminder-fire text.
  The reminder and shared-reminder rows contained the correct titles and local
  trigger times.
- Superseded turns did not create stale shared reminders. The stale 11:40 and
  15:00 coffee attempts had no materialized shared-reminder command.
- Availability data did not expose detailed friend schedule titles. The leakage
  came from generated wording, not from the public availability facts.

## Product Feedback Cross-Check

This section reconciles the later product feedback list with this RCA and the
current repository state. It separates production-observed failures from broader
requirement gaps that were not visible in the original Eva-only timeline.

### Already Implemented Or Partially Implemented

- Friend-link handoff is mostly implemented locally. The Friends page preserves
  the `join` code through login/registration, calls `/api/friends/join`, refreshes
  the list, and the domain service creates an active friendship without requiring
  the joining user to have a usable channel. Remaining gap: the success message is
  generic (`好友已添加。`) and does not say `已成功添加 Oliver`.
- Direct friendship state is the current product model. The domain has no
  pending accept/reject flow for friend links, and shared reminders are active
  immediately once created.
- Waiting/final reply infrastructure exists. Runtime-owned waiting text is sent
  after a delay, `pending_async_reply` is an intermediate state, and the final
  Interaction Agent reply is still expected later. Remaining gap: Eva showed that
  failed provider delivery of the waiting text is logged but treated too much like
  successful user-visible progress.
- Friend availability has a backend/tool path for explicit date ranges. The
  service returns privacy-safe busy/free windows and strips reminder detail ids.
  Remaining gap: generated replies can still add inferred activity labels from
  conversation context, and no current rule defines a default range for vague
  requests like `看看 Oliver 什么时候有空`.
- Reminder and shared-reminder duration fields are implemented with the current
  default of 15 minutes. This is implemented, but it is not the product feedback's
  requested activity-based default.

### Not Yet Implemented Or Not Yet Proven Fixed

- `ReminderFireTurn` still needs trusted reminder facts loaded from `fire_ids`
  before rendering, plus validation that rendered text matches the loaded title,
  local due time, timezone, and participant-visible context.
- Waiting-message provider failure needs a retry, downgrade, or recovery path
  instead of leaving the user with an apparent silent turn.
- Shared-reminder final text needs validation against the materialized tool
  result and must forbid approval, pending, or soft-success wording when the
  durable command did not happen.
- Friend alias/correction recovery is not implemented for `X就是Y` turns that
  should repair the immediately preceding failed scheduling request.
- Availability replies need output-contract enforcement so they only expose
  busy/free windows unless a canonical product rule explicitly permits
  participant-visible labels.
- The first-use notification recipient pending gap is unresolved for render turns
  that finish without settling notification delivery.
- The configured onboarding prompt is not wired end-to-end. The pre-LLM gate can
  mark that first guidance is needed, but the Interaction Agent prompt does not
  receive an onboarding block and runtime code does not mark
  `first_guidance_sent_at` after sending guidance.
- Activity-based default durations are not implemented. Current requirements and
  code use 15 minutes when the user omits duration; the detector is explicitly
  told not to normalize guessed durations.
- Early reminder lead time is not implemented. Current requirements and scheduler
  behavior trigger reminders when due; the product feedback's 5-10 minute advance
  reminder is a new requirement.
- User-defined bookable windows such as `只有早上 9 点到晚上 6 点能约` are not part
  of the current requirements and are not enforced by shared-reminder creation.
  Existing checks cover receiver conflicts and participant channel reachability,
  not schedulable-hour preferences or recommended slots.
- Latency instrumentation for reminder creation is not implemented as a product
  requirement. The system carries `traceparent`, but it does not yet record
  per-stage timings for LLM detection, tool execution, database writes, outbox
  relay, and provider delivery or compare those timings with direct Reminder API
  calls.

### Newly Discovered Gaps Not Reflected In The Original RCA

- The current requirements document has a friendship contradiction: the matrix
  now says the joining user does not need a usable channel to establish
  friendship, while older detailed bullets still require the joining user to have
  a usable channel. The implementation follows the newer channel-optional joiner
  contract.
- Product onboarding wording mentions `约课` and `随手备忘`, but the current product
  baseline does not support external booking execution and explicitly excludes
  memo runtime/cards/search/review queue. If product wants those terms, the
  requirement baseline needs to define whether they mean shared reminders,
  unscheduled reminders, long-term memory, or a new feature.
- Vague availability queries need a canonical default date range. An older
  friend-booking design mentioned a next-7-days default, but the current
  requirements baseline now requires availability queries to have a date range
  and does not promote that default into the active contract.
- Friend-add success feedback needs the friend's display name in the web flow and
  any conversation-code flow, so the user sees a concrete result like
  `已成功添加 Oliver` instead of a generic notice.
- Reminder copy needs a lead-time-aware wording contract. The Eva incident shows
  wrong remaining-time text, and the product feedback now also asks for advance
  reminders; both require tests that bind rendered copy to actual trigger/due
  facts rather than recent conversation context.

## Recommended Fix Order

1. P0: Add a trusted `ReminderFireTurn` domain-result path. Given `fire_ids`,
   load the reminder projection, content/title, local due time, timezone,
   participant-visible shared-reminder context, and delivery/fire id. Render only
   from those facts, or use a deterministic renderer for fire notifications.
2. P0: Validate reminder-fire output against the loaded fact before delivery.
   Reject or replace text that mentions a different title, different time, or a
   tool-call serialization.
3. P1: Treat waiting-message provider failure as an incomplete visibility state.
   Add retry or delayed recovery, and do not report the waiting text as visible
   when `delivery_attempt.status='failed'`.
4. P1: Add shared-reminder reply validation that forbids approval/pending copy
   and verifies final text against the exact materialized tool result.
5. P1: Add friend alias/correction handling for `X就是Y`-style turns, scoped to
   active friends and the immediately preceding failed intent.
6. P1: Constrain availability replies to busy/free windows unless a current
   canonical product spec explicitly permits participant-visible labels.
7. P2: Close the notification-recipient pending gap for render turns that finish
   without settling recipient delivery.
8. P2: Finish onboarding prompt injection and `first_guidance_sent_at`
   materialization. The first reply should use the configured user address name
   and only introduce capabilities that exist in the current product contract.
9. P2: Personalize friend-add success copy by returning or resolving the added
   friend's display name for web and conversation join flows.
10. P2: Decide and document the requirement for vague availability ranges, then
   implement the chosen default or require a clarification consistently.
11. P2: Add activity-based duration defaults only after updating
   `docs/product-requirements/current.md`; otherwise keep the current 15-minute
   default and avoid prompt-only drift.
12. P2: Add early-reminder lead-time semantics and lead-time-aware render tests
   only after the product baseline defines whether reminders trigger before the
   activity start, at the activity start, or both.
13. P3: Add user-defined bookable-window settings, parsing, enforcement, and
   recommended-slot behavior if product confirms this as a current requirement.
14. P3: Add per-stage latency instrumentation for reminder creation and compare
   it with direct Reminder API timings before optimizing blindly.

## Current Status

Open. Production was inspected read-only. No code or deployment change was made
as part of this investigation.

## Evidence Commands

The investigation used production SQL over:

- `account`, `user_profile`, `conversation`, `message`, and `delivery_attempt`
  for Eva's message and delivery timeline;
- `turn` for supersession and command materialization boundaries;
- `shared_reminder`, reminder projection/fire tables, and notification tables for
  durable facts versus rendered text;
- `ai.agno_sessions.runs` for render prompt input and model output evidence.

Relevant local code paths:

- `coke/llm/agno_interaction_agent.py`
- `coke/turn/runner.py`
- `coke/worker/waiting_reply.py`
- `coke/composition.py`
- `coke/domains/social_scheduling/service.py`
- `coke/domains/social_scheduling/availability.py`
- `coke/domains/reminder/service.py`
- `coke/domains/reminder/scheduler.py`
- `coke/llm/reminder_detector.py`
- `web/app/(customer)/account/friends/page.tsx`
- `web/lib/i18n.ts`
