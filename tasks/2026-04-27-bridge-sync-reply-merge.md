# Bridge Sync Reply Merge

Date: 2026-04-27

## Problem

ClawScale `request_response` turns could produce multiple text segments, but the
bridge consumed the first pending output immediately. Later segments from the
same `causal_inbound_event_id` were marked as
`unexpected_extra_request_response_output`, so users often saw only the first
part of a response.

## Surfaces

- `bridge`
- `worker-runtime`

## Fix

- Let worker sync replies emit multiple pending text outputs for the same turn.
- Let `ReplyWaiter.wait_for_reply()` drain all pending text outputs for the same
  sync event, order them by `expect_output_timestamp`, merge them with newlines,
  and mark every consumed segment handled.

## Verification

- `pytest tests/unit/connector/clawscale_bridge/test_reply_waiter.py tests/unit/agent/test_message_util_clawscale_routing.py -v`
- `pytest tests/unit/connector/clawscale_bridge/ -v`
- `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/ -v`
- `.venv/bin/python -m pytest tests/unit/agent/test_message_util_clawscale_routing.py -v`
- `zsh scripts/check`

`pytest tests/unit/agent/test_message_util_clawscale_routing.py tests/unit/agent/test_agent_handler.py -v`
was also attempted. The message-util tests passed. The agent-handler tests did
not run cleanly under system Python because `apscheduler` is missing, and under
`.venv/bin/python` because importing `agent.agno_agent.tools.timezone_tools`
raises an existing `TypeError` at `dao: UserDAO | None = None`.
