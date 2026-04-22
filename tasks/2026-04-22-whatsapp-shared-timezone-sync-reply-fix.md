# Task: WhatsApp Shared Timezone And Sync Reply Fix

- Status: Completed
- Owner: Codex
- Date: 2026-04-22

## Goal

Fix the two user-visible bugs found in the live `whatsapp_evolution` E2E run on
`gcp-coke`:

- shared-channel synthetic users must persist timezone updates
- request/response replies must not drop extra same-turn text segments

## Scope

- In scope:
  - fix `UserDAO` settings updates so shared business accounts can persist
    timezone changes even when `coke_settings` does not exist yet
  - fix sync reply handling so multiple text outputs in one turn are delivered
    as one request/response reply instead of failing after the first segment
  - add focused regression tests for both behaviors
  - redeploy and rerun the two production WhatsApp scenarios
- Out of scope:
  - web UI changes
  - unrelated prompt tuning
  - broader channel routing redesign

## Touched Surfaces

- worker-runtime
- bridge
- repo-os

## Linked Docs

- Spec:
  - `docs/superpowers/specs/2026-04-22-whatsapp-shared-timezone-sync-reply-design.md`
- Exec plan:
  - `docs/exec-plans/2026-04-22-whatsapp-shared-timezone-sync-reply-fix.md`

## Acceptance Criteria

- A shared WhatsApp synthetic account with no existing `coke_settings` document
  can persist a timezone update.
- A request/response turn that emits multiple text outputs no longer leaves
  extra outputs failed with
  `failure_reason=unexpected_extra_request_response_output`.
- The bridge returns one reply string that includes all same-turn text output
  segments in order.
- Focused regression tests cover both bugs.
- The production E2E scenario reproduces the expected fixed behavior on
  `gcp-coke`.

## Verification

- `pytest tests/unit/test_user_dao_timezone.py tests/unit/agent/test_message_util_clawscale_routing.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py -v`
- production WhatsApp webhook E2E replay on `gcp-coke`

## Notes

- Root cause evidence is recorded in
  `tasks/2026-04-22-whatsapp-e2e-live-testing.md`.
- Production verification on `gcp-coke` after redeploy:
  - isolated WhatsApp `你好` scenario on external id `120260422074231` produced
    exactly one handled Mongo output for the causal event, with no extra
    `pending` tail
  - isolated WhatsApp timezone scenario on external id `120260422074232`
    persisted `coke_settings.timezone=America/New_York`
  - Postgres message history for both test users includes the assistant reply
    generated after the live webhook request
- Focused unit verification passed:
  - `pytest tests/unit/agent/test_agent_handler.py tests/unit/test_user_dao_timezone.py tests/unit/agent/test_message_util_clawscale_routing.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py tests/unit/test_timezone_tools.py -v`
- Full bridge suite still has one unrelated failure in the already-dirty
  `tests/unit/connector/clawscale_bridge/test_verify_auth_retirement.py`.
