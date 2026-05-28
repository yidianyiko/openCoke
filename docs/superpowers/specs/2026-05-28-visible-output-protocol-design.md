---
status: active
created_at: 2026-05-28
updated_at: 2026-05-29
owner: worker-runtime
kind: design
---

# Visible Output Protocol Design

## Decision

The Interaction Agent is the only producer of final assistant prose in chat
channels. The worker runtime accepts only a structured `MultiModalResponses`
envelope as successful model output. The only user-visible field is
`MultiModalResponses[*].content`, normalized into `VisibleMessage.content`.

Runtime validation is single-pass. If the Interaction Agent returns malformed
JSON, an invalid envelope, empty output, internal protocol labels, blocked
durable-write claims, identifier leaks, or any other current output-contract
violation, the turn produces no visible chat message and records a structured
error disposition. The runtime must not ask the model to rewrite the answer.

Domain and capability results are trusted facts for grounding, traces, metrics,
tests, and eval evidence. They are not alternate producers of final assistant
prose. The worker must not replace model text with domain summaries,
capability summaries, reminder titles, direct templates, or fixed operational
fallback text.

## Scope

This design covers the worker-runtime output path:

- `user.turn` interaction responses
- `reminder.fired` typed runtime events
- interaction model output parsing
- `VisibleMessage` construction
- ordinary user-turn sending through `agent_handler`
- proactive reminder sending through `ReminderFireEventHandler`

It does not change Gateway product notifications, bridge outbound dispatch, or
provider-specific delivery behavior except through the output messages they
receive from the worker runtime.

## Runtime Flow

```text
AgentInput
  -> Interaction Agent
  -> parse MultiModalResponses once
  -> validate current output contract once
  -> VisibleMessage[] when valid
  -> empty output + structured error when invalid
```

Invalid output is a runtime failure state, not a prompt-repair workflow:

- no protocol-repair prompt
- no second interaction-agent attempt
- no response-only rewrite pass
- no domain-summary replacement
- no capability-summary replacement
- no template fallback prose

## Sending Contract

Sending layers consume `VisibleMessage` values only. If the runtime returns
`output_disposition.status == "empty"`, `agent_handler` records that state and
sends nothing. It must not call a timeout or empty-output fallback helper.

Reminder fire handling follows the same rule. A fired reminder without valid
Interaction Agent output is `OutputUnavailable`; it must not send a direct
template such as `提醒：{title}`.

## Testing

Tests should prove:

- valid `MultiModalResponses` produces ordered `VisibleMessage.content`
  entries
- malformed JSON or invalid envelope fails closed
- raw plain text fails closed
- empty model output fails closed
- blocked write claims fail closed
- domain and capability summaries do not replace valid model prose
- handler empty-output paths send no fallback chat message

Tests must not assert protocol-repair prompts, retry success after malformed
output, second-pass visible-content rewrites, domain-summary replacement, or
fixed fallback prose.
