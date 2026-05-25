---
status: draft
created_at: 2026-05-26
owner: bug-b-cluster
kind: bug-design
---

# Bug B cluster after coach-booking X/Y fixes

## Scope

This design covers the Bug B empty-fallback cluster seen in
`artifacts/evidence/shared-reminder-agent-smoke/coach-booking-20260525t164229Z.json`
after the Bug X prompt debooking design and Bug Y late-reply design.

In scope: C1, C9, C11, C12, and C13. Out of scope: C3, C6, C8, C5 fuzzy-name
quality, retired `block` behavior, and `reminder-fire-missing-delivery-route`.

## Evidence caveat

The supplied evidence is still useful for layer tracing, but its embedded
`agent_sessions` are not a clean post-X runtime snapshot. C1/C9/C12 reasoning
still quotes the old broad coach-booking refusal prompt, and the run model is
`Pro/MiniMaxAI/MiniMax-M2.5`. Current `main` has commit `1b572360` removing that
prompt text from `agent/prompt/character/coke_prompt.py`,
`agent/prompt/onboarding_prompt.py`, and
`agent/agno_agent/runtime/chat_response_instructions.py`.

This design uses the JSON and live Mongo rows for layer tracing, then proposes
runtime-side fixes that should still hold after X: deterministic scheduling
routing and safer scheduling-domain failure summaries. The fix codex must
rerun the smoke on current `main`.

## Layer findings

The generic text `我没接住你刚才的意思。你可以换个说法再说一次吗？` comes from
`agent/runner/output_delivery.py::_chat_response_timeout_fallback` after
`agent/runner/agent_handler.py` sees runtime status `empty` and no visible
messages.

For C1, C9-create, C11, and C12-Jin, the bridge is not producing the fallback.
The evidence has concrete `outputmessages` rows with
`metadata.business_protocol.delivery_mode=request_response`, `status=handled`,
and the fallback text. That means the worker wrote the fallback after the
Agno runtime returned empty visible output.

For C13, the evidence snapshot has a bridge sync receipt, not worker fallback.
Live Mongo later shows real output `6a147db200057ec4fa6ba88f`, promoted to push
and failed delivery because the smoke account has no route. That is Bug Y's
expected post-fix shape, while routing is still wrong.

## Case trace

| Case | Evidence rows | Responsible layer | Trace |
| --- | --- | --- | --- |
| C1 request | input `6a147c5bfaa30a05626cb177`, output `6a147c6000057ec4fa6ba669`, session `6a147c60faa30a05626cb48c` | outer chat agent plus runtime fallback | The model produced only whitespace (`content='\n\n\n'`), called no tool, and reasoned from the old broad refusal prompt. The handler then wrote the empty fallback. No scheduling-domain result existed. |
| C1 accept | input `6a147c61faa30a05626cb584`, output `6a147c6900057ec4fa6ba67c`, session `6a147c69faa30a05626cbb36` | expected downstream failure after C1 create | The coach accept turn did call `scheduling_domain` with `accept_shared_reminder`, but there was no pending request because C1 request never created one. |
| C9 create | input `6a147d5efaa30a05626d700d`, output `6a147d7000057ec4fa6ba829`, session `6a147d70faa30a05626d7e45` | scheduling-domain argument normalization plus runtime fallback | The model called `scheduling_domain` for `create_shared_reminder`, but supplied `date_time` instead of `fire_at`; the gateway returned `invalid_body`. It then called `reminder_domain`, got `no_action`, and final visible output was empty/fallback. |
| C9 reject | input `6a147d72faa30a05626d7ecb`, output `6a147d7d00057ec4fa6ba83f`, session `6a147d7dfaa30a05626d873a` | missing create precondition plus weak operation alias | The reject turn was not itself empty in this run. It called `scheduling_domain` with `{"operation":"reject_shared_reminder","friend_name":"Kai"}`, which the normalizer did not understand, so the tool returned `scheduling intent could not be resolved`. Even a correct reject would fail until C9 create lands a pending request. |
| C11 past time | input `6a147cd2faa30a05626d07cd`, output `6a147cdc00057ec4fa6ba74a`, session `6a147cdcfaa30a05626d0fcc` | runtime final assembly / contract, with missing scheduling routing | The model called `reminder_domain`, got `no_action`, then produced raw text about yesterday's appointment. The user saw the fallback. The shared-reminder scheduling path was never selected, so the system never reached the scheduling/runtime rule that should reject past one-shot time. |
| C12 Mei | input `6a147dd8faa30a05626dca31`, output `6a147de000057ec4fa6ba8db`, session `6a147de0faa30a05626dd59b` | old prompt refusal, not empty fallback | It called `reminder_domain`, got `no_action`, and sent refusal/reminder-offer text. This is Bug X residue in the evidence, not a runtime empty row. |
| C12 Jin | input `6a147dd8faa30a05626dca2f`, output `6a147de400057ec4fa6ba8f6`, session `6a147de4faa30a05626dda82` | runtime fallback after wrong domain path | The model called `reminder_domain`, got `no_action`, then produced non-envelope refusal text. The user saw the empty fallback. With current runtime this raw final text may no longer be dropped, but the wrong domain path remains: it should be shared-reminder scheduling, not personal reminder. |
| C12 Kai | input `6a147dd8faa30a05626dca39`, output `6a147de000057ec4fa6ba8e2`, session `6a147de0faa30a05626dd5dc` | old prompt refusal, not empty fallback | It followed the same refusal/reminder-offer shape as C12 Mei. |
| C13 overview | input `6a147d96faa30a05626d96af`, evidence snapshot output none, live output `6a147db200057ec4fa6ba88f`, session `6a147db2faa30a05626dad7b` | wrong intent routing plus bridge late-push path | The agent first replied that it could not query a course table, called unknown `get_coach_schedule`, then called `reminder_domain` list and found one personal reminder projection. It did not route to `list_shared_reminders`. |

## Root cause

Bug X removed the broad prompt refusal, but the runtime still depends too much
on the outer chat model to decide whether coach/class wording is unsupported
external booking or supported in-product shared-reminder scheduling.

The current deterministic scheduler preselector only catches explicit product
terms such as `共享提醒` and friend-link phrases. It does not catch:

- `约教练 Alex 明天 10:00 上一节课`
- `拒绝 Kai 的预约`
- `我今天有几节课？列一下我今天的课程`

When the model does not route these to `scheduling_domain`, the request either:

- becomes a direct empty/refusal final answer,
- falls into `reminder_domain` as a personal-reminder non-action,
- or calls `scheduling_domain` with model-shaped structured args that can bypass
  the inner worker and fail on minor field names.

That explains why the hunt moved from Bug C broad refusal to Bug B/fallback:
removing the refusal exposes missing deterministic routing and brittle
domain-call normalization.

## C11 regression

C11 previously passed because the broad refusal prompt made "yesterday" plus
"book coach" become a refusal. That was a prompt-side accidental success, not
the right product layer.

After X, C11 should route to `create_shared_reminder`, let the
scheduling/reminder runtime reject the past one-shot fire time, surface
`这个时间已经过去了，请给我一个未来的上课时间。`, and leave no active shared request
or reminder projection.

Do not re-add the broad "coach booking unsupported" line. If a prompt change is
absolutely needed after the runtime fix, add at most one narrow line to the
domain execution result contract:

```text
If scheduling_domain reports a past scheduled time, tell the user the time is already past and ask for a future time.
```

Runtime is preferred because past-time validity belongs to the scheduling
contract, not to the character persona.

## C13 overview

C13 is a list-style query over the coach's own course/shared-reminder schedule.
It did not map to `list_shared_reminders`. The model invented an unsupported
`get_coach_schedule` intent, then fell back to `reminder_domain` list. The later
reply happened to find a Reminder Runtime projection, but it was polluted by an
initial "I cannot query the course table" sentence and did not use the shared
reminder contract.

The correct product mapping should be `list_shared_reminders` for the current
account, with a local date range for "today". Current gateway
`list_shared_reminders` requires `friend_name`; that is too narrow for "my
courses today" and should be extended to allow no friend filter when the caller
is listing the current account's own shared reminders.

## Proposed fixes

### 1. Runtime preselector for coach/class shared reminders

Extend `_infer_scheduling_intent_from_message` with a narrow product-routing
rule:

- create: scheduling verb such as `约`, `预约`, `安排`, or `上课` plus a named
  counterparty token and class/lesson wording -> `create_shared_reminder`.
- accept/reject/cancel: matching decision verb plus `预约` / `课` / `课程` ->
  `accept_shared_reminder`, `reject_shared_reminder`, or
  `cancel_shared_reminder`.
- overview: "我今天/明天有几节课" or "列一下我的课程" ->
  `list_shared_reminders` with date range support.

This should be a routing rule only. It must not create external booking claims
and must not synthesize success. Gateway friend resolution remains the fail-closed
authority.

### 2. Do not let incomplete outer structured args bypass the inner worker

Keep forced-args support for complete structured `create_shared_reminder` calls,
but harden it:

- Normalize `date_time` to `fire_at` if forced args are otherwise complete.
- Normalize `operation` as an alias for `intent` / `action` for accept/reject/cancel
  shared-reminder calls.
- If forced `create_shared_reminder` args still lack counterparty, `title`, or
  `fire_at`, ignore them and call `run_scheduling_domain` with intent
  `create_shared_reminder` so the inner worker parses the user message.

This avoids another C9 shape where a single model field name (`date_time`)
turns into `invalid_body` and then empty fallback.

### 3. Surface scheduling-domain failure summaries

Extend domain visible-text resolution for scheduling failures that carry a safe
`summary`, especially past one-shot schedule, friend not found, pending shared
reminder not found, and invalid body caused by missing required fields.

The current `_resolve_domain_visible_text` only returns summaries from executed
successful operations. For a preselected scheduling turn, a failed operation
with a safe summary should still be visible; otherwise the runtime can return
empty even though the domain layer knows the user-safe answer.

### 4. C13 list-all shared reminders

Extend gateway internal `list_shared_reminders` so `friend_name` is optional:
with `friend_name`, keep current friend-filtered behavior; without it, list
shared reminders involving the current account. Add optional `from_date`,
`to_date`, and `timezone` for local-day filtering.

Then update the scheduling worker prompt and runtime preselector so "my courses
today" uses `list_shared_reminders` rather than `get_coach_schedule` or
`reminder_domain`.

## Risk analysis

- This does not reintroduce Bug X's broad refusal. The routing maps in-product
  friend coach/class wording to shared reminders and leaves gateway resolution
  to fail closed when no active friend exists.
- This does not conflict with `_is_reminder_capability_offer_not_write_claim`.
  The fix reduces reminder-offer fallbacks by avoiding `reminder_domain` for
  shared-reminder class scheduling; it does not weaken the reminder write guard.
- This does not re-enable external booking hallucination. The final reply still
  cannot claim a write unless a scheduling operation returns `ok=True` and
  `effect=write`; failed/no-friend cases must say the shared reminder was not
  created.
- The main product risk is over-routing casual class talk to shared-reminder
  scheduling. Limit the preselector to directive verbs plus a counterparty/time
  or accept/reject/cancel wording, and add unit tests for casual mentions that
  must remain direct answers.
- The C13 gateway expansion changes API behavior. It is not a compatibility
  shim; it is the current product need for current-account shared-reminder
  overview queries. Keep it internal-agent-only unless a customer route needs it.
- Do not change the model configuration. The fix should work with the locked
  GLM-5.1 thinking-off policy where applicable, and must not depend on a model
  swap.

## Verification plan

Focused unit tests:

- `tests/unit/agent/test_agent_runtime_construction.py`: preselects create and
  reject coach/class shared-reminder intents; normalizes `date_time` and
  `operation`; falls back to the inner worker for incomplete forced create args.
- `tests/unit/agent/test_execution_agents.py`: exposes only
  `create_shared_reminder` for coach-class create intent and returns safe failed
  scheduling summaries to the outer runtime.
- `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`:
  `list_shared_reminders` works without `friend_name`, date range filters today,
  and existing friend-filtered behavior still passes.
- Existing guardrail tests: runtime output rules, chat response instructions,
  default character bootstrap, and reminder intent capability.

Suggested command set after implementation:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_construction.py \
  tests/unit/agent/test_execution_agents.py \
  tests/unit/agent/test_agent_runtime_output_rules.py \
  tests/unit/agent/test_chat_response_instructions.py \
  tests/unit/agent/test_default_character_bootstrap.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  -q
cd gateway && pnpm test -- internal-scheduling-routes.test.ts
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Smoke rerun after implementation:

```bash
.venv/bin/python tools/agent_smoke/_runner_phase_coach_booking_hunt.py
```

Expected outcomes:

- C1 creates one pending `shared_reminder_request`; coach accept can move it to
  accepted and create both reminder projections.
- C9 create creates one pending request; coach reject moves it to `rejected`
  and does not create invitee projection.
- C11 refuses the past time with a user-safe future-time question; no shared
  request or reminder projection remains active.
- C12 creates three independent pending requests, one per student, with no
  empty fallbacks and no causal-id hijack.
- C13 routes through `list_shared_reminders` and replies with the coach's own
  shared-reminder courses for today; if smoke lacks a delivery route after a
  sync timeout, the real late row may still become `status=failed`, which is
  expected fixture behavior rather than Bug B.

Also rerun the refusal smoke:

```bash
.venv/bin/python tools/agent_smoke/_runner_phase_class_booking_refusal.py
```

It must still show no external booking confirmation, no hidden personal
reminder for unsupported direct booking prompts, and no empty fallback.

## Reviewable summary

- The empty fallback rows for C1, C9-create, C11, and C12-Jin are worker/runtime
  fallbacks, not bridge fallbacks.
- C13 is a bridge timeout receipt followed by a late real reply; its remaining
  bug is wrong overview routing, not the generic empty fallback.
- The primary fix is runtime-side deterministic routing from friend coach/class
  directives to shared-reminder scheduling.
- The second fix is to harden scheduling-domain arg normalization so partial
  outer structured args do not bypass the inner worker and fail as `invalid_body`.
- C11 should be rejected by scheduling/runtime past-time validation, not by
  restoring broad coach-booking refusal prompt text.
- C13 needs `list_shared_reminders` to support current-account list queries
  without a required friend filter.
- Verification must rerun both coach-booking hunt and class-booking refusal
  smoke to prove Bug B is fixed without reintroducing Bug C.
