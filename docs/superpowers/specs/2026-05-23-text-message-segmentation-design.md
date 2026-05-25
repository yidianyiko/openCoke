# Text Message Segmentation Design

## Goal

Restore the legacy human-like multi-message reply experience for text replies
in the current single-Agent runtime.

When the assistant has a natural reason to send more than one short message,
the runtime should emit multiple `VisibleMessage(message_type="text", ...)`
items and let the existing output delivery layer write them as separate
`outputmessages` with staggered `expect_output_timestamp` values.

The first version restores only `type="text"` segmentation. It does not let the
model choose voice or photo outputs.

## Current Facts

- Legacy `coke-legacy-server` used `StreamingChatWorkflow` to parse
  `MultiModalResponses` and send each item as it appeared.
- Current `coke` no longer runs that workflow. `run_agent_runtime()` currently
  treats `run_output.content` as one final visible text and wraps it in one
  `VisibleMessage`.
- `agent/runner/agent_handler.py` already iterates over
  `result.visible_messages`.
- `agent/runner/output_delivery.py` already sends one visible message at a time
  and increments `expect_output_timestamp` for later text messages based on
  message length.
- Some legacy `MultiModalResponses` prompt/schema files still exist, but they
  are not the active production output contract.

## Required Changes

### `agent/agno_agent/runtime/chat_response_instructions.py`

Add an explicit structured visible-output contract for the Interaction Agent:

- Output a JSON object with `MultiModalResponses`.
- Every item must be `{ "type": "text", "content": string }`.
- Use 1 to 3 items for ordinary segmented replies.
- Prefer one item for concise confirmations, tool result summaries, URLs,
  dense instructions, and replies where splitting would reduce clarity.
- Do not emit voice or photo items in this version.
- Do not include reasoning, prompt commentary, tool logs, or non-user-visible
  fields in the final output.

The segmentation wording should preserve the legacy intent: short casual turns
may be short, complex answers may be longer, and segmented messages should feel
natural rather than mechanically equal-sized.

### `agent/agno_agent/runtime/agent_runtime.py`

Replace the direct `final_text -> one VisibleMessage` conversion with a parser
that converts model output into text `VisibleMessage` items.

Behavior:

- Parse valid JSON containing `MultiModalResponses`.
- Keep only valid text items with non-empty `content`.
- Reject or ignore non-text item types for this version.
- Cap visible text segments at 3.
- If parsing fails, fall back to one text `VisibleMessage` containing the
  stripped final text.
- Preserve the existing durable-write and unconfirmed-promise failure behavior:
  when a runtime contract error suppresses output today, it must still suppress
  segmented output.
- Run user-visible text guardrails against the parsed visible text, not only
  the raw JSON envelope. For guardrails that currently accept `final_text`,
  use the joined text segment contents as the semantic text under review.
- Preserve visible-summary fallback behavior for capability results. If the
  runtime uses capability summaries because model text is empty, those summaries
  should remain one visible text message unless a later implementation
  explicitly adds deterministic segmentation for summaries.

### Removed structured-output schema

`agent/agno_agent/schemas/chat_response_schema.py` has been removed because it
was not an active runtime contract. The current Interaction Agent construction
does not pass an Agno `output_schema`.

Keep the first version enforced through `chat_response_instructions.py` plus the
runtime parser helper. If a future implementation introduces an active
structured-output contract, add a new schema at that point instead of reviving
the historical file.

If the schema becomes active:

- `MultiModalResponses` remains the conceptual response list.
- The first implementation only accepts `type="text"` for production visible
  output, even if the historical schema still mentions voice/photo.
- Any schema cleanup should avoid reintroducing the retired streaming workflow.

### `tests/unit/agent/`

Add focused unit coverage for:

- valid JSON with two text segments becomes two `VisibleMessage` values
  in order.
- malformed JSON falls back to one text message instead of exposing parser
  errors.
- non-text items are ignored or rejected according to the implementation
  helper contract.
- more than three text segments are capped.
- durable-write contract errors still return no visible messages.
- `agent_handler` sends multiple visible messages by repeatedly calling
  `_send_single_message` with increasing `expect_output_timestamp`.
- `test_chat_response_instructions.py` accepts the new active text-only JSON
  contract while still rejecting retired legacy wording such as JSON Schema,
  unrestricted message types, and structured multi-modal output claims.

## ClawScale Decision

Do not change the ClawScale protocol in this first version.

The worker/runtime change is enough for async push paths:

- Proactive/reminder push output writes multiple pending `outputmessages`.
- `connector/clawscale_bridge/output_dispatcher.py` already claims one pending
  push message at a time when `expect_output_timestamp <= now`.
- Each pushed segment can therefore be delivered separately with the existing
  delayed timestamp behavior.

Keep synchronous `request_response` behavior as a single reply string:

- `agent/util/message_util.py` currently merges extra sync reply output into
  the first pending sync reply.
- `connector/clawscale_bridge/reply_waiter.py` can also join multiple pending
  sync replies into one `reply` string.
- Gateway/provider immediate reply paths consume one reply string, not a
  first-class list of reply segments.

Changing synchronous ClawScale to real multi-message delivery would require a
separate gateway/channel contract, such as a `replies[]` payload or async
follow-up dispatch. That is out of scope for this design.

## Non-Goals

- Do not revive `StreamingChatWorkflow`.
- Do not add regex streaming JSON parsing.
- Do not enable model-selected voice or photo outputs.
- Do not change gateway outbound API shape.
- Do not change provider webhook immediate reply contracts.
- Do not split capability visible summaries unless a later requirement asks
  for deterministic summary segmentation.

## Verification

Recommended verification after implementation:

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -v`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py -v`
- `.venv/bin/python -m pytest tests/unit/runner/test_agent_handler_inflight_interrupt.py -v`
- `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py -v`
- `.venv/bin/python -m pytest tests/unit/agent/test_message_util_clawscale_routing.py -v`
- `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_reply_waiter.py -v`
- `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_output_dispatcher.py -v`
- A real-model smoke or eval case that verifies the Interaction Agent can
  return parseable text-only `MultiModalResponses` for a normal conversational
  reply.
- `zsh scripts/suggest-verification --base HEAD~1`
- `zsh scripts/review-trigger --base HEAD~1`

`test_message_util_clawscale_routing.py` and `test_reply_waiter.py` prove the
deliberate ClawScale sync behavior remains unchanged. `test_output_dispatcher.py`
proves the async push path still dispatches separate pending output documents
according to their staggered `expect_output_timestamp` values.
