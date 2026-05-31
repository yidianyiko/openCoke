---
kind: incident
status: open
surface: conversation-runtime, agent-runtime, notification-delivery
created_at: 2026-06-01
updated_at: 2026-06-01
---

# Confirmation Turn No Reaction After Shared-Reminder Clarification

## What Happened

In production conversation `7fed5c7c-08f9-4778-bdcc-c14b7f2cf346`, account
`olivers` sent two questions, then asked:

- `帮我和他约一个明天上午八点半的晨跑活动吧`

The requester only received:

- `你是想约 lizihao 一起晨跑吗？`

When the user later replied `是的`, the turn did not create a shared reminder
and did not send a final visible reply.

## Why It Matters

This is the core follow-up confirmation path for shared-reminder creation. A
user-visible clarification must remain actionable when the user confirms it.
The failure also hid useful progress messages because waiting replies were
persisted but not delivered.

## Affected Surfaces

- `conversation-runtime`
- `agent-runtime`
- `notification-delivery`

## Evidence

- Production `input_message` rows for the conversation show seq 76 and 77 were
  coalesced question inputs, seq 78 requested the morning run, and seq 79 was
  `是的`.
- Production `turn` rows show the seq 79 turn
  `9d750217-8587-454b-95dd-14dffd670e76` ended with
  `failed / invalid_output_protocol`.
- Production `ai.agno_sessions` for session
  `7fed5c7c08f94778bdccc14b7f2cf346` shows the last run content was literal
  `<tool_call>social_scheduling_tool({...})</arg_value>`, not a native tool
  invocation or Coke JSON output.
- The same turn's trusted semantic decision was
  `chit_chat / missing_context / ask_context`, so the runtime exposed a
  clarification-only tool profile and instructed the agent to ask context before
  any domain action.
- Waiting replies for the question and command turns were persisted but their
  delivery attempts failed with `provider_network_error`; those waiting
  delivery requests used raw provider trigger ids as idempotency keys, unlike
  compact final reply keys.

## Current Status

- Open. The incident is under repair with regression tests for waiting-message
  idempotency, short confirmation tool availability, and serialized tool-call
  retry guidance.

## Resolution

- Pending fix commit, deployment SHA, and production smoke evidence.
