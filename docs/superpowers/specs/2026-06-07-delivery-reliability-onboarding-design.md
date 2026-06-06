---
status: approved-for-autonomous-implementation
created_at: 2026-06-07
scope:
  - Track B: waiting-message delivery recovery
  - Track F: notification recipient lifecycle
  - Track G: onboarding prompt wiring
---

# Delivery Reliability And Onboarding Design

## Context

Eva's RCA separated three reliability problems that share one boundary: the
Interaction Agent remains the single user-facing prose producer, while runtime
facts and delivery state determine whether output is safe to show, retry, or
record as complete.

This design implements only Tracks B, F, and G from
`docs/issues/2026-06-06-eva-chat-rca.md`. It preserves the D1 sole-producer
invariant. It does not add typed renderers, keyword routing, pending-approval
flows, prompt-only guarantees, a separate durable interruption artifact, or
product capabilities outside the current requirements baseline.

The two older waiting-reply fixes remain binding:

- `pending_async_reply` is an intermediate turn disposition.
- Waiting-message visibility never materializes staged commands, closes an input
  window, advances `conversation.last_closed_inbound_seq`, or proves progress to
  the user.

## Design Alternatives

### Recommended: diagnostic envelope plus guarded terminal settlement

Add structured delivery metadata to outbound delivery attempts and make waiting
delivery use logical intents (`turn_id:waiting:1`, `turn_id:waiting:2`) instead
of reusing one provider idempotency key. The first attempt is always diagnostic.
One jittered retry is allowed only for retryable transport failures, only while
the turn is still non-terminal, and only when the per-route/account circuit
breaker allows another waiting attempt.

Notification recipient settlement is fixed in the primary terminal paths before
adding a reconciler. Every terminal `NotificationTurn` path records delivered,
failed, or undelivered recipient state with structured facts. The reconciler is
only a crash/history backstop for recipients that predate or escape the primary
settlement path.

Onboarding guidance becomes a trusted prompt block when
`onboarding_guidance_required` is true. The block uses the existing configured
agent settings and trusted `user_address_name`; there is no separate onboarding
settings schema today. `first_guidance_sent_at` is stamped only after a final
inbound onboarding reply is committed and all reply delivery requests reach a
visible state.

Trade-off: waiting retries remain in-process and bounded instead of becoming a
durable retry queue. That matches D5 because a waiting message is optional
visibility, while final replies remain the durable product path.

### Rejected: log-only diagnostics

Adding logs would help immediate triage but would not make failures buckettable
from durable state, would not separate waiting and final reply paths after the
fact, and would not explain idempotency-key reuse.

### Rejected: blind retry with the same provider key

Retrying `turn_id:waiting` is a no-op under current provider idempotency. Retrying
with a new opaque key can duplicate user-visible sends. Logical delivery intents
make the duplicate boundary explicit and bounded.

### Rejected: deterministic onboarding renderer

A deterministic first-use renderer could guarantee the exact onboarding text, but
it would create a second user-facing prose producer. Onboarding remains a trusted
prompt block consumed by the Interaction Agent, with structural stamping tied to
delivery state rather than to prompt compliance.

## Architecture

### Track B: delivery envelope

`DeliveryRequest` gains optional diagnostic fields that flow through
`ChannelReachabilityOutboundDelivery` into
`ChannelReachabilityService.send_text()` and the persisted `delivery_attempt`
row:

- `delivery_source`: `reply`, `waiting_timer`, or `waiting_sync_timeout`
- `delivery_intent`: logical send intent such as `turn_id:waiting:1`
- `retry_attempt`: `1` for the first logical attempt, `2` for the only retry
- `traceparent`: inbound/outbox trace context when available
- `container`: runtime hostname
- `context_token_source`: `trigger_payload`, `latest_inbound_message`, or `none`
- `context_token_age_seconds`: age of the token source at send time when known
- `latency_ms`: adapter send latency

Existing persisted fields continue to provide provider route, provider type,
provider idempotency key, message id, turn id, status, error code, and timestamps.
The new fields make waiting-vs-reply failures buckettable without changing the
provider adapter contract.

`ConversationRuntimeService` exposes a read-only context-token observation for a
conversation. Waiting sends use that observation so the diagnostic envelope can
name both source and age; synchronous timeout sends still use the trusted trigger
payload token when present.

### Track B: waiting retry policy

Waiting-message delivery is centralized in a small helper used by both
`coke-outbox-relay` (`waiting_timer`) and synchronous timeout handling
(`waiting_sync_timeout`). The helper:

1. records the waiting outbound message before delivery;
2. sends logical intent `turn_id:waiting:1`;
3. persists/logs the diagnostic envelope and outcome;
4. does not retry token/session-window failures such as
   `context_token_required`, `invalid_context_token`, or `ret_-2`;
5. retries retryable transport failures such as `provider_network_error` at most
   once with logical intent `turn_id:waiting:2`;
6. checks the current turn disposition after jitter and skips the retry if the
   turn is `replied`, `failed`, or `superseded`;
7. uses a per-route/account circuit breaker so repeated transport failures on the
   same destination suppress optional waiting retries.

The helper never changes the close boundary. A failed waiting attempt leaves the
turn in `pending_async_reply`; later final reply completion can still transition
the same turn to `replied`.

### Track F: primary notification settlement

`OutputLifecycleDeliveryCallbacks` remains the boundary that translates render
delivery facts into notification-recipient lifecycle state. The primary fix is in
`TurnRunner`: every terminal path for `NotificationTurn` must call lifecycle
settlement before returning:

- valid reply delivery records each recipient as delivered, failed, or
  undelivered according to delivery outcome;
- invalid render output records render failure for every target recipient;
- `no_reply` retry exhaustion records failure, because `NotificationTurn`
  requires visible output;
- turn failure before output records failure;
- supersession records failure with a superseded reason;
- lock/start/runtime failures record failure with the structured reason code.

Structured recipient facts stay informational. Retry paths never create
approval/action materialization.

### Track F: reconciler backstop

SocialScheduling exposes a reconciler that scans pending notification recipients
older than a threshold, checks their associated turn disposition, and settles only
when the turn is already terminal. The reconciler records facts such as
`notification_turn_terminal_without_recipient_settlement` and the terminal
disposition. It does not resend, approve, or perform user actions.

This backstop is not the primary settlement path. New completed render turns
should settle recipients before the reconciler sees them.

### Track G: onboarding prompt block

`TurnRunner` already receives `onboarding_guidance_required` from the identity
pre-LLM gate. When true for an inbound turn, it adds an `onboarding_guidance`
trusted fact built from:

- configured assistant name and persona/settings fields already returned by
  Settings;
- trusted `user_address_name` when configured;
- current product capabilities: reminders, shared reminders with friends,
  availability checks, and long-term memory/preferences when enabled.

`AgnoInteractionAgent.build_prompt_blocks()` renders this fact as a conditional
`onboarding_guidance` trusted block. The block instructs the single producer to
offer concise first-use guidance without claiming unsupported features. It must
not introduce external class booking, memo runtime, memo cards/search/review, or
other capabilities absent from `docs/product-requirements/current.md`.

### Track G: first guidance stamp

The first-guidance activation stamp is tied to visible final delivery, not prompt
construction. `TurnRunner` passes an onboarding flag into inbound reply completion
lifecycle only after:

- the output was a valid final reply;
- the reply was committed through `ConversationRuntimeService.commit_reply()`;
- every final reply delivery request returned `sent` or `delivered`.

`OutputLifecycleDeliveryCallbacks.record_inbound_reply_completed()` then calls
`IdentityAccessService.mark_first_guidance_sent()`. It does not stamp for invalid
output, `no_reply`, provider delivery failure, access-denied render turns,
supersession, or pending async waiting messages.

Async final replies preserve the original onboarding flag in `_AsyncState` so a
later visible final onboarding reply can stamp correctly, while the earlier
waiting message cannot.

## Data Flow

### Waiting message

1. Timeout/relay marks the turn `pending_async_reply`.
2. Runtime records a waiting outbound message with `message_type=waiting`.
3. Waiting delivery sends intent `turn_id:waiting:1` with diagnostic metadata.
4. Failed attempts persist as delivery attempts and logs.
5. A retryable transport failure may schedule intent `turn_id:waiting:2` if the
   turn is still non-terminal and the circuit breaker is closed.
6. Final reply delivery later closes the turn normally if the agent output
   succeeds.

### Notification render

1. Notification fact creation creates pending recipients.
2. Render trigger runs through the single producer.
3. Every terminal `NotificationTurn` path calls lifecycle settlement.
4. Recipient state becomes delivered, failed, or undelivered.
5. The reconciler only repairs old/crashed pending rows whose turns are already
   terminal.

### Onboarding

1. Identity gate marks first inbound received and computes
   `onboarding_guidance_required`.
2. Turn context and trusted facts carry the onboarding guidance block only for
   that turn.
3. The Interaction Agent returns normal JSON reply output.
4. Conversation runtime commits the reply and outbound delivery reaches visible
   state.
5. Inbound reply lifecycle stamps `first_guidance_sent_at`.
6. Later inbound turns omit the onboarding block because activation no longer
   requires first guidance.

## Structural Guards And Invariants

- The Interaction Agent remains the only normal user-facing prose producer.
- Waiting delivery retry never creates user-visible progress or closes input.
- Waiting delivery retry is bounded to one retry and cannot run on token/window
  failures.
- Notification terminal completion cannot leave a recipient pending.
- The reconciler cannot resend, approve, materialize, or otherwise act for the
  user.
- Onboarding prompt content is conditional on a trusted runtime flag and current
  product capabilities.
- First guidance is stamped only after visible final onboarding reply delivery.

## Test Plan

- Track B unit: provider `failed/provider_network_error` leaves the turn active,
  preserves staged commands, does not advance `last_closed_inbound_seq`, records a
  failed waiting delivery envelope, and later final reply transitions to
  `replied`.
- Track B unit: token/session-window failures do not retry.
- Track B unit: retryable waiting failure uses logical intents
  `turn_id:waiting:1` and `turn_id:waiting:2`.
- Track F unit: invalid `NotificationTurn` output settles all recipients failed.
- Track F unit/integration: a completed notification render turn cannot leave a
  recipient pending.
- Track F unit: reconciler settles stale pending recipients only after terminal
  completion.
- Track G prompt unit: first inbound with `onboarding_guidance_required` includes
  exactly one onboarding block with supported capabilities and no unsupported
  class-booking/memo wording.
- Track G runner/unit: later inbound turns omit the onboarding block.
- Track G lifecycle unit: `first_guidance_sent_at` stamps only after committed
  visible onboarding reply delivery and not on waiting, no-reply, invalid output,
  access denial, or provider delivery failure.

## Documentation

Update `docs/ARCHITECTURE.md` for the delivery attempt envelope, waiting retry
boundary, notification recipient settlement invariant/reconciler, and onboarding
first-guidance stamp rule. Update the schema migration and SQLAlchemy table in the
same change as delivery attempt metadata.
