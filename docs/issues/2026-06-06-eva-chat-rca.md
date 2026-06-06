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

## 2026-06-07 Fix Plan Addendum

This addendum turns the RCA into implementation-ready repair tracks. The first
six tracks are current-contract repairs. The later product-feedback tracks must
not be implemented as prompt-only behavior until the current requirements
baseline is updated.

### Track A: Trusted Reminder-Fire Rendering

Target files:

- `coke/turn/runner.py`
- `coke/composition.py`
- `coke/llm/agno_interaction_agent.py`
- `coke/domains/reminder/service.py`
- `tests/unit/coke/turn/test_turn_runner.py`
- `tests/unit/coke/llm/test_interaction_agent.py`

Repair shape:

- Add a reminder-fire domain-result builder parallel to the existing
  notification domain-result path. It should hydrate `fire_ids` into reminder
  facts in the worker/runner context assembly path before the Interaction Agent
  sees the turn. Do not add a render-time `query_reminder` tool to let the LLM
  fetch facts itself.
- The trusted facts must include at least: `fire_ids`, `reminder_id`, title or
  content, owner account id, local due time, captured timezone,
  `duration_minutes`, reminder kind, viewer account id, delivery/fire id, and
  shared-reminder participant names that are already visible to the recipient.
- Treat conversation history as advisory language evidence only. For
  `ReminderFireTurn`, title/time/participant truth must come from the hydrated
  domain result, not from recent chat history.
- Add render validation before delivery. A reminder-fire reply must fail closed
  or use a deterministic fallback if it mentions a different title, a different
  local time, a serialized tool call, or a remaining-time phrase that cannot be
  computed from trusted facts.
- Prefer a deterministic renderer for reminder-fire notifications if validation
  against free-form LLM prose remains brittle. The current architecture allows a
  runtime-owned exception only for waiting text, so a deterministic reminder
  renderer would need an explicit architecture/product decision before it
  replaces Interaction Agent prose.

Verification:

- Unit test that a `ReminderFireTurn` prompt contains a trusted
  `domain_result` with the reminder title and local due time.
- Regression test with recent conversation mentioning a different activity/time;
  rendered output must use the hydrated reminder fact.
- Protocol test that `no_reply`, tool-call serialization, wrong title, and wrong
  time fail closed for reminder-fire render turns.

### Track B: Waiting-Message Delivery Failure Recovery

Target files:

- `coke/worker/waiting_reply.py`
- `coke/turn/runner.py`
- `coke/domains/conversation_runtime/service.py`
- `tests/unit/coke/worker/test_waiting_reply.py`
- `tests/unit/coke/turn/test_turn_runner.py`

Repair shape:

- Keep `pending_async_reply` as an intermediate disposition; do not revert to the
  old bug where waiting visibility closes the input window or materializes staged
  commands.
- Split "waiting message recorded" from "waiting message actually sent". A
  provider failure should remain observable as failed waiting delivery, not as
  successful user-visible progress.
- Cover both waiting paths: `WaitingReplyDispatcher` emits timer-based waiting
  text from the outbox relay, while `TurnRunner._record_pending_async()` emits
  sync-timeout waiting text. Both paths must follow the same failed-delivery
  semantics.
- Add one of these explicit recovery policies:
  - retry waiting delivery with a new attempt while the original turn remains
    active; or
  - skip retry but leave a durable failed waiting-delivery marker and rely on the
    final async reply; or
  - if the final reply also fails, surface the failure through the existing
    undelivered/recovery path.
- The dispatcher must not count a failed provider send as a successful waiting
  visibility outcome in logs, metrics, or future operator-facing status.

Verification:

- Unit test for provider `failed/provider_network_error`: turn stays active,
  staged commands are not materialized, `last_closed_inbound_seq` does not
  advance, and failed waiting delivery is observable.
- Regression test that a later final reply can still transition from
  `pending_async_reply` to `replied` after waiting delivery failed.

### Track C: Shared-Reminder Reply Contract Enforcement

Target files:

- `coke/llm/agno_interaction_agent.py`
- `coke/turn/output_protocol.py`
- `coke/composition.py`
- `tests/unit/coke/llm/test_interaction_agent.py`
- `tests/unit/coke/turn/test_output_protocol.py`

Repair shape:

- Validate final user-visible text against the latest state-changing
  social-scheduling tool result, not just against the existence of any tool call.
- Expand social-scheduling tool domain results enough for validation:
  `created`, `already_active`, `duplicate`, `blocked`, or `needs_*` status;
  title/activity, local time, timezone, duration, and participant display names
  when available.
- If the tool did not materialize a shared reminder, final text must not say or
  imply success with phrases like `没问题`, `约好了`, `已经帮你`, or `邀约成功`.
- If the tool did create a shared reminder, final text must state active creation
  and must not imply approval, confirmation, pending acceptance, invitation
  approval, or `等他确认`.
- For blocked results, final text must reflect the trusted blocker: missing
  friend, ambiguous friend, receiver conflict, unreachable participant, duplicate
  reminder, or missing time.
- Keep this as a runtime/protocol guard plus tests. Do not rely on prompt wording
  alone; production already showed prompt-only constraints are insufficient.

Verification:

- Unit tests for successful shared-reminder creation forbidding approval/pending
  copy.
- Unit tests for no materialized command forbidding soft success language.
- Unit tests for blocked conflict/unreachable facts requiring the visible reply
  to mention the trusted blocker.

### Track D: Friend Alias And Correction Recovery

Target files:

- `coke/turn/reference.py` or the current reference-resolution owner
- `coke/turn/runner.py`
- `coke/llm/agno_interaction_agent.py`
- `tests/unit/coke/turn/test_turn_runner.py`
- `tests/unit/coke/llm/test_interaction_agent.py`

Repair shape:

- Detect correction turns like `X就是Y`, `X is Y`, and `我说的 X 是 Y` only when
  the previous unresolved intent failed on an unmatched or ambiguous friend name.
- Resolve `Y` through active friends. If exactly one active friend matches,
  attach a turn-local alias mapping from `X` to that friend's account id and
  re-open the immediately preceding failed scheduling intent.
- If the previous failed intent contains enough time/activity facts and the
  current input window has not been superseded, either stage the repaired command
  or ask one concise confirmation. Do not silently create a reminder from an
  old, already-superseded request.
- Do not persist global alias memory from this repair unless product explicitly
  adds alias memory as a requirement. The safe default is turn-local recovery.

Verification:

- Regression test for `帮我和zihao约...` followed by `zihao就是olivers`: the
  assistant should recover the scheduling intent or ask one confirmation, not
  answer as a generic availability refusal.
- Negative tests for unrelated `X就是Y` statements and ambiguous friend matches.

### Track E: Availability Privacy And Default Range

Target files:

- `coke/domains/social_scheduling/availability.py`
- `coke/composition.py`
- `coke/llm/agno_interaction_agent.py`
- `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- `tests/unit/coke/llm/test_interaction_agent.py`

Repair shape:

- Keep the domain response privacy-safe: busy/free windows only, no reminder
  titles, prompts, locations, participant names, or private metadata.
- Add output validation for availability replies so the agent cannot reattach
  inferred labels from conversation context, for example `忙（你们约了散步）`,
  unless a current canonical product spec explicitly allows that label.
- Introduce an explicit reply contract such as `render_availability_busy_free`
  for availability tool results. The visible answer may use only each window's
  `start`, `end`, and `state`, plus the queried friend's public display name.
- Decide the missing product rule for vague requests such as
  `看看 Oliver 什么时候有空`: either default to a bounded local range, or ask for a
  date range. Do not depend on an older dated design note as active product truth.
- If product chooses a default range, put it in
  `docs/product-requirements/current.md` before implementation, then pass the
  resolved `local_start`, `local_end`, and timezone explicitly to the tool.

Verification:

- Unit test that availability facts contain only public windows.
- LLM/prompt regression where conversation history contains a shared activity;
  availability answer still exposes only free/busy windows.
- Natural-language test for vague availability requests after the default-range
  requirement is settled.

### Track F: Notification Recipient Lifecycle Reconciliation

Target files:

- `coke/composition.py`
- `coke/turn/runner.py`
- `coke/domains/social_scheduling/service.py`
- `tests/unit/coke/worker/test_notification_render_trigger.py`
- `tests/integration/coke/test_social_scheduling_notification_outbox_contract.py`

Repair shape:

- Audit all `NotificationTurn` terminal paths: valid reply delivery, delivery
  failure, invalid render output, `no_reply` retry failure, turn failure, and
  supersession. Each path must settle `notification_recipient` as delivered,
  failed, or undelivered with structured error facts.
- Re-check the production failure chain for Eva's first `friendship_created`
  notification specifically. The likely missing branches to verify are: outbox
  row not processed, worker trigger missing a conversation, payload missing
  `notification_fact_id` or `recipient_account_ids`, delivery callback not
  invoked, or recipient fanout settling only part of the recipient set.
- Add a reconciliation path for notification recipients that remain `pending`
  past a threshold after their render turn has terminally completed. The
  reconciler should mark them failed or reschedule them based on provider/turn
  evidence rather than leaving indefinite pending rows.
- Keep notification facts informational only. Do not introduce approval or action
  execution through notification retries.

Verification:

- Unit tests for invalid `NotificationTurn` output settling recipients as failed.
- Integration test that a completed notification render turn cannot leave the
  corresponding recipient row pending.
- Production query or smoke evidence that stale pending recipients are either
  retried or converted to structured failed/undelivered state.

### Track G: Onboarding Prompt Wiring

Target files:

- `coke/composition.py`
- `coke/turn/context.py`
- `coke/turn/runner.py`
- `coke/llm/agno_interaction_agent.py`
- `coke/domains/identity_access/service.py`
- `tests/unit/coke/identity_access/test_identity_access_service.py`
- `tests/unit/coke/llm/test_interaction_agent.py`
- `tests/unit/coke/turn/test_turn_runner.py`

Repair shape:

- Add an onboarding prompt block only when `onboarding_guidance_required` is true.
  The block should include the configured onboarding prompt/settings and the
  trusted `user_address_name` if present.
- Mark `first_guidance_sent_at` only after a visible onboarding reply is
  successfully committed and delivery reaches the product-defined visible state
  (`sent` or `delivered`, depending on provider semantics). Do not mark it on
  failed output, `no_reply`, provider delivery failure, access-denied turns, or
  a pending async waiting message that is not the final onboarding reply.
- The onboarding prompt must not introduce features outside the current product
  contract. In particular, do not claim external class booking or memo runtime
  unless the product baseline adds those features. Use current supported wording
  such as reminders, shared reminders with friends, availability checks, and
  long-term memory/preferences where enabled.
- Keep the reply message-style and short, but let the configured prompt own the
  exact wording and number of segments.

Verification:

- Unit test that first inbound includes an onboarding block once and later turns
  do not.
- Unit test that `first_guidance_sent_at` is stamped only after a committed
  visible onboarding reply.
- Prompt test that unavailable capabilities are not introduced by the default
  onboarding configuration.

### Track H: Friend-Add Personalized Feedback

Target files:

- `coke/api/friend_routes.py`
- `coke/composition.py`
- `coke/domains/social_scheduling/service.py`
- `web/lib/customer-friends.ts`
- `web/app/(customer)/account/friends/page.tsx`
- `web/lib/i18n.ts`
- `web/app/(customer)/account/friends/page.test.tsx`

Repair shape:

- Extend the friend-join result with the added counterpart's display name, or
  make the web flow resolve it from the refreshed friend list before showing the
  success notice.
- Show a concrete success message such as `已成功添加 Oliver` for `created` and a
  concrete already-active message for `already_active`.
- Keep self-friendship, disabled link, invalid link, and auth handoff errors
  distinct.

Verification:

- API/adapter test that join results include enough counterpart identity for UI
  feedback.
- Web test for logged-out handoff and logged-in auto-join showing personalized
  success copy.

### Track I: Render-History Isolation For System Turns

Target files:

- `coke/llm/agno_interaction_agent.py`
- `coke/turn/runner.py`
- `tests/unit/coke/llm/test_interaction_agent.py`

Repair shape:

- Render turns such as `ReminderFireTurn`, `NotificationTurn`,
  `UndeliveredResendTurn`, and `AccessDeniedTurn` should not use Agno chat
  history as a fact source. Current agent construction enables
  `add_history_to_context=True` globally, which can let recent user chat compete
  with structured render facts.
- In render mode, either disable Agno history entirely or make the prompt
  explicitly classify history as style/language evidence only. The structured
  `domain_result`, `turn_source`, and render payload must be the only fact source
  for product state, title, time, participant, delivery status, and error status.
- Keep persona, speaking style, and configured assistant settings available for
  tone. The fix is not to make render text robotic; it is to isolate facts from
  stale conversation context.

Verification:

- Unit test that render-mode agent construction disables or downranks history
  while interactive inbound turns can still use relevant history.
- Regression test with chat history containing a different reminder title/time;
  render output uses only the structured render facts.

### Track J: Eva Regression Corpus

Target files:

- `tests/evals/` or the existing conversation/runtime eval harness
- `tests/unit/coke/turn/test_turn_runner.py`
- `tests/unit/coke/llm/test_interaction_agent.py`
- `artifacts/evidence/` for generated evidence when the eval/smoke runs

Repair shape:

- Convert the Eva production cases into a focused regression set instead of only
  isolated unit tests. The minimum cases are:
  - three reminder-fire turns where recent chat mentions the wrong title/time;
  - `zihao就是olivers` correction after an unmatched friend failure;
  - availability reply after shared-reminder context exists, with no activity
    label leakage;
  - waiting provider failure followed by eventual final reply;
  - shared-reminder creation reply that must not say `等他确认`, `邀约`, or soft
    success when no durable command materialized.
- The regression should assert user-visible text and durable state separately:
  reminders/shared reminders must materialize only when the fresh close boundary
  allows it, and visible text must match the durable facts.
- Store run evidence under the normal generated-evidence path when an eval or
  smoke command is used for completion claims.

Verification:

- Unit tests for each narrow guard.
- A conversation-level eval or smoke that replays the Eva sequence enough to
  prove the cross-turn behavior, not only mocked helper behavior.

### Track K: Product-Requirement-First Items

These items are product-feedback requests, but they conflict with or extend the
current requirements baseline. Do not implement them as hidden prompt behavior.

- Activity-based default duration: update the product baseline with activity
  defaults first, then change detector/tool behavior and tests. Until then, 15
  minutes remains the current contract.
- Early reminder lead time: define whether the product sends an advance reminder,
  an at-start reminder, or both. Then update scheduler/fire facts, delivery
  semantics, and render copy tests.
- User-defined bookable windows: define storage, conversation update semantics,
  timezone behavior, overlap rules, and recommended-slot behavior before adding
  enforcement. This should be a settings/social-scheduling feature, not a
  one-off prompt rule.
- Latency instrumentation: define the stages and evidence destination before
  optimizing. Minimum stages should include inbound persistence, semantic/LLM
  detection, tool execution, database commit, outbox relay, worker start,
  provider send, and final delivery callback.

Verification:

- Each product-requirement-first item needs a `docs/product-requirements/current.md`
  update or a dated spec before code changes.
- Runtime behavior claims need unit tests plus either an eval/smoke path for
  conversation behavior or an operational evidence query for latency.

### What Not To Do

- Do not fix reminder-fire copy by adding more recent-chat prompt examples while
  leaving trusted reminder facts absent.
- Do not give render mode new business lookup tools such as `query_reminder` to
  compensate for missing pre-hydrated facts. Render mode should receive trusted
  structured facts, not perform business discovery.
- Do not add regex-only parsers for `X就是Y`, availability, or duration defaults
  without a current owner and tests.
- Do not reintroduce pending approval flows for friendship or shared reminders.
- Do not expose friend reminder titles through availability responses to make the
  generated wording easier.
- Do not mark product feedback items as implemented until production or
  user-path smoke evidence covers the actual channel-visible behavior.

## Current Status

Open. Production was inspected read-only. No code or deployment change was made
as part of this investigation. On `2026-06-07`, the local issue record was
expanded with implementation-oriented fix tracks; no runtime code or deployment
change was made in that follow-up.

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
