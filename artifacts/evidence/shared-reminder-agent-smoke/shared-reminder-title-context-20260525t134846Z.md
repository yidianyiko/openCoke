# Shared Reminder Title and Product Notification Context Fix

Created: 2026-05-25 13:48:46 UTC

## Scope

- Shared-reminder creation title policy must use the current requested shared
  item instead of product defaults or stale conversation topics.
- Bridge inbound normalization must preserve trusted
  `metadata.product_notification` so short invitee replies can be handled as
  shared-reminder accept/reject actions.

## Verification

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_agent_runtime_construction.py -q -k 'snake_case_product_notification or chat_response_scheduling_instructions or uses_friend_link_worker_prompt or product_notification_context_turns_short_confirmation_into_shared_reminder_accept or normalizes_start_datetime_alias'`
  - Result: 19 passed, 127 deselected.
- `zsh scripts/suggest-verification --base HEAD~1`
  - Suggested surfaces: `worker-runtime bridge`.
- `zsh scripts/verify-surface worker-runtime bridge`
  - Result: passed.
  - Included `tests/unit/runner/`, `tests/unit/agent/`,
    `tests/unit/test_clawscale_only_topology.py`,
    `tests/unit/connector/clawscale_bridge/`, and
    `tests/unit/agent/test_message_util_clawscale_routing.py`.

## Review Gate

- `zsh scripts/review-trigger --base HEAD~1` reported
  `human_review_required: yes` for cross-boundary worker/bridge changes.
