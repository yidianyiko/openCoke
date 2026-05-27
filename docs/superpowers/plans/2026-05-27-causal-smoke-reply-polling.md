# 2026-05-27 Causal Smoke Reply Polling Cleanup

status: completed

## Goal

Remove the smoke-helper fallback that treated any recent output to the same
account as a reply to the current bridge request. The resolved batch-mixing
incident means a missing `causal_inbound_event_id` match should fail the smoke
path instead of borrowing an unrelated row.

## Surfaces

- `repo-os`: verification helper semantics
- `bridge`: request/response smoke evidence

## Changes

1. Empty synchronous bridge replies are now polled only by
   `metadata.business_protocol.causal_inbound_event_id`.
2. Recipient plus timestamp polling was removed.
3. Unit tests now cover both a matching causal reply and a missing causal reply.

## Non-goals

- Do not change production runtime behavior.
- Do not change late push polling, which is handled separately by
  `poll_late_reply_text`.
