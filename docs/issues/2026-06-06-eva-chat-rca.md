---
kind: investigation
status: open
title: Eva 2026-06-06 chat root-cause analysis
created_at: 2026-06-06
updated_at: 2026-06-13
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

> This ordering predates the `2026-06-07` design review. Where it conflicts with
> the revised tracks, the design review and the revised Track repair shapes win. In
> particular: P0 now leads with Track I (structural render-history isolation) as the
> precondition for the Track A fact hydration and guard; "use a deterministic
> renderer" in item 1 and "validate ... text that mentions a different title" in
> item 2 are superseded by the single-producer + dynamic-fact-block + structural
> fail-closed guard decisions (D1/D2); item 3's "add retry" is superseded by the
> diagnostic-first, bounded-`delivery_intent` policy (D5).

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

> The track repair shapes below were revised on `2026-06-07` after a multi-agent
> design review. Read the "2026-06-07 Multi-Agent Design Review" subsection first
> (immediately below); it sets the cross-cutting architecture decisions (D1-D6)
> that govern Track A, B, C, D, E, F, and I.

### 2026-06-07 Multi-Agent Design Review

This subsection records the design decisions that govern the Track repair shapes
below. Read it before the tracks.

#### Method

The fix tracks above were pressure-tested by six independent design agents in two
rounds. Each agent was given a fixed slice and explicitly instructed to attack the
lead engineer's position rather than agree. Round one covered render-turn
architecture (RC1/Track A/I), response-contract enforcement (RC3/RC5/RC4), and
delivery/lifecycle reliability (RC2/RC6). Round two arbitrated the one open
question round one surfaced: whether failed/interrupted scheduling intent needs a
durable artifact, argued by a neutral data-model voice, a minimalism advocate, and
a reliability advocate. The decisions below are the converged conclusion, not any
single agent's view.

#### Cross-cutting principle

Nearly every root cause is the same anti-pattern: the runtime reconstructs product
truth from conversation prose or chat history instead of carrying typed trusted
facts. The unifying repair is to replace "reconstruct truth from history" with
"carry a typed trusted fact, render or act from it, and validate structurally
rather than by scanning prose."

#### D1: Single user-facing producer is preserved (architecture decision)

The Interaction Agent remains the only producer of channel-visible prose. Internal
or intermediate agents may emit factual or structured content, but the text
delivered to the user always comes from the single persona agent. We explicitly
reject the round-one proposal to add typed deterministic renderers that produce
user-visible text, and we explicitly keep the `docs/ARCHITECTURE.md` invariant
"Interaction Agent is the sole user-facing prose producer". Splitting the
user-facing voice into per-turn renderers would fragment persona ownership.

Trusted facts reach the single agent as dynamic prompt blocks (the legacy
`coke-legacy-server` "Soul vs Skills" notice/context-block pattern: a constant
persona plus dynamically loaded fact and stance blocks). Determinism lives in the
fact supply and in the guard, not in the output. Because production already proved
prompt-only constraints fail, the dynamic-fact approach must be paired with two
non-prompt structural supports:

1. Render-mode chat-history isolation, enforced at agent construction, not by a
   prompt instruction. In RC1 the agent already had the instruction and still
   borrowed from history; the injected fact block must not have to out-compete
   full chat history.
2. A structural fail-closed guard on fact-bearing output. The rendered
   fact-bearing values (title, time, status) must reconcile with the trusted fact
   tokens; if they cannot, fail closed to a safe minimal rendering or retry. This
   is a guard on the single producer, not a second producer.

#### D2: History isolation is the highest-leverage structural fix (RC1 + RC5)

Render-mode history isolation closes both RC1 and RC5 by removing the contaminating
source. The wrong reminder content and the `你们约了散步` privacy leak both came
from chat history, not from durable facts or the availability tool. Once render-mode
history is structurally isolated and the trusted fact block is the only fact source,
the leak is impossible by construction; no prose-scanning privacy validator is
needed. Keep structural validation (facts present, due time computable, subject ids
present, protocol well-formed); drop free-prose contradiction parsing.

#### D3: Bind response copy to close-time materialized outcome (RC3)

State-changing tools are staged and only materialize at the close boundary
(`commit_reply`). The authoritative result is the close-time materialized outcome,
not the pre-close staged preview, and today the materialized facts are not fed back
into reply rendering. The fix binds the visible state claim to a structured
`SocialSchedulingOutcome` carrying a canonical status (`created_active`,
`duplicate_active`, `blocked_*`, `needs_*`, `staged_pending_close` which is never
user-visible as success, etc.) with a per-status allowed-claim mapping. The phrase
denylist (`等他确认`/`没问题`/`邀约`) moves into eval and regression assertions, not
production routing, because denylisting is the keyword-routing anti-pattern this
project forbids.

#### D4: Failed scheduling intent needs a narrow durable artifact (RC4)

Round-two conclusion. Existing rows (`turn`, `message`, `output_disposition`,
`staged_command`, `SemanticDecision`) cannot represent an understood-but-blocked
scheduling intent without re-parsing chat history as executable state, which is the
same anti-pattern as RC1. Turn-local recovery fails because the correction
(`zihao就是olivers`) arrived after the blocked turn had already closed, and workers
run as separate containers with Postgres as the durable truth.

The reliability advocate's intent-vs-interruption split resolves the scope worry:
these are two different durability needs, not one artifact.

- The failed/blocked scheduling intent (RC4) gets a narrow durable
  `recoverable_scheduling_intent` artifact. Scope discipline: only
  `shared_reminder_create` blocked by `unmatched_friend`/`ambiguous_friend`; at most
  one open per conversation; short expiry; never materialized directly; consumed only
  when the semantic interpreter classifies a later fresh inbound as a correction;
  freshness/close boundary remains the final authority; a superseded consuming turn
  does not consume it. Not a task queue, no global alias memory, no approval flow.
- The interruption/coalescing fact (RC2) is derived transiently from existing
  `turn`/`output_disposition`/`message`/`delivery_attempt` rows. It does not get its
  own durable artifact. What RC2 does need durable is failed-waiting-delivery
  evidence, which belongs in Track B, not in this artifact.

The minimalist's bright line is retained as a product-requirement-first item: if the
product later requires resume-after-restart, resume-after-unrelated-turns, or
restate-free recovery, that is a named requirement extension. The baseline artifact
only guarantees near-term (within-expiry) recovery.

#### D5: Waiting-delivery recovery is diagnostic-first (RC2)

The 10/10 waiting-delivery failures versus 24 successful reply deliveries through
the same adapter are strong evidence but not proof of a defective path; same adapter
does not mean same path (waiting comes from `WaitingReplyDispatcher` and the
sync-timeout branch, replies from the runner delivery lifecycle). The most likely
structural cause is wechat `context_token` windowing: delayed waiting sends may use a
stale or missing context token while fresh final replies do not. Before choosing a
recovery policy, add a delivery-envelope diagnostic (delivery source, container,
traceparent, provider route, context-token source/age, error code, latency, retry
attempt) and bucket waiting versus reply failures by window/recipient/route/error.

Do not blind-retry: same-key retry is a no-op under current idempotency, and a new
key can duplicate user-visible "still processing" sends. The clean policy is a
logical `delivery_intent` (`turn_id:waiting:1`, `:2`), at most one jittered retry for
retryable transport errors only while the final reply is not ready, no retry for
`context_token_required`/invalid-token/session-window errors, cancellation when the
turn becomes `replied`/`failed`/`superseded`, and a per-route/account circuit
breaker. A failed waiting send is durable observable evidence, never user-visible
progress. RC1 (wrong trusted reminder content) remains the top severity; the
silence-then-supersession chain is treated as a to-be-confirmed hypothesis, not an
asserted fact, until input-window and causal-id evidence shows successor turns
dropped the original intent.

#### D6: Notification recipient lifecycle settles at the terminal path first (RC6)

Fix the terminal-settlement invariant first: every `NotificationTurn` terminal path
must settle every target recipient as delivered, failed, or undelivered with
structured facts. A reconciler is a crash/history backstop only; starting with a
reconciler would hide the settlement bug rather than fix it.

#### Open decisions deferred to the human or product baseline

- Whether the product requires resume-after-restart / restate-free recovery for
  failed scheduling intent (extends D4 beyond near-term recovery).
- Whether availability may ever expose participant-visible shared-reminder labels
  (default: busy/free only).
- The default range for vague availability queries.
- Whether waiting retry should ever be user-visible once the final reply is near, or
  always downgrade.

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
- Isolate chat history structurally in render mode (per D1/D2). This is the
  highest-leverage fix: `add_history_to_context` must be off (or strongly
  downranked) for `ReminderFireTurn` at agent construction, not via a prompt
  instruction. In production the agent already had the "render the reminder fact"
  instruction and still borrowed from history; the hydrated fact block must not
  have to out-compete full chat history. The hydrated `domain_result` is the only
  fact source for title/time/participant truth.
- Keep the single user-facing producer (per D1). Do NOT add a typed deterministic
  renderer that emits user-visible reminder text. The persona Interaction Agent
  renders the reminder, with the trusted reminder facts injected as a dynamic
  fact block (legacy notice-block pattern), history isolated, persona intact.
- Add a structural fail-closed guard before delivery (per D1/D2). The guard
  reconciles the fact-bearing values in the reply against the trusted fact tokens:
  the stated title must match the hydrated title, the stated local time must match
  the hydrated due time, and any remaining-time phrase must be computable from
  `due_at - now`. Keep structural validation (facts present, due time computable,
  subject ids present, no serialized tool call, protocol well-formed). Do not
  build a free-prose contradiction parser. If reconciliation fails, fall back to a
  safe minimal rendering of the trusted facts or retry.

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
- Diagnose before choosing a recovery policy (per D5). Add a delivery-envelope
  diagnostic (delivery source, container, traceparent, turn/trigger id, provider
  route, context-token source and age, error code, latency, retry attempt) and
  bucket the waiting failures against the successful reply deliveries by
  window/recipient/route/error. The leading hypothesis is wechat `context_token`
  windowing: delayed waiting sends may use a stale or missing context token while
  fresh final replies do not. "Same adapter" does not mean "same path".
- Do not blind-retry. Same-key retry is a no-op under current idempotency, and a
  new key can duplicate user-visible "still processing" sends. Use a logical
  `delivery_intent` (`turn_id:waiting:1`, `:2`); allow at most one jittered retry
  for retryable transport errors and only while the final reply is not ready; do
  not retry `context_token_required`/invalid-token/session-window errors (mark
  waiting visibility failed and rely on the final reply); cancel any pending retry
  when the turn becomes `replied`/`failed`/`superseded`; add a per-route/account
  circuit breaker to prevent retry storms.
- Persist failed-waiting-delivery as durable observable evidence (this is the
  durable half of the RC2 split in D4). The interruption/coalescing fact is
  derived transiently from existing `turn`/`output_disposition`/`message`/
  `delivery_attempt` rows; do not add a separate durable interruption artifact.
- The dispatcher must not count a failed provider send as a successful waiting
  visibility outcome in logs, metrics, or future operator-facing status.

Verification:

- Unit test for provider `failed/provider_network_error`: turn stays active,
  staged commands are not materialized, `last_closed_inbound_seq` does not
  advance, and failed waiting delivery is observable.
- Regression test that a later final reply can still transition from
  `pending_async_reply` to `replied` after waiting delivery failed.

2026-06-07 implementation note:

- Track B now records delivery-envelope diagnostics on delivery attempts, shares
  waiting-delivery code between the timer and sync-timeout paths, uses bounded
  logical waiting intents with one retry for retryable transport errors, and keeps
  failed waiting delivery as observable evidence while the turn remains active.

### Track C: Shared-Reminder Reply Contract Enforcement

Target files:

- `coke/llm/agno_interaction_agent.py`
- `coke/turn/output_protocol.py`
- `coke/composition.py`
- `tests/unit/coke/llm/test_interaction_agent.py`
- `tests/unit/coke/turn/test_output_protocol.py`

Repair shape:

- Bind final user-visible text to the close-time materialized outcome, not to the
  pre-close staged preview and not to the mere existence of any tool call (per D3).
  State-changing tools stage and only materialize at the close boundary
  (`commit_reply`); today the materialized facts are not fed back into reply
  rendering, so feed a structured `SocialSchedulingOutcome` (with `outcome_id` or
  staged-command id) into the reply context. `staged_pending_close` is an internal
  status and must never be rendered as user-visible success.
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
- Keep this as a structured-outcome guard plus tests, not a phrase denylist (per
  D3). Enforcement binds the visible claim to the canonical status via a per-status
  allowed-claim mapping; the model must echo the structured outcome rather than be
  scanned for banned words. Concrete banned phrases (`等他确认`/`没问题`/`邀约`/
  `约好了`) become eval and regression assertions, not production routing, because
  phrase denylisting is the keyword-routing anti-pattern this project forbids. Do
  not rely on prompt wording alone; production already showed prompt-only
  constraints are insufficient.

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

- Classify the correction through the semantic interpreter, not a regex (per D4
  and the no-keyword-routing rule). The interpreter emits a typed follow-up action,
  for example `resolve_friend_reference_correction` carrying
  `prior_reference_text`, `corrected_friend_text`, and a scope of
  `immediately_preceding_unresolved_intent`. Do not string-match `就是`/`is` in the
  runner. Accept the correction only when an open recoverable intent exists that
  failed on an unmatched or ambiguous friend.
- Persist a narrow durable `recoverable_scheduling_intent` artifact (per D4),
  because the correction arrives after the blocked turn has already closed and
  workers run as separate containers. Create it only at the fresh close that tells
  the user the request is blocked, only for `shared_reminder_create` blocked by
  `unmatched_friend`/`ambiguous_friend`, with the understood request facts (parsed
  activity/title, absolute local trigger time, timezone, duration if known, the
  unresolved reference, source input window, `facts_hash`, short `expires_at`). At
  most one open per conversation. Do not reconstruct it by re-parsing chat history.
- Consume it on a later fresh inbound turn: resolve `corrected_friend_text` through
  active friends; if exactly one active friend matches and the artifact is open,
  unexpired, and matching, inject it as a dynamic trusted-fact block and let the
  single Interaction Agent call the scheduling tool, which stages a fresh command
  on the current turn carrying `recoverable_scheduling_intent_id` and `facts_hash`.
  Close-boundary freshness is the final authority: if a newer inbound supersedes the
  consuming turn, the staged command dies and the artifact is not consumed. If the
  correction is ambiguous or stale, the single agent asks one concise confirmation.
  This is not an approval flow; a resolved correction creates the shared reminder
  active-immediate.
- The friend alias is turn-local only. Do not persist global alias memory
  (`zihao = olivers`) unless product explicitly adds alias memory as a requirement.
  Resume-after-restart / resume-after-unrelated-turns / restate-free recovery is a
  product-requirement-first extension (see Track K); the baseline artifact only
  guarantees within-expiry recovery.

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
- Close the leak structurally by removing its source, not by scanning prose (per
  D2). `忙（你们约了散步）` came from chat history, not from the availability tool. In
  availability render mode the chat history must be structurally isolated (same
  agent-construction fix as Track A), so the only fact source is the busy/free
  window block. With history isolated the label has no source and the leak is
  impossible by construction; a free-prose privacy parser is not needed.
- Inject availability results as a dynamic fact block whose visible answer may use
  only each window's `start`, `end`, and `state`, plus the queried friend's public
  display name. The single Interaction Agent still produces the reply; the block is
  the only privacy-bearing fact source. Keep structural validation (the block
  carries no titles/labels/detail ids), not phrase scanning.
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
- Fix the terminal-settlement invariant first (per D6): the audit above is the
  primary fix, so that a completed `NotificationTurn` can never leave a recipient
  `pending`. Only after that, add a reconciliation path for recipients that remain
  `pending` past a threshold after their render turn has terminally completed; the
  reconciler marks them failed or undelivered based on provider/turn evidence. It
  does not retry sends or execute actions. The reconciler is a crash/history
  backstop only and must not be the primary fix — leading with a reconciler would
  hide the settlement bug rather than fix it.
- Keep notification facts informational only. Do not introduce approval or action
  execution through notification retries.

Verification:

- Unit tests for invalid `NotificationTurn` output settling recipients as failed.
- Integration test that a completed notification render turn cannot leave the
  corresponding recipient row pending.
- Production query or smoke evidence that stale pending recipients are either
  retried or converted to structured failed/undelivered state.

2026-06-07 implementation note:

- Track F terminal paths now call the notification render-failure lifecycle so
  invalid output, no-reply retry failure, generic failure, lock/start failure, and
  supersession settle recipients. The reconciler only marks stale pending
  recipients after a terminal turn disposition and does not resend or execute
  product actions.

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

2026-06-07 implementation note:

- Track G now injects onboarding guidance as a trusted fact block only when the
  identity gate requires it, restricts the default capability wording to current
  product surfaces, and stamps first guidance only after a visible final
  onboarding reply delivery succeeds.

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

This is the mechanism root cause behind RC1 and RC5 and the highest-leverage
structural fix (per D2). It governs Track A and Track E: do this first, because the
hydrated fact blocks in those tracks cannot win against full chat history until
history is isolated. Render-mode availability replies (Track E) are included.

Target files:

- `coke/llm/agno_interaction_agent.py`
- `coke/turn/runner.py`
- `tests/unit/coke/llm/test_interaction_agent.py`

Repair shape:

- Render turns such as `ReminderFireTurn`, `NotificationTurn`,
  `UndeliveredResendTurn`, `AccessDeniedTurn`, and availability render turns must
  not use Agno chat history as a fact source. Current agent construction enables
  `add_history_to_context=True` globally
  (`coke/llm/agno_interaction_agent.py`), which lets recent user chat compete with
  structured render facts.
- Isolate history structurally at agent construction, not by prompt instruction
  (per D1/D2). Disable or strongly downrank Agno history for render-mode turns; do
  NOT rely on a prompt that classifies history as "style only", because production
  already had the equivalent instruction and still borrowed from history. The
  structured `domain_result`, `turn_source`, and render payload (injected as
  dynamic fact blocks) must be the only fact source for product state, title, time,
  participant, delivery status, and error status.
- Keep the single user-facing producer and its persona (per D1). The fix is not a
  typed deterministic renderer and not robotic text; persona, speaking style, and
  configured assistant settings stay available for tone. Determinism lives in the
  fact supply and the structural fail-closed guard, not in the output. Interactive
  inbound turns still use relevant history.

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
- Do not add typed deterministic renderers that produce user-visible text, and do
  not rewrite the `docs/ARCHITECTURE.md` invariant that the Interaction Agent is
  the sole user-facing prose producer (per D1). The single producer stays; facts
  flow in as dynamic blocks.
- Do not isolate render history by a prompt instruction alone; do it structurally
  at agent construction (per D2). The equivalent prompt instruction already existed
  in production and failed.
- Do not enforce response contracts with a phrase denylist in production routing;
  bind to the structured outcome status and keep banned-phrase checks in eval (per
  D3).
- Do not blind-retry waiting delivery; diagnose first, then use a logical
  `delivery_intent` with bounded retry and a circuit breaker (per D5).
- Do not add a separate durable interruption artifact; derive interruption context
  transiently from existing rows (per D4). The only new durable artifact is the
  narrow `recoverable_scheduling_intent`, and only for friend-resolution blockers.
- Do not validate render or availability output by parsing free prose for
  contradictions or labels; remove the contaminating history source and keep
  validation structural (per D2).

## 2026-06-07 Eva Reply Fix Deploy

Commit `b4859e057486e00498ed4c802ebc3a32482e3703` was deployed to the clean
production stack on `gcp-coke` over previously deployed
`fb3efb5c699c17fc23cf913dad1171bc8fe4baab`.

This deploy covers two concrete no-reply contributors observed after the RCA:

- fenced JSON from the Interaction Agent is now normalized before output
  protocol validation, preventing `invalid_output_protocol` from turning a
  valid model reply into no reply;
- `coke-outbox-relay` now has `host.docker.internal:host-gateway`, so relay-owned
  waiting delivery can reach the personal-WeChat connector instead of failing
  with host connection refusal.

Production verification used eva account
`94566791-4d39-4b28-9d9f-367c1ed0be2c` and marker
`server-verify-20260607T070825Z`. The clean `/webhooks/wechat/personal` endpoint
accepted one inbound reminder request with eva's current connector context token
(token value was not printed). Postgres verdict:

- turn `272feff9-6715-49cf-9a9d-b5637a42d584` completed with
  `output_disposition.disposition='replied'` and `reason_code='reply_ready'`;
- outbound reply message `c98b2440-c375-47d5-8f8c-f5cb2cc6ff8d` existed;
- delivery attempt `b5cdb1d3-a73c-4cb0-b7fe-b8a8eb0e741f` had
  `status='sent'` and a provider message id present;
- no waiting message was emitted for that turn (`waiting_attempt_count=0`);
- the marked reminder `1b84e908-53a9-46ef-b253-4073d226aa00` was cleaned up
  through `ReminderService.delete_reminder` and ended `lifecycle='deleted'`.

Evidence is saved under
`artifacts/evidence/2026-06-07-eva-reply-fix-deploy/`.

## 2026-06-12 Eva Open-Window State Reset

On `2026-06-12`, Eva again appeared unable to receive replies. Production
inspection showed this was not a provider outage, outbox stall, active worker
turn, or Redis lock:

- clean stack health was OK and `coke-api` was healthy;
- Eva's account/channel/route were active and connected;
- Eva was the only conversation with an open input window;
- no active Eva turn existed;
- recent Eva inbound outbox rows were `published`, `processed`, and `acked`.

The stuck conversation state was:

- account `94566791-4d39-4b28-9d9f-367c1ed0be2c`;
- conversation `50425626-97b2-4056-b493-99aa738ba171`;
- before reset: `last_closed_inbound_seq=69`, `latest_inbound_seq=72`;
- inbound `70`: `王五今天什么时候有空？`;
- inbound `71`: `今天8-9给我建立一个运动的日程`;
- inbound `72`: `hey`.

The window `70..72` had already been processed repeatedly, but each replacement
turn completed with `output_disposition.disposition='failed'` and
`reason_code='needs_past_time_confirmation'`:

- turn `979d2444-e39d-4cfa-b1e8-5ca5a8ec0ba2`, input `70..71`;
- recovery turn `3e4ceba8-6b4c-4031-8758-6178929d8020`, input `70..71`;
- turn `42dbde86-2656-4db5-b722-de8d4a05d572`, input `70..72`.

Because `failed` is an audit terminal state rather than an input-window close
decision, `last_closed_inbound_seq` stayed at `69`. Every new Eva message was
therefore coalesced with the stale `70..latest` window and retriggered the same
past-time failure.

Operational repair was a scoped conversation reset:

```sql
UPDATE conversation
SET last_closed_inbound_seq = latest_inbound_seq,
    updated_at = now()
WHERE id = '50425626-97b2-4056-b493-99aa738ba171'
  AND account_id = '94566791-4d39-4b28-9d9f-367c1ed0be2c'
  AND last_closed_inbound_seq = 69
  AND latest_inbound_seq = 72;
```

The update affected exactly one row. Post-reset verification showed Eva at
`last_closed_inbound_seq=72`, `latest_inbound_seq=72`, no remaining open input
windows, and no active Eva turns.

Follow-up product/runtime bug: `needs_past_time_confirmation` and similar
needs-confirmation settled outcomes must produce a user-visible close decision
(`replied` or `recovered`) instead of leaving the conversation in a repeating
`failed` window.

## 2026-06-12 Eva Open-Window Recurrence and Convergence Fix

Eva's conversation stuck again later on `2026-06-12`. Production evidence showed
the same open-window failure class with a different settled reason:

- account `94566791-4d39-4b28-9d9f-367c1ed0be2c`;
- conversation `50425626-97b2-4056-b493-99aa738ba171`;
- before reset: `last_closed_inbound_seq=79`, `latest_inbound_seq=82`;
- inbound `80`: `olivers今天什么时候有空`;
- inbound `81`: `以及王五今天什么时候有空？`;
- inbound `82`: `今天8-9给我建立一个运动的日程`.

There was no active Eva turn. The three relevant inbound outbox rows were already
`published`, `processed`, and `acked`. Replacement turns for input `80..82`
completed as terminal `failed` rows with reasons including
`needs_past_time_confirmation` and `duplicate_staged_command_idempotency`. No
final delivery attempt existed for the window, so the primary failure was still
the runtime close state rather than the outbox relay.

Manual user notification was attempted before the reset with:

`刚才有几条旧消息卡住了后面的回复，我已经恢复了。现在可以继续发新消息。`

The first send failed with `context_token_required`. Retrying with the latest
context token failed with `wechat_not_connected`; connector health was globally
OK, but Eva's specific connector session
`2e5c4cd8c9f34624abb19d49e590e715` was `expired`. That is a separate channel
session problem and explains why the manual recovery notice could not be sent.

Operational repair was again a scoped conversation reset:

```sql
UPDATE conversation
SET last_closed_inbound_seq = latest_inbound_seq,
    updated_at = now()
WHERE id = '50425626-97b2-4056-b493-99aa738ba171'
  AND account_id = '94566791-4d39-4b28-9d9f-367c1ed0be2c'
  AND last_closed_inbound_seq = 79
  AND latest_inbound_seq = 82;
```

The update affected exactly one row. Post-reset verification showed Eva at
`last_closed_inbound_seq=82`, `latest_inbound_seq=82`, no active Eva turns, and
zero open conversations globally.

Runtime convergence fix: interactive input-window failures now prefer
`recovered` close decisions over audit-only `failed` rows when there is a current
input window to release. The added guardrails cover:

- inbound pipeline unavailable;
- inbound pipeline runtime exception;
- inbound pipeline close-result runtime error;
- async completion timeout after a pending reply;
- async timeout without a task id;
- invalid output protocol on a fallback/access-denied path with current input.

The state-machine impact is intentionally narrow: `failed` remains available for
render/system audit failures that do not own a user input window, while
interactive user windows converge through `recovered` so the cursor advances and
new messages are not dragged behind stale input.

## 2026-06-13 Eva Account Handoff

Eva later connected the same personal-WeChat identity while logged in as the new
web account `eva@potaristudio.com`
(`55d922f5-5dae-47b4-820b-e6ea0ac04794`). Production state was split:

- the durable `channel_identity`, active `channel`, and active `delivery_route`
  for wxid `o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat` still belonged to the old
  account `eva.liu43@hotmail.com`
  (`94566791-4d39-4b28-9d9f-367c1ed0be2c`);
- the live connector session `860c1bbf61ea4b02aca54fb9bcb1ff3e` was connected
  for the new account and the same wxid;
- the old account's conversation was already closed
  (`latest_inbound_seq=82`, `last_closed_inbound_seq=82`), so this was not a
  recurrence of the open-window stall.

Root cause: account handoff had no supported domain operation, and the connector
state also used compact UUID strings for some sessions while Postgres-backed
domain objects use canonical dashed UUID strings. With the split, Coke routed
delivery through the old account while the connector could only send for the new
account. With compact ids, later webhook or send paths could also compare the
same account as unequal at Python string boundaries.

Operational repair:

- retired the old active Eva `channel` and `delivery_route`;
- moved the wxid's `channel_identity` to `eva@potaristudio.com`;
- created a fresh active connected channel
  `8f4d5482-cea8-4b42-9204-38e7298025d5` and active route
  `1eca0551-4099-4606-b8dd-a64a63c2f5da` for the new account;
- left old messages, conversation, reminders, and shared-reminder projections on
  the old account because this was a reachability handoff, not an account merge;
- ensured the new account's onboarding fields
  `first_inbound_received_at`, `activation_completed_at`, and
  `first_guidance_sent_at` remained `NULL`, so the next real WeChat inbound can
  complete first activation and receive first-use guidance;
- normalized all personal-WeChat connector session `account_id` values from
  compact UUIDs to canonical dashed UUIDs, then restarted the connector.

Post-repair production checks showed:

- `channel_identity a202a065-ddf5-42a7-b9b7-49faa654dad7` belongs to
  `eva@potaristudio.com`;
- the old Eva account has no active connected channel;
- the new Eva account has an active connected `wechat_personal` channel and
  route;
- connector `/login/status` for session
  `860c1bbf61ea4b02aca54fb9bcb1ff3e` returned `200`, `status=connected`, the
  canonical new account id, and the expected wxid;
- connector health returned `ok=true`, `connected=true`, and all connected
  sessions now use canonical account ids;
- no Eva-related API error appeared in the immediate post-repair logs.

This was an operational handoff only. A durable product fix should add an
explicit account-handoff domain operation and make the connector/API boundary
canonicalize account ids, instead of relying on manual database and state-file
repairs.

## 2026-06-13 Eva Post-Handoff Webhook Rejection

After the operational handoff, Eva sent another personal-WeChat message but no
reply was produced. Production checks showed this was not another open-window
stall:

- no new Eva inbound row appeared in `message`;
- the old Eva conversation remained closed
  (`latest_inbound_seq=82`, `last_closed_inbound_seq=82`);
- the connector logged webhook delivery failures to
  `/webhooks/wechat/personal` with HTTP `400`, then dropped the message after
  retry exhaustion.

A rollback-only production diagnostic rebuilt the same inbound shape for
account `eva@potaristudio.com`
(`55d922f5-5dae-47b4-820b-e6ea0ac04794`) and wxid
`o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat`. It failed before writing a message:

```text
ChannelReachabilityError code=channel_identity_already_bound
```

The durable row was correct: `channel_identity
a202a065-ddf5-42a7-b9b7-49faa654dad7` already belonged to the new Eva account.
The code path was wrong. `PostgresIdentityAccessRepository` maps UUID columns
through `db_id`, so loaded domain objects carry compact UUID strings, while the
account-bound connector webhook sends the canonical dashed UUID string. The
identity service compared those strings directly in
`bind_channel_identity_to_account`, so the same account was misclassified as a
different account and rejected as `channel_identity_already_bound`.

Local fix: compare account ownership through UUID-equivalence rather than raw
string equality in `IdentityAccessService`, covering both the bind path and
channel-identity ownership checks. Regression coverage:

```bash
.venv/bin/python -m pytest tests/unit/coke/identity_access/test_identity_access_service.py::test_bind_channel_identity_accepts_dashed_uuid_for_existing_compact_identity -q
.venv/bin/python -m pytest tests/unit/coke/identity_access/test_identity_access_service.py tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py tests/unit/coke/channel_reachability/test_provider_webhooks.py -q
```

Deploy evidence:

- Fix commit: `257829d6 fix(identity): compare account UUIDs canonically`.
- Clean backend deploy recreated `coke-api`, `coke-worker`, `coke-scheduler`,
  and `coke-outbox-relay`; deploy marker:
  `257829d66559cb92931c8482a95736ec153ea994`.
- Post-deploy rollback diagnostic in `coke-api` returned `ACCEPT_OK` for the
  new Eva account and wxid, then `RECORD_OK` for a synthetic inbound row and
  outbox row, then `ROLLBACK_OK`.
- No real new Eva message had landed at the time of verification; the previously
  rejected connector delivery was already absent from Coke's durable message
  table, so the fix applies to the next real webhook delivery.

## 2026-06-13 Eva Outbound Route-Key Rejection

After the webhook UUID fix, a manual active outbound test for
`eva@potaristudio.com` still failed before reaching the personal-WeChat
connector. Production evidence:

- Eva's new account, `channel_identity`, active `channel`, and active
  `delivery_route` were present and connected;
- the connector session `860c1bbf61ea4b02aca54fb9bcb1ff3e` was connected and
  had a context token for wxid
  `o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat`;
- `ChannelReachabilityService.send_text(...)` failed in
  `resolve_route -> upsert_route` with:

```text
ValueError: duplicate_active_route_for_channel
```

The route row existed, but its `route_key` had been generated from the dashed
channel UUID. Runtime domain objects loaded through `db_id` use compact UUID
strings, so `send_text` recomputed a different route key, failed to find the
existing active route by key, then tried to create a second active route for the
same channel.

Fix direction: make delivery route keys canonicalize UUID inputs before hashing,
and let `upsert_route` repair/reuse an existing active route when the
account/channel/provider/address identity matches and only the route key is
stale.

Follow-up deployment and live-send evidence:

- Route-key fix commit: `815f0bb6 fix(channel): canonicalize delivery route keys`.
- Clean backend deploy marker after the route-key fix:
  `815f0bb64a7101950ef2c5cbc49f151c4aaba614`.
- First post-deploy active send
  `manual-eva-connectivity-20260612T161854Z` repaired Eva's stale route key but
  failed quickly with `delivery_attempt.status=failed` and
  `error_code=wechat_not_connected`.
- That second failure was not a stuck-message condition. The personal-WeChat
  connector held the connected session account id as dashed UUID
  `55d922f5-5dae-47b4-820b-e6ea0ac04794`, while Coke sent the compact UUID
  `55d922f55dae47b4820be6ea0ac04794`; the connector compared the strings
  directly and falsely rejected the session as disconnected.
- Connector fix commit:
  `29a78d6e fix(wechat): match connector account UUIDs canonically`.
- Connector deploy rebuilt and restarted compose project
  `wechat-personal-connector`; `/healthz` returned
  `{"connected":true,"connected_session_count":3,"ok":true,"status":"connected"}`.
- Final active send
  `manual-eva-connectivity-20260612T162724Z` succeeded with
  `delivery_attempt.status=sent`,
  `provider_message_id=coke-1781281651063-8e8b7da2e620`, route
  `1eca0551-4099-4606-b8dd-a64a63c2f5da`, and `latency_ms=871`.

## 2026-06-13 Eva Hard Reset And Fresh Start

Production evidence later showed the same Eva WeChat wxid
`o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat` spread across multiple connector
sessions and account ids. Coke DB still had `eva@potaristudio.com` connected to
that wxid, while the connector's connected session for the same wxid belonged to
`791077310@qq.com`; the new Eva account's connector session had expired. This was
not one stuck turn. It was account/session ownership drift caused by repeated
scan/bind attempts across different web accounts.

Operational reset evidence:

- Pre-reset backups:
  `/home/whoami/coke-clean/backups/coke-before-eva-reset-20260613T034541Z.dump`
  and
  `/home/whoami/coke-clean/backups/wechat-personal-state-before-eva-reset-20260613T034541Z.json`.
- Deleted the three Eva-related accounts:
  `55d922f5-5dae-47b4-820b-e6ea0ac04794`,
  `94566791-4d39-4b28-9d9f-367c1ed0be2c`, and
  `10d43cb6-ba8d-4301-a43b-8178097e9db1`.
- Deleted associated durable rows including credentials, web sessions, access and
  activation rows, channels, delivery routes, the Eva WeChat channel identity,
  conversations, turns, messages, delivery attempts, reminders, shared reminder
  records, notification records, friend links, and friendships.
- Removed six connector sessions whose account id matched the Eva-related
  accounts or whose `ilink_user_id` matched Eva's wxid; restarted
  `wechat-personal-connector`.
- Post-reset checks returned zero rows for the old account ids, old Eva emails
  `eva.liu43@hotmail.com` and `791077310@qq.com`, and the Eva wxid in
  `channel_identity`; connector state returned `eva_wxid_match_count=0`.
- Created a fresh `eva@potaristudio.com` account:
  `082ef414-4f66-4645-8c79-faab7e0f135b`, with `email_verification_state=verified`,
  `subscription_state=active`, `suspension_state=active`, and fresh activation
  flags still unset.
- Fresh channel smoke: `/api/channels/status` returned `connection_state=not_connected`.
  `/api/channels/wechat-personal/connect` and subsequent
  `/api/channels/wechat-personal/login-status` returned
  `connection_state=connecting`, `connector_status=waiting_for_scan`, session
  `136844cb57364276be4e2ab75d385a1f`, QR id
  `f3e9cccb6d2f63b343a8f1a548600f1d`, and a non-empty QR image
  (`qrcode_image_len=1442`).

## 2026-06-13 Olivers Onboarding Miss In Turn Pipeline

After resetting `olivers@coke.keep4oforever.com` activation fields, production
evidence showed the account sent `Hi` at `2026-06-13T04:01:13Z`, received only
`Hi~`, and then had `first_guidance_sent_at` stamped at
`2026-06-13T04:01:19Z`. The reset had worked; the runtime incorrectly counted a
plain greeting as delivered onboarding.

Root cause: `TurnPipelineRequest.trusted_facts` carried `onboarding_guidance`,
but `_express_request` did not pass it into `ExpressRequest`, and the Express
JSON input/system message did not expose it. The lifecycle recorder only knew
that onboarding was required and a visible reply was delivered, so it marked
first guidance even though the Express reply had no guidance content.

Repair: pass `onboarding_guidance` into Express, include it in the Express input
and system message, and append a short deterministic first-use guidance segment
when the model omits it. This keeps the fix local to the final reply layer and
prevents a plain greeting from being the only visible onboarding reply.

Deployment evidence:

- Commit `90f50774cf9c0f33574484f8257c6ea381962172` deployed to the clean stack.
- `scripts/deploy-compose-to-gcp.sh` rebuilt and restarted `coke-api`,
  `coke-worker`, `coke-scheduler`, and `coke-outbox-relay`; deploy health checks
  passed.
- Post-deploy service check showed all clean compose services running.
- Post-deploy Olivers reset set `first_inbound_received_at`,
  `activation_completed_at`, and `first_guidance_sent_at` back to `NULL` while
  the active WeChat channel remained `connected` and open-turn count was `0`.

## Current Status

Open for the broader Eva RCA tracks that were outside this workstream. The
2026-06-12 open-window close bug described above has a deployed runtime
convergence fix. Eva's 2026-06-13 account handoff has been operationally
repaired, but the product still needs a first-class self-service/account-handoff
operation if this is expected to be a normal user flow. The
specific no-reply deploy slice above is verified in production: fenced-JSON turn
normalization and relay-to-connector reachability are deployed, and eva's real
wechat_personal turn path produced a sent reply. On `2026-06-07`, the local issue
record was expanded with implementation-oriented fix tracks, then revised the
same day after a six-agent design review ("2026-06-07 Multi-Agent Design Review"):
Track A, B, C, D, E, F, and I now reflect the single-user-facing-producer
architecture, structural render-history isolation, close-time outcome binding,
the narrow `recoverable_scheduling_intent` artifact, and diagnostic-first
delivery recovery. The open decisions deferred to product/human in the design
review remain open.

`2026-06-07` delivery-confirmation finding (closed, not a TODO): production data
showed `wechat_personal` records only `sent`, never `delivered`/`delivered_at`.
Investigation of the iLink connector confirmed this is a protocol limitation, not
a missing feature: personal WeChat exposes no delivery/read receipt, and the
connector only learns of inbound messages by polling iLink `get_updates` — there is
no outbound delivery/read callback to record. The server therefore cannot prove a
`wechat_personal` recipient received a message; `sent` (iLink success `ret` +
`provider_message_id`) is the strongest achievable signal. This limitation and the
exact `sent` semantics are documented in `docs/ARCHITECTURE.md` (provider delivery
confirmation). The earlier "add delivery-receipt observability for wechat_personal"
item is closed as not implementable; the actionable parts (honest `sent` semantics,
recording negative/`failed` signals) are already in place.

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
