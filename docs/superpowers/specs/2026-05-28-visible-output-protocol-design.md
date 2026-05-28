---
status: active
created_at: 2026-05-28
owner: worker-runtime
kind: design
---

# Visible Output Protocol Design

## Decision

The interaction LLM must be the only producer of user-visible assistant text.
Both ordinary user turns and fired reminder events flow through the same
interaction runtime before any output is sent to the user.

The runtime accepts only the structured `MultiModalResponses` envelope as a
successful LLM output protocol. The only user-visible field is
`MultiModalResponses[*].content`, normalized into `VisibleMessage.content`.
Sending layers must consume `VisibleMessage` values only; they must not send
raw reminder titles, raw prompts, tool-call protocol text, or whole model
outputs directly.

If the interaction LLM does not return a parseable `MultiModalResponses`
envelope, the runtime treats that output as a protocol violation. For
`reminder.fired`, the runtime retries the same interaction LLM once with an
explicit protocol-repair instruction because reminder fires expose no tools. For
`user.turn`, the runtime may retry only when the first attempt did not execute a
durable write. If a user-turn attempt already executed a durable write, the
current implementation must fail closed until a response-only repair pass exists
that can reuse trusted domain results without re-exposing write tools. If the
retry also violates the output protocol, the turn produces no user-visible
message and records a protocol violation.

Once valid `MultiModalResponses[*].content` values have been produced, the
runtime does not reject them because their text resembles JSON, tool-call
markup, or another internal-looking string. Stability of visible wording is a
prompt, eval, and smoke-testing responsibility; structure compliance is a
runtime contract.

## Scope

This design covers the worker-runtime output path:

- `user.turn` interaction responses
- `reminder.fired` typed runtime events
- interaction LLM prompt/output protocol
- `VisibleMessage` construction
- ordinary user-turn sending through `agent_handler`
- proactive reminder sending through `ReminderFireEventHandler`

It does not change Gateway product notifications, bridge outbound dispatch, or
provider-specific delivery behavior except through the output messages they
receive from the worker runtime.

## Current Problem

The runtime already has a dedicated user-visible output field:
`VisibleMessage.content`. The intended path is:

```text
interaction LLM
  -> MultiModalResponses[*].content
  -> VisibleMessage.content
  -> send layer
```

The unsafe ambiguity is that malformed or non-envelope model output can be
treated as visible text, and the current runtime has lenient envelope recovery
for malformed JSON. Both behaviors make it hard to distinguish a valid
user-visible message from an LLM output-protocol failure.

The previous serialized-tool-call guard addressed one symptom by blocking
visible text that looked like tool-call markup. That is the wrong long-term
contract. The runtime should enforce the structural output protocol before
constructing `VisibleMessage`, then trust the content field that the protocol
defines as user-visible.

## Data Flow

```mermaid
flowchart TD
  A[Input event] --> B{input_type}
  B -->|user.turn| C[agent_handler]
  B -->|reminder.fired| D[ReminderFireEventHandler]

  C --> E[run_agent_runtime]
  D --> E

  E --> F[CokeInteractionAgent]
  F --> G[interaction LLM]

  G --> H{parseable MultiModalResponses?}
  H -->|yes| I[MultiModalResponses[*].content]
  I --> J[VisibleMessage.content]
  J --> K{sender}
  K -->|user.turn| L[output_delivery.send_single_message]
  K -->|reminder.fired| M[output_writer / send_message_via_context]
  L --> N[outputmessages and delivery]
  M --> N

  H -->|no| O[retry when safe]
  O --> P{parseable MultiModalResponses?}
  P -->|yes| I
  P -->|no| Q[no user-visible output]
  Q --> R[record output_protocol_violation]
```

## Input-Type Rules

### `user.turn`

User turns use the normal interaction LLM and may expose the active domain and
utility tools. Tool results may inform the final answer, but the final user
message still must come back through `MultiModalResponses[*].content`.

### `reminder.fired`

Fired reminders use the same interaction LLM and the same visible-output
protocol, but expose no tools. The model receives the reminder fire payload and
must render a user-visible reminder message through `MultiModalResponses`.

Reminder output must not be sent through a direct template fallback such as
`提醒：{title}` when the typed runtime is available. Direct template fallback is
only acceptable as an explicitly separate degraded mode for environments that
do not wire the typed runtime, and follow-up reminders must continue to fail
closed without the typed runtime.

## Output Protocol

Successful LLM output is a JSON object with this shape:

```json
{
  "MultiModalResponses": [
    {"type": "text", "content": "message text"}
  ]
}
```

Runtime rules:

- Parse only `MultiModalResponses` envelopes as successful structured output.
- Preserve the current text-only message type for this feature.
- Convert each non-empty text `content` value into a `VisibleMessage`.
- Preserve ordered multi-message output from the envelope.
- Enforce the configured maximum visible segment count.
- Treat raw plain text, arbitrary JSON, malformed envelope JSON, empty output,
  or an envelope with no usable text content as an output protocol violation.
- Retry one time on protocol violation.
- Do not send anything if both attempts violate the protocol.

Content rules:

- Do not block a valid `VisibleMessage.content` because it resembles JSON,
  tool-call markup, or another internal-looking string.
- Keep durable-write and domain-result safety checks for user turns where they
  protect real side effects.
- Keep identifier-leak checks only if they protect non-negotiable privacy or
  security boundaries. Do not use them as a replacement for the output
  protocol.

## Retry Semantics

The retry is a protocol-repair attempt, not a deterministic fallback.

Requirements:

- Use the same interaction LLM role.
- Preserve the original `AgentInput`, `AgentRunContext`, session, and input
  type.
- Preserve tool exposure rules for reminder fires: they still have no tools.
- For user turns, preserve the logical interaction context but do not replay
  durable write tools that already executed.
- Add a concise repair instruction that says the previous response violated
  the output protocol and the retry must return only the
  `MultiModalResponses` JSON object.
- Do not execute domain tools a second time if the first attempt already
  executed durable writes. Implementation must either avoid replaying writes or
  split protocol repair from domain execution before enabling retry for
  post-write user turns.

Because user turns can include tools and durable writes, implementation should
handle retry carefully:

- If no tools or durable writes ran, a full interaction retry is acceptable.
- If domain tools ran but no durable write ran, a full interaction retry is
  acceptable, with the same tool exposure rules.
- If domain tools or capability tools performed a durable write, do not run a
  full interaction retry. Prefer a response-only repair pass that receives
  trusted domain/capability results and exposes no write tools.
- If a safe response-only repair pass is not available, fail closed instead of
  replaying a write.

Reminder fires are simpler because they expose no tools and can safely retry
the same interaction generation once.

## Error Handling

When both attempts fail the output protocol, the runtime returns:

- no `VisibleMessage`
- `OutputDisposition(status="empty")`
- `RuntimeErrorDisposition(code="output_protocol_violation")`
- trace metadata indicating whether this was the first attempt or retry
  failure

For `reminder.fired`, `ReminderFireEventHandler` must treat that as
`OutputUnavailable` and must not send a fallback template through the normal
typed-runtime path.

For `user.turn`, existing user-turn fallback behavior should be reviewed during
implementation. If the fallback bypasses the interaction LLM visible-output
protocol, it must be removed or rewritten to use a valid `VisibleMessage`
contract before this design is complete.

Existing runtime guardrail responses that intentionally do not call the
interaction LLM, such as pre-run safety rejections, are out of scope for the
first implementation. They must remain visible as explicit runtime outputs and
should be covered by a separate design if the product requires the interaction
LLM to rephrase them.

## Prompt Contract

`build_chat_response_instructions` should explicitly state:

- The only successful final output is the `MultiModalResponses` JSON object.
- `MultiModalResponses[*].content` is the user-visible text field.
- The model must not output raw text outside the object.
- For `reminder.fired`, the model is rendering an existing reminder, not
  creating, listing, updating, or cancelling reminders.
- For `reminder.fired`, no tools are available and the model must still produce
  the visible reminder message through the structured envelope.

Prompt tuning is responsible for keeping the content natural and stable.
Runtime parsing is responsible for rejecting structural violations.

## Testing

Unit tests should cover:

- valid `MultiModalResponses` produces ordered `VisibleMessage.content`
  entries
- raw plain text triggers exactly one retry
- retry success sends only the retry envelope content
- retry failure sends no visible message and records
  `output_protocol_violation`
- `reminder.fired` uses the interaction LLM with no tools
- `reminder.fired` never sends a direct title/prompt template when typed
  runtime is wired
- valid envelope content that looks like tool-call markup is still surfaced as
  `VisibleMessage.content`
- user turns with durable writes do not replay write tools during protocol
  repair

Integration or smoke evidence should cover:

- a normal user turn response
- a fired visible reminder response
- a fired internal follow-up response
- a multi-segment response arriving as multiple ordered output messages

Production verification must check both `outputmessages` and downstream
delivery evidence, because an output document alone does not prove the user
received the message.

## Non-Goals

- Do not add a deterministic reminder template fallback to satisfy this
  contract.
- Do not expose tools to `reminder.fired`.
- Do not send raw model output as a successful result.
- Do not preserve the serialized-tool-call content guard as a primary safety
  mechanism for valid `VisibleMessage.content`.
- Do not broaden this design into Gateway notification formatting.
