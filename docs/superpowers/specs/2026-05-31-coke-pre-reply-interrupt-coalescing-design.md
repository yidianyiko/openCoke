# Coke Pre-Reply Interrupt Coalescing

Status: proposed
Created: 2026-05-31
Updated: 2026-05-31 (aligned with `docs/ARCHITECTURE.md` as the canonical
runtime contract before implementation planning)
Scope: interactive inbound turns, same-conversation interruption, Agno invocation,
freshness, and outbound close semantics
Architecture reference: `docs/ARCHITECTURE.md`, section "Interactive Input
Windows And Pre-Reply Interruption"

## 1. Problem

The clean runtime currently suppresses stale replies only at commit time. A turn
starts from one inbound message, holds the per-conversation execution path while
it runs, and discovers a newer inbound message only when it tries to commit a
reply or guarded state change.

That is not the product contract we need.

If a user sends a new message in the same conversation before receiving an
agent-visible reply, the active work must be interrupted quickly. The older
message is not discarded. The replacement turn must process the older and newer
messages together, in channel order, as one current input window.

The 2026-05-31 incident demonstrates the gap:

- inbound 1 was recorded at `2026-05-31 09:01:06.552896+00`
- inbound 2 was recorded at `2026-05-31 09:01:27.276933+00`
- the visible reply was persisted at `2026-05-31 09:08:34.625869+00`
- the first turn ran for roughly 270 seconds, was marked `superseded`, and only
  then allowed the second turn to run for another roughly 178 seconds

The user experienced this as a seven-minute wait because the runtime treated the
newer inbound as a stale-output guard, not as an active interruption signal.

## 2. Decision

Adopt **pre-reply input-window coalescing** for interactive turns.

For each conversation, the runtime maintains a closed input boundary and an open
input boundary:

- `conversation.latest_inbound_seq`: the highest durable inbound sequence ever
  recorded for the conversation.
- `conversation.last_closed_inbound_seq`: the highest inbound sequence that has
  already been covered by a durable close decision.

An interactive turn claims an ordered input window:

```text
input_from_seq = conversation.last_closed_inbound_seq + 1
input_to_seq   = conversation.latest_inbound_seq
```

Before any close decision is persisted, any newer inbound in the same
conversation extends the open window. The old running execution is superseded,
cancelled, and replaced by a new turn that covers:

```text
[old input_from_seq, new conversation.latest_inbound_seq]
```

The window closes only when the runtime durably persists the first close
decision for that window: a user-visible outbound, a product-approved terminal
no-visible result, or visible waiting text for an async continuation. That close
is atomic with advancing `conversation.last_closed_inbound_seq` to the turn's
`input_to_seq`.

This is the correct design for the current architecture because Coke owns the
conversation orchestration contract and Agno owns the agent loop/tool execution
inside that contract. Interruption and coalescing are not Agno memory features;
they are Coke runtime semantics that must be expressed before and around the
Agno invocation.

## 3. Product Contract

### 3.1 Pre-Reply Interruption

If inbound `N + 1` arrives while a turn covering inbound `N` has not yet
persisted a user-visible outbound, the active turn must be interrupted.

The interruption applies regardless of the active turn phase:

- pre-LLM gate
- semantic interpreter
- focus/reference/context assembly
- Agno model invocation
- Agno tool execution
- output validation
- reply persistence, until the close transaction wins

The older inbound remains part of the next attempt. The replacement turn sees
the ordered message window, not only the newest message.

### 3.2 Window Close

The first durable close decision closes the input window. This includes:

- `replied`
- intentional `no_reply` only when it is a product-approved terminal no-visible
  outcome for the current window
- `pending_async_reply` when it persists runtime-owned waiting text or any other
  visible placeholder

After the close transaction commits, later inbound messages start the next input
window. Delivery of the already-persisted outbound must not be cancelled merely
because a later inbound arrives after the close.

If product later decides that waiting text should not close a window, that must
be a separate product change. This spec treats the first durable close decision
as the stable boundary because it is persisted, observable, and recoverable.

`pending_async_reply` closes the input window but does not make the whole async
job terminal. The later async result remains bound to the already-closed window.
It must not absorb later inbound messages, and it must not bypass delivery
ordering or freshness rules for async continuations.

### 3.3 Prompt Semantics

The agent's current input block is the authoritative source for the open window.
It must contain every inbound message in `[input_from_seq, input_to_seq]` in
sequence order.

The block must make clear that these messages are adjacent user input in one
conversation. The latest message may refine, correct, or complete an earlier
message. The agent should answer the combined intent, not independently answer
each message unless the content requires that.

Agno session history may remain enabled, but it must not be the source of truth
for the current input window. Coke must construct the current input explicitly.

## 4. Agno Alignment

The target architecture intentionally keeps the deep Agno binding:

- Agno remains the agent runtime substrate.
- Agno owns model invocation, structured output, tool execution, and run traces.
- Coke owns trust framing, semantic interpretation, focus/reference context,
  input-window boundaries, freshness, idempotency, delivery, and recovery.

The current implementation uses synchronous `Agent.run(...)` through
`InteractionAgent.invoke(...)`. That is incompatible with quick interruption.

The target implementation must introduce an async interaction path built on
`Agent.arun(...)`, with deterministic Agno `run_id` derived from the Coke
`turn_id` or `turn_id:attempt`.

Agno 2.5.9 exposes `Agent.cancel_run(...)` / `Agent.acancel_run(...)`, and its
OpenAI-compatible async model path uses an async HTTP client with timeout
support. However, Agno cancellation is cooperative. The runtime checks
cancellation before and after model calls, but an in-flight provider HTTP call
may not be interrupted quickly by `acancel_run(...)` alone.

Therefore the Coke runtime must use all of these controls together:

- record durable interruption intent in ConversationRuntime
- call `Agent.acancel_run(run_id)` for Agno-local cooperative cancellation
- cancel the asyncio task awaiting `Agent.arun(...)`
- configure provider/model timeouts for the interaction model
- retain freshness checks at every state-changing boundary

`Agent.acancel_run(...)` is a local execution aid, not the durable source of
truth. Coke's durable input-window and freshness state remains authoritative,
especially across worker restarts.

The implementation must prove provider cancellation behavior. If the underlying
OpenAI-compatible provider cannot abort an in-flight request when the asyncio
task is cancelled, the runtime must still bound the wait with a configured
interaction timeout. That timeout fallback is a degraded safety bound, not full
success for the quick-interrupt requirement.

## 5. Data Model

### 5.1 Conversation

Add:

- `last_closed_inbound_seq bigint not null default 0`

Keep:

- `latest_inbound_seq bigint not null`

Invariant:

```text
0 <= last_closed_inbound_seq <= latest_inbound_seq
```

Open inbound exists when:

```text
latest_inbound_seq > last_closed_inbound_seq
```

### 5.2 Turn

Replace the single-version turn input marker with an explicit window:

- `input_from_seq bigint null`
- `input_to_seq bigint null`
- `superseded_by_inbound_seq bigint null`

For interactive turns:

```text
input_from_seq <= input_to_seq
input_from_seq == conversation.last_closed_inbound_seq + 1 at claim time
input_to_seq == conversation.latest_inbound_seq at claim time
```

`based_on_inbound_seq` is retired as the product contract. During migration,
implementation may temporarily map it to `input_to_seq`, but new code and docs
must speak in window terms.

Active turn membership must not be inferred from `message.turn_id`. Inbound
messages belong to a turn by sequence interval. Outbound messages may continue to
store the producing `turn_id`.

### 5.3 Durable Interruption

ConversationRuntime needs a durable way to express that an open turn is no
longer allowed to close the current window. The minimal contract is:

- when a newer inbound is recorded before the window closes, any active turn with
  `input_to_seq < conversation.latest_inbound_seq` is stale
- stale turns may be marked `superseded` with `superseded_by_inbound_seq`
- the replacement turn must claim from the unchanged `last_closed_inbound_seq + 1`

An implementation may add explicit turn execution state if useful, but the
product semantics are the sequence boundaries and close transaction.

## 6. Runtime Flow

### 6.1 Ingress

Inbound recording must be independent of active turn execution.

The webhook/API path must durably persist the inbound message, advance
`conversation.latest_inbound_seq`, and enqueue/signal work without waiting for
the active turn to complete.

If ingress is routed through the same synchronous worker that is blocked inside
the active Agno call, interruption cannot work. The separation between ingress
recording and turn execution is a hard requirement.

### 6.2 Claim

When interactive work is scheduled for a conversation:

1. Load the conversation under the appropriate transactional lock.
2. If `latest_inbound_seq <= last_closed_inbound_seq`, there is no open input.
3. Create a turn with:
   - `input_from_seq = last_closed_inbound_seq + 1`
   - `input_to_seq = latest_inbound_seq`
4. Read the inbound messages in that inclusive interval.
5. Start the turn execution task.

Only one open interactive turn should attempt to close a conversation window at a
time. Redelivery and duplicate worker events are resolved by the same claim and
close invariants.

### 6.3 New Inbound During Active Execution

When ingress records a newer inbound for a conversation with an active
pre-close turn:

1. The inbound is persisted immediately and `latest_inbound_seq` advances.
2. The runtime signals the active turn supervisor.
3. The active turn records interruption intent and requests Agno cancellation.
4. The active Agno await task is cancelled.
5. The active turn exits as `superseded` without persisting a user-visible
   outbound.
6. A replacement turn is scheduled from `last_closed_inbound_seq + 1` through the
   new `latest_inbound_seq`.

If the old provider call returns despite cancellation, freshness and close
guards must still reject its state changes and outbound close.

### 6.4 Close

Reply persistence, no-reply terminalization, pending-async visible waiting text,
and materialization of staged interactive commands must all close through one
compare-and-set style operation:

```text
where conversation.last_closed_inbound_seq == turn.input_from_seq - 1
  and conversation.latest_inbound_seq == turn.input_to_seq
```

On success:

```text
staged commands for the turn are materialized idempotently
conversation.last_closed_inbound_seq = turn.input_to_seq
turn disposition = replied | no_reply | pending_async_reply
outbound persisted with producing turn_id
```

On failure, the turn is stale. It must not persist a visible outbound. If a newer
inbound caused the failure, the turn becomes `superseded`.

If staged command materialization fails, the runtime must not persist a success
reply that claims the command was completed. The close should either persist a
truthful failure/clarification result or fail as a retryable runtime error,
depending on the domain error.

### 6.5 Delivery and Pub/Sub

The close boundary is close-result persistence, not adapter delivery. After a
visible outbound is persisted, channel delivery should proceed under normal
outbound idempotency rules.

For synchronous waiters, the visible reply for a coalesced window should be
published against the latest causal inbound event in that window. Older request
waiters in the same window should receive an explicit coalesced/superseded
terminal signal or be otherwise completed so they do not hang.

## 7. State Changes and Tool Calls

Pre-reply interruption creates a duplicate-attempt shape: the replacement turn
may re-evaluate earlier messages that were also visible to the superseded turn.

The runtime must not rely on rollback. The legacy rollback style is not the
clean architecture.

For interactive turns, state-changing tools must use a staged command contract.
Before the input window closes, they may validate intent, read state, reserve a
turn-local draft, and return a structured preview to the agent. They must not
activate user-visible domain facts, enqueue product notifications, or trigger
external adapter effects.

The close transaction is the first point where staged interactive commands may
become real domain facts.

Required contract:

- every state-changing tool entry must check turn freshness before mutation
- every pre-close interactive mutation must be a staged command owned by the
  turn, not an active product fact
- every staged command must have an idempotency key tied to the input window and
  command identity
- every close transaction must re-check freshness before materializing staged
  commands
- superseded turns must leave no active product facts behind; their staged
  commands are discarded or marked `superseded`

Command idempotency keys should be derived from stable product intent, not from
raw LLM prose. Acceptable key components include:

```text
conversation_id
input_from_seq
input_to_seq
normalized command type
normalized target/entity identity when known
command item index within the validated output/tool batch
```

This prevents double materialization during close retries and duplicate worker
delivery for the same window.

Domains may introduce invisible durable draft rows if needed, but those rows must
not be effective, user-visible, or externally delivered until the fresh close
transaction materializes them.

This stronger staging contract is required for the user-correction case. If the
user says "remind me at 9" and then sends "actually 10" before receiving the
agent reply, the superseded first attempt must not leave an active 9 o'clock
reminder behind.

## 8. Worker and Recovery

The worker cannot remain a single synchronous `xreadgroup count=1 -> run turn ->
ack` loop for interactive inbound work if that loop prevents newer inbound
events from being observed.

The target worker shape is:

- ingress writes are fast and independent
- interactive execution is supervised per conversation
- the supervisor keeps an in-process task registry only as an optimization
- durable conversation state determines recovery after crash/restart
- on restart, any open input window is reconstructed from:

```text
conversation.last_closed_inbound_seq + 1
through
conversation.latest_inbound_seq
```

The task registry may map `conversation_id -> active turn task/run_id`, but that
registry must never be the only source of correctness.

## 9. Non-Goals

This spec does not introduce:

- rollback or compensation for already committed durable facts
- reuse of partial LLM output from superseded turns
- cross-conversation message merging
- keyword-based correction detection
- a hidden legacy-style pending-message queue outside the conversation sequence
- delivery cancellation after close-result persistence
- treating Agno session history as the current-input authority
- `Agent.acancel_run(...)` as the only interruption mechanism
- active user-visible domain mutations before the fresh close boundary

## 10. Required Verification

### 10.1 ConversationRuntime

Tests must prove:

- inbound recording advances `latest_inbound_seq` without advancing
  `last_closed_inbound_seq`
- a turn claims `[last_closed + 1, latest]`
- a newer inbound before close makes the older turn stale
- a superseded turn does not advance `last_closed_inbound_seq`
- a successful close atomically persists the close result and advances
  `last_closed_inbound_seq`
- duplicate/redelivered inbound work does not create a second close for the same
  window

### 10.2 Turn Runner

Tests must prove:

- two quick user messages are rendered in one current input block
- a newer inbound during pre-agent context assembly cancels/replaces the active
  turn
- a newer inbound during Agno execution cancels/replaces the active turn
- if the old Agno call returns after cancellation, its output is rejected
- a newer inbound after close persistence starts the next window instead of
  cancelling delivery
- output is published to the latest causal inbound event in a coalesced window
  and older waiters complete

### 10.3 Agno Cancellation

Tests must prove:

- Coke uses `Agent.arun(...)` for interruptible interactive execution
- the deterministic Agno `run_id` is linked to the Coke `turn_id`
- `Agent.acancel_run(run_id)` is called when a pre-close newer inbound arrives
- the asyncio task awaiting `Agent.arun(...)` is cancelled
- provider timeout is configured for the interaction model
- provider cancellation behavior is exercised with a fake or local
  OpenAI-compatible async server

The provider-cancellation test must distinguish these outcomes:

- pass: task cancellation aborts the in-flight HTTP request promptly
- degraded: the provider call is only bounded by configured timeout
- fail: the provider call can block beyond the interrupt/timeout contract

### 10.4 Tools and Domain Mutations

Tests must prove:

- state-changing interactive tools create staged commands, not active product
  facts, before close
- stale turns reject staged-command creation and close materialization
- superseded staged commands do not become active reminders, shared-reminder
  proposals, notifications, or adapter sends
- close retries use the same command idempotency key for the same product command
- reminders and shared-reminder proposals are materialized exactly once for the
  winning fresh window
- a correction sequence such as "remind me at 9" then "actually 10" creates only
  the coalesced final command

### 10.5 End-to-End Smoke

Use a deliberately slow interaction agent or provider stub:

1. Send message A.
2. While A is still in the agent call, send message B in the same conversation.
3. Assert A's active turn is cancelled/superseded quickly.
4. Assert the replacement prompt contains A then B.
5. Assert one visible reply is delivered for the coalesced window.
6. Assert the total user wait is bounded by the interrupt supervisor and not by
   waiting for A's full old model call plus B's full model call.

## 11. Rollout Plan

1. Add the input-window schema and ConversationRuntime close/claim API.
2. Change prompt construction to render an ordered current input window.
3. Introduce async Agno invocation for interactive turns with deterministic
   `run_id`, task cancellation, and provider timeout configuration.
4. Replace synchronous worker blocking with a per-conversation interrupt
   supervisor and durable recovery.
5. Convert interactive state-changing tools to staged command contracts.
6. Add freshness/idempotency enforcement at staged command materialization.
7. Add delivery/pub-sub completion for coalesced older waiters.
8. Run unit, integration, and slow-agent smoke verification before production.

## 12. Architecture Stance

This is the optimal direction for the current Coke architecture.

It keeps Agno where the target architecture says Agno belongs: inside the agent
execution substrate. It does not push Coke's conversation semantics into Agno
session history, and it does not reintroduce legacy rollback behavior.

The hard architectural boundary is:

```text
Coke decides what input window is current and whether the turn is still fresh.
Agno decides how to execute the agent for that window.
```

The only unresolved implementation risk is provider-level cancellation
propagation. The spec makes that risk explicit and testable. If cancellation
does not propagate through the OpenAI-compatible provider client, the runtime can
still bound the failure with interaction timeouts, but the target requirement
remains fast event-driven interruption.
