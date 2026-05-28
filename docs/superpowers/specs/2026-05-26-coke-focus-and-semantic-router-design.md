---
kind: design_spec
status: draft
authors:
  - Spec A lane
created: 2026-05-26
related:
  - docs/issues/2026-05-26-product-action-context-model.md
  - docs/issues/2026-05-25-product-notification-outbound.md
  - docs/issues/2026-05-25-shared-reminder-notification-missing-context.md
  - docs/design-docs/prompt-rule-ownership.md
  - docs/superpowers/specs/2026-05-26-coke-context-system-design.md
---

# Coke Focus And Semantic Router Design

## 1. Problem statement

The trigger bug was Eva's reply to a shared-reminder invitation. Coke
delivered a shared-reminder request notification with the expected trusted
`metadata.product_notification`; Eva later replied `确认`; the runtime answered
from stale friend-invite conversation context instead of treating the message
as a response to the latest shared-reminder request. The correct runtime path
should have bound the turn to the shared-reminder request and then surfaced the
current domain state, including the fact that the request may already have
expired.

Two related incidents show the same context boundary weakness from adjacent
directions:

- `docs/issues/2026-05-25-product-notification-outbound.md`: product
  notifications were marked delivered without a WeChat push path, then later
  replies still failed when trusted notification context was not propagated or
  was hidden behind formatted input text.
- `docs/issues/2026-05-25-shared-reminder-notification-missing-context.md`:
  invitee notifications lacked requester, title, local time, and duration, so
  the user could not make an informed accept/reject decision even when delivery
  itself succeeded.

The common failure is not only a missing keyword. It is that the runtime has no
typed current-action focus, does not syntactically separate trusted product
context from ordinary transcript text, and relies on deterministic
keyword/regex routing over user utterances before the authoritative domain
state is rechecked.

This document is the governing design for the decision-layer boundary. When
other architecture docs, prompt-ownership docs, or dated specs are ambiguous
about whether the final response model should classify intent, choose business
tools, or only render the final user-visible answer, this spec wins.

The target contract is:

- A decision layer, implemented as the semantic interpreter or a domain-specific
  detector, is the first and only owner of user-utterance intent classification
  for product actions.
- Domain executors and capability ports own business tool execution, permission
  checks, freshness checks, concrete arguments, and durable writes.
- The Interaction Agent owns final user-visible prose. It consumes trusted
  Focus, semantic intent, and `DomainExecutionResult` facts; it does not decide
  whether a business action should be routed to scheduling, reminder, friendship,
  or another product domain.
- Any remaining `chat_response` delegation prompt, Interaction Agent business
  tool exposure, or response-prompt domain selection is transitional
  compatibility and must be migrated toward this boundary.
- Provider/model configuration must preserve the same ownership split. A model
  role named `chat_response` is for response synthesis, not scheduling or
  reminder execution. Executor agents should use executor-specific roles when
  provider selection matters.

The target user-visible behavior is that an explicit action request such as
`帮我和 olivers 约一个明天上午九点的测试会议` is classified before response
synthesis, executed by the scheduling domain when valid, and then confirmed from
trusted execution facts. A fact query such as `我现在有几个好友？` is likewise
classified as a domain read before the final response is generated; the response
model must not answer from a missing-capability assumption when the domain has a
read capability.

## 2. In-scope

### A. Typed Focus channel

Add a typed Focus channel representing the one actionable business object the
current turn may act on. It is computed at run start and exposed via
`RunContext.session_state`.

The Focus channel has exactly these action fields:

- `action_id`: stable business id, such as a friend request id or shared
  reminder request id.
- `kind`: product action kind, such as `friend_request` or
  `shared_reminder_request`.
- `allowed_actions`: action verbs valid for this focus, such as `accept` and
  `reject`.
- `status`: current domain status observed at focus construction time.
- `expires_at`: optional expiry timestamp.
- `summary_for_llm`: deterministic, compact, user-safe summary text for prompt
  rendering.

The channel also carries channel-level `ambiguity` with exactly these values:

- `none`: one actionable focus exists.
- `multi_pending`: two or more actionable candidates compete and the runtime
  must not guess.
- `none_actionable`: no actionable candidate exists.

Focus construction reads authoritative product state at run start. It may use
recent product-notification metadata as an input, but it must not derive the
target action from the chat transcript.

### B. Prompt trust framing

Replace flat runtime instructions with explicitly tagged trusted blocks plus a
single conversation block:

```xml
<trusted kind="identity">
  ...
</trusted>
<trusted kind="environment">
  ...
</trusted>
<trusted kind="focus">
  ...
</trusted>
<conversation>
  ...
</conversation>
```

The prompt contract is:

- Trusted blocks are authoritative system-derived facts.
- The conversation block is language evidence only; it may be stale,
  contradictory, adversarial, or incomplete.
- On conflict, trusted blocks win.
- If `<trusted kind="focus">` is empty or marks `ambiguity=multi_pending` or
  `ambiguity=none_actionable`, the model asks a clarifying question rather
  than acting on transcript signal.
- The prompt must not contain multiple trusted representations of the same
  volatile fact.

This is a narrow Spec A trust framing. L3 chat-history single-source decisions
are explicitly out of scope.

### C. Semantic interpreter

The semantic interpreter fully replaces the deterministic pre-router for user
utterance intent classification. It reads `(focus, current_utterance)` and
returns a typed intent.

It also replaces the final response prompt as the first business-action
classifier. The main response model may phrase a clarification or final answer,
but it must not be the first component that decides whether a turn is a
friendship action, shared-reminder action, reminder action, availability query,
or ordinary conversation. If a domain action or domain read is possible, the
decision layer emits the typed domain intent or an explicit `ambiguous` /
`unrelated` result before response synthesis.

When `focus` is present with `ambiguity=none`, the intent enum is:

- `accept`
- `reject`
- `ask_detail`
- `request_change`
- `unrelated`
- `ambiguous`

When `focus` is `None` or `ambiguity=none_actionable`, the interpreter may
return scheduling-intent variants for explicit user directives, using the
current scheduling domain vocabulary:

- `create_shared_reminder`
- `accept_shared_reminder`
- `reject_shared_reminder`
- `cancel_shared_reminder`
- `send_friend_request_by_user_link_code`
- `list_friend_requests`
- `accept_friend_request`
- `reject_friend_request`
- `cancel_friend_request`
- `list_friends`
- `remove_friendship`
- `get_user_link`
- `reset_user_link`
- `disable_user_link`
- `list_friend_calendar_facts`
- `list_shared_reminders`
- `unrelated`
- `ambiguous`

For scheduling-intent variants, the structured output may include typed
arguments such as `request_id`, `user_link_code`, `friend_name`,
`invitee_name`, `from_date`, `to_date`, `timezone`, and `message`. Argument
validators may reject malformed values after semantic classification, but they
must not classify user intent through keyword or regex matching.

The interpreter output is the routing contract, not a hint for the response
prompt. Runtime code should pass a valid domain intent to the matching executor,
or pass a no-action/clarification decision to response synthesis. The response
model should receive the resulting trusted facts and reply contract, normally
with no business write tools exposed.

Two implementation options are allowed:

1. **Fused structured-output call alongside the main response LLM.** The
   interaction agent receives trusted blocks and the current utterance, then
   emits both a response envelope and a structured `semantic_intent` object.
   This minimizes extra round trips and can preserve KV-cache friendliness if
   trusted blocks use a stable prefix. The drawback is correctness coupling:
   action execution still needs a domain write after interpretation, so the
   fused answer cannot safely claim success until the executor freshness check
   has completed.
2. **Separate fast LLM call before the main response LLM.** A small structured
   interpreter call receives only Focus plus the current utterance, executes
   before domain mutation, and hands the typed intent to the domain executor or
   to the response LLM. This adds one model round trip, but keeps intent
   evaluation, executor freshness, and response synthesis independently
   testable.

Recommendation: use option 2, the separate fast LLM call, for the first
implementation. The extra latency is acceptable because it buys clear failure
boundaries, easier corpus evaluation, no action-success claims before DB
freshness, and a direct replacement for the current deterministic pre-router.
Treat fused interpretation as a later optimization after the representative
corpus and live smoke prove the separate interpreter's behavior.

Multi-pending handling is fail-closed. If Focus marks `multi_pending`, the
semantic interpreter may classify the utterance as `ask_detail`, `unrelated`,
or `ambiguous`, but it must not choose one pending action from transcript
clues. The response asks the user which pending request they mean, using
trusted candidate summaries.

### D. Executor freshness check

Every domain mutation re-queries authoritative DB state immediately before
writing. The executor must treat Focus as a pointer, not as fresh state.

Executors are responsible for concrete tool choice inside their domain. For
example, scheduling execution maps `list_friends` to the friendship read
capability and `create_shared_reminder` to the shared-reminder write capability.
This mapping belongs to executor code, schemas, tool signatures, and domain
prompts, not to the final response prompt.

For each write:

1. Read `focus.action_id`, `focus.kind`, and the semantic intent.
2. Re-query the authoritative domain store for that action.
3. Confirm the action still exists, is still owned by the current user or
   conversation route, is still in an allowed status, and has not expired.
4. Execute the mutation in the same domain boundary that checked the state.
5. If state moved, return a structured domain failure with a user-safe
   `visible_summary` and a `reply_contract` that prohibits success claims.

State moved cases include accepted by someone else, rejected elsewhere,
expired, canceled, missing, wrong recipient, or action no longer allowing the
requested verb.

### E. Response synthesis boundary

The Interaction Agent is the only owner of final chat prose, but final prose
ownership is not tool-routing ownership. Response synthesis receives:

- trusted identity, environment, and Focus blocks;
- the semantic intent or clarification decision;
- trusted `DomainExecutionResult` or `CapabilityResult` facts;
- a reply contract describing required facts, required questions, prohibited
  claims, and whether rephrasing is allowed.

The response model must:

- explain completed reads and writes from trusted facts;
- ask required clarification questions when the decision layer or executor
  reports ambiguity;
- report structured domain failures without inventing missing capabilities;
- never claim a durable write unless the domain result reports a successful
  write effect;
- never retry or choose an alternate business domain after a trusted executor
  result unless the runtime explicitly starts a new decision pass.

In the steady-state architecture, response-only repair or protocol retries may
reuse trusted domain results, but they must not re-expose durable-write tools.
This preserves user-visible wording flexibility without letting the response
model become a hidden router.

## 3. Out-of-scope (Spec B')

The following are deliberately parked for Spec B' and must not be implemented
as part of this design:

- L3 chat-history single-source decisions, including the S1 vs S2 question and
  the Agno `add_history_to_context` decision.
- L4 persisted event log design.
- L7 long-term memory ontology, retrieval, activation, and decay.
- Memory compaction pre-flush.

Spec A may expose Focus through `RunContext.session_state` and may reshape the
prompt trust framing, but it must not solve storage ownership for chat history,
event logs, or long-term memory.

## 4. Hard policy constraints encoded in spec

### No keyword or regex routing on user utterances

There must be no keyword or regex routing on user utterances anywhere in the
Spec A path. All user intent classification moves to the LLM semantic
interpreter. This includes short confirmations, negative replies, friend-link
actions, shared-reminder actions, coach/class scheduling phrases, course
overview phrases, and change requests like `改成` or `先不要`.

Regex or string checks may remain only for non-semantic safety/output
guardrails, JSON parsing, explicit typed payload validation, and trace or
environment mechanics. A validator may say "this returned link code is
malformed"; it may not say "because this utterance contained `链接码`, classify
it as a friend request."

### Safety and guardrail regex verdicts

- `_RETIRED_ACCOUNT_CONTROL_RE`: migrate. Preserve the retired-account-control
  failure behavior, but stop detecting it through a user-utterance regex in
  `run_agent_runtime`. The semantic interpreter should return an unsupported
  scheduling/domain intent, or the scheduling domain should reject the typed
  intent with `retired_account_control`.
- `_UNCONFIRMED_DURABLE_WRITE_PATTERNS`: keep as an output guardrail. It runs
  on generated visible text after tool execution and prevents unsupported
  success claims. It does not classify user intent.
- `_VISIBLE_IDENTIFIER_LEAK_PATTERNS`: keep as an output guardrail. It detects
  internal ids in final text, not user intent.
- `_CAPABILITY_BOUNDARY_MARKERS`, `_REMINDER_OFFER_MARKERS`, and
  `_COMPLETED_WRITE_CLAIM_PATTERNS`: keep temporarily as output-guardrail
  support. They should be migrated later to stricter domain-result contracts,
  but they are not part of routing.
- `_FENCED_JSON_RE`, `_LENIENT_ENVELOPE_RE`, and `_LENIENT_CONTENT_RE`: keep.
  They recover model output envelopes and do not inspect user utterances for
  action routing.
- `chat_response_instructions._FORBIDDEN_LINE_PATTERNS`: keep. It strips legacy
  prompt lines and does not classify user intent.

### Eval corpus

Build a representative 30-50 case corpus, not a full-corpus migration gate.
The subset must cover:

- Single-pending accept variants, including `确认`, `好`, `可以`, `那我参加`,
  `yes`, `ok`, and English accept forms.
- Single-pending reject variants, including `拒绝`, `不通过`, `不同意`,
  `我不太方便`, `decline`, and `reject`.
- Multi-pending ambiguity, with two or more pending actions and short replies.
- Ask-detail cases such as `谁发的？`, `几点？`, `这是什么？`.
- Request-change cases such as `可以改晚一点吗？`, `改到明天`, `换个时间`.
- Stale-focus cases where the focused action has already moved state.
- Expired-focus cases where the action exists but is no longer actionable.
- Unrelated utterances while focus exists.
- Negative controls, especially phrases like `先不要`, `先不要急着`, and
  `不要现在处理`, which the current keyword router can false-positive as reject.

The corpus should record expected semantic intent, expected executor behavior,
and expected response class. It should not require exact wording except where
the domain failure summary is contractually fixed.

### Latency and cost tradeoff

The separate interpreter call should use a small structured-output model with
bounded input:

- Trusted Focus block: target 150-300 tokens.
- Current utterance: target 1-80 tokens, hard cap around 200 tokens.
- Static interpreter instructions and schema: target 300-600 tokens.
- Output: target 20-80 tokens.

Expected added latency for the separate call is 200-600 ms p50 and 700-1500 ms
p95 in normal network conditions, depending on model/provider. It is
cache-friendly because the static schema and prompt prefix are stable, while
Focus and utterance are short.

The fused option avoids an extra network round trip and may save 200-1500 ms
when no domain mutation is needed. However, it is less cache-friendly for the
intent decision because the large response prompt, conversation block, and
tool context change more often. More importantly, it cannot safely combine
intent, domain mutation, and final success wording in one pass unless the
response is delayed until after the executor freshness check. That complexity
is not worth it for the first rollout.

Recommendation: ship separate interpreter first; measure interpreter p95,
overall turn p95, token count, domain-failure rate, and clarification rate;
then revisit fused interpretation as an optimization only if latency is the
dominant production problem.

## 5. Appendix: retired keyword/regex paths

This appendix enumerates keyword/regex routing paths found in
`agent/agno_agent/runtime/agent_runtime.py` plus directly related utterance
routing or prompt-routing surfaces found during targeted search. "Retire" means
remove from user-utterance intent routing. "Migrate" means preserve the product
behavior through the semantic interpreter, typed validation, or a domain
failure path.

| File | Function or variable | Current behavior | Retirement disposition |
| --- | --- | --- | --- |
| `agent/agno_agent/runtime/agent_runtime.py` | `_contains_any` | Generic substring helper used by scheduling intent routing, output arbitration, and guardrails. | Retire from user-utterance routing. Keep only for non-routing output guardrails if still needed. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_product_notification_decision` | Normalizes short text with `re.sub`, caps length at 16, then maps reject/accept substrings such as `拒绝`, `不要`, `确认`, `好`, `yes`, and `ok`. | Retire. Replace with semantic interpreter over `(focus, current_utterance)`. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_infer_scheduling_intent_from_product_notification` | Converts `_product_notification_decision` plus `request_type` into `accept_friend_request`, `reject_friend_request`, `accept_shared_reminder`, or `reject_shared_reminder`. | Retire. Focus binds the action; semantic intent maps accept/reject; executor maps kind plus action to a domain operation. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_infer_scheduling_intent_and_args_from_agent_input` | Runs the product-notification pre-router, falls back to the general scheduling keyword router, and forces args such as `request_id`. | Retire as deterministic pre-router. Replace with Focus construction plus separate semantic interpreter result. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_infer_scheduling_intent_from_agent_input` | Thin wrapper returning only the deterministic preselected scheduling intent. | Retire with the pre-router. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_friend_request_link_args` | Uses regexes for `链接码`, `邀请码`, `link code`, `/u/<code>`, and `备注/note` to extract friend-link args after keyword routing. | Migrate. The semantic interpreter returns typed args; validators may check code shape after classification. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_infer_scheduling_intent_from_message` | Main deterministic scheduling keyword router for user links, friend requests, remove/list friends, friend calendar availability, shared-reminder status/accept/reject/cancel/create/list, and own user-link actions. | Retire. All intent classification moves to the semantic interpreter. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_RETIRED_ACCOUNT_CONTROL_RE` | Regex detects `屏蔽`, `拉黑`, `解除屏蔽`, `block`, and `unblock` and routes to a retired-feature failure. | Migrate. Keep the safety behavior, but classify through semantic intent or domain unsupported-intent handling, not regex routing. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_is_retired_account_control_turn` | Applies `_RETIRED_ACCOUNT_CONTROL_RE` to `_latest_user_turn_text`. | Migrate with `_RETIRED_ACCOUNT_CONTROL_RE`. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_infer_coach_class_scheduling_intent` | Keyword/regex router for coach/class appointment phrasing, including accept/reject/cancel shared reminder and create shared reminder. | Retire. Covered by scheduling-intent variants from the semantic interpreter. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_has_named_counterparty_token` | Regex detects an ASCII token as a named counterparty for coach/class routing. | Retire from routing. Replace with semantic typed arg extraction and validation. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_has_time_wording` | Regex detects Chinese relative dates, weekdays, day periods, and clock forms for coach/class routing. | Retire from routing. Date/time parsing belongs in domain validation after semantic intent. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_is_course_overview_query` | Regex and keywords detect `我今天/明天有几节课` and course listing phrases. | Retire. Interpreter returns `list_shared_reminders` with a typed date range or asks clarification. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_shared_reminder_overview_range_args` | Uses `_is_course_overview_query` and the keyword `明天` to derive `from_date`, `to_date`, and timezone. | Migrate. Date range should come from semantic output plus domain date normalization, not keyword routing. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_explicit_friend_request_write_intent` | Re-runs the scheduling keyword router to override model-selected `list_friend_requests` when the utterance looks like accept/reject/cancel. | Retire. Structured interpreter output should be the only intent source. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_normalize_scheduling_intent` | Normalizes model-supplied scheduling tool intent and repeatedly falls back to `_infer_scheduling_intent_from_message` when input is blank, unknown, or mapping-shaped. | Migrate. Keep schema normalization for structured interpreter output; remove all keyword-router fallbacks. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_normalize_scheduling_intent_args` | Renames and filters structured args, including create-shared-reminder field aliases. | Keep as typed output normalization if it no longer classifies intent from user text. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_split_scheduling_intent_args` | Parses an already-normalized `intent: {json}` string into tool name and args. | Keep short term for compatibility with typed model output; prefer replacing string envelopes with a typed schema. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_should_prefer_domain_visible_text` | Uses keywords such as `等一下`, `先取消`, `取消刚才`, `改成`, `wait`, and `instead` to prefer domain visible text when batched messages imply a correction. | Migrate. The semantic interpreter should emit `request_change`; response selection should prefer structured domain results, not keyword evidence. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_latest_user_turn_text` | Splits formatted input with regex `（[^）]*发来了文本消息）` and returns the latest user text. | Keep only as temporary input normalization. Long term, use a structured current-utterance field from the payload. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_explicit_past_reminder_precheck` | Calls `reminder_intent._REMINDER_VERB_PATTERN`, `_single_relative_delay`, and `_explicit_past_time_evidence` before the main agent run to fail explicit past reminder creates. | Migrate out of `run_agent_runtime` pre-routing. Keep the failure behavior inside the reminder domain semantic path. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_retired_account_control_result` | Builds the structured failure result used by the retired account-control regex path. | Keep the result contract, but call it from semantic/domain unsupported-intent handling. |
| `agent/agno_agent/runtime/agent_runtime.py` | `run_agent_runtime` preselected scheduling block | Calls `_explicit_past_reminder_precheck`, `_is_retired_account_control_turn`, and `_infer_scheduling_intent_and_args_from_agent_input`; preloads scheduling domain result before the response agent. | Retire deterministic preselection. Replace with Focus, semantic interpreter, executor freshness check, then response synthesis. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_UNCONFIRMED_DURABLE_WRITE_PATTERNS` | Regexes detect final responses that claim reminder/shared-reminder/friend-request writes without a successful durable write. | Keep as output safety guardrail; not a user-utterance router. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_VISIBLE_IDENTIFIER_LEAK_PATTERNS` | Regexes detect leaked internal ids such as `ck_...` and `acct_...` in final visible text. | Keep as output safety guardrail. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_CAPABILITY_BOUNDARY_MARKERS`, `_REMINDER_OFFER_MARKERS`, `_COMPLETED_WRITE_CLAIM_PATTERNS`, `_is_reminder_capability_offer_not_write_claim` | Keyword/regex carve-out so capability-boundary offers are not mistaken for completed durable writes. | Keep temporarily as output guardrail support; migrate later to stricter response contracts if possible. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_FENCED_JSON_RE`, `_LENIENT_ENVELOPE_RE`, `_LENIENT_CONTENT_RE`, `_try_parse_envelope_json`, `_recover_lenient_envelope` | Regexes recover structured model response envelopes from markdown or malformed JSON-like text. | Keep. These parse model output, not user intent. |
| `agent/agno_agent/runtime/agent_runtime.py` | `_is_safe_scheduling_failure_summary` | Filters unsafe failure summaries using infrastructure keywords such as `traceback`, `postgres`, `sql`, and `exception`. | Keep as output safety filtering; not routing. |
| `agent/agno_agent/runtime/chat_response_instructions.py` | `_DELEGATION_BOUNDARY` | Prompt text instructs the main LLM to call scheduling tools based on explicit keyword examples such as accept/reject/cancel/list shared reminders and friend requests. | Migrate. Replace with trusted Focus framing and semantic interpreter results; main response prompt should not be the first intent classifier. |
| `agent/agno_agent/runtime/chat_response_instructions.py` | `_runtime_context_block` product-notification line | Renders `product_notification` into a flat "Trusted runtime context" block. | Migrate to `<trusted kind="focus">` and remove flat product-notification prompt routing. |
| `agent/agno_agent/runtime/chat_response_instructions.py` | `_FORBIDDEN_LINE_PATTERNS` and `_strip_legacy_artifacts` | Regexes remove obsolete output-format prompt lines. | Keep. This is prompt cleanup, not utterance routing. |
| `agent/agno_agent/capabilities/reminder_intent.py` | `_REMINDER_VERB_PATTERN`, `_single_relative_delay`, `_explicit_past_time_evidence` as reached by `agent_runtime._explicit_past_reminder_precheck` | Regex-driven explicit-past reminder failure before the interaction agent runs. | Migrate into reminder-domain semantic handling so `agent_runtime.py` no longer pre-routes user utterances by regex. |
| `agent/agno_agent/capabilities/reminder_intent.py` | `ReminderIntentPort.run` pre-LLM helpers such as `_is_unsupported_booking_request`, `_explicit_reminder_list_decision`, `_is_recurring_occurrence_skip_text`, `_snooze_update_decision`, and `_fallback_decision_from_text` | Reminder domain contains additional regex/keyword helpers around its existing LLM detector. | Park outside Spec A except for the explicit-past runtime precheck. If the "no regex anywhere" policy is applied repository-wide, this domain needs a follow-up migration plan so regexes become validators or domain constraints rather than intent classifiers. |
| `agent/runner/agent_handler.py` | product-notification metadata extraction into `runtime_metadata` and `product_notification_input_text` | Preserves trusted product-notification context and raw reply text for runtime routing. | Migrate. Keep metadata transport until Focus exists; then produce structured current utterance plus Focus inputs instead of feeding the deterministic pre-router. |
| `gateway/packages/api/src/lib/route-message.ts` | product-notification context attachment | Resolves recently delivered pending product notification and attaches trusted context to inbound metadata. | Migrate to Focus input production. This is not keyword routing, but it is part of the current action-binding path. |
