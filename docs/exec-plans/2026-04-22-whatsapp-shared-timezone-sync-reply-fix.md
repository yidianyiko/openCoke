# 2026-04-22 WhatsApp Shared Timezone And Sync Reply Fix

## Status

- State: Implemented and verified
- Branch: `fix/whatsapp-sync-timezone`
- Worktree: `/data/projects/coke/.worktrees/fix-whatsapp-sync-timezone`

## Goal

Repair the two production regressions exposed by the live WhatsApp E2E test:

- timezone changes for shared synthetic accounts must persist
- request/response turns must return all same-turn text output as one reply
  instead of silently dropping later segments

## Scope

- In scope:
  - settings update semantics in `dao/user_dao.py`
  - request/response text aggregation in `agent/runner/agent_handler.py`
  - sync reply safety handling in `agent/util/message_util.py`
  - bridge-side pending reply consumption in
    `connector/clawscale_bridge/reply_waiter.py`
  - focused regression coverage
- Out of scope:
  - gateway webhook schema changes
  - prompt/content changes
  - web UI or settings pages
  - non-text multipart reply redesign

## Inputs

- Related task:
  - `tasks/2026-04-22-whatsapp-shared-timezone-sync-reply-fix.md`
- Related spec:
  - `docs/superpowers/specs/2026-04-22-whatsapp-shared-timezone-sync-reply-design.md`
- Related references:
  - `tasks/2026-04-22-whatsapp-e2e-live-testing.md`
  - `docs/fitness/coke-verification-matrix.md`
  - `docs/deploy.md`

## Touched Surfaces

- worker-runtime
- bridge
- repo-os

## Execution Plan

### 1. Lock the failures with focused regression tests

- [x] Add a DAO-level test showing timezone persistence succeeds when
  `coke_settings` does not exist before the write.
- [x] Add request/response routing tests showing same-turn text output no
  longer fails as `unexpected_extra_request_response_output`.
- [x] Add bridge waiter coverage for combining pending sync reply outputs tied
  to the same causal inbound event.
- [x] Add agent-handler coverage for the business `request_response` text
  aggregation path.

### 2. Repair timezone persistence for shared synthetic users

- [x] Change settings writes to use `upsert=True` so first-time shared users can
  create `coke_settings` on demand.
- [x] Treat matched-or-upserted writes as success, including same-value writes.
- [x] Keep the document keyed by `account_id` and preserve existing settings
  fields.

### 3. Repair same-turn sync reply delivery

- [x] Normalize business ClawScale `request_response` text output to one
  aggregated message at the worker boundary.
- [x] Keep push-mode behavior unchanged.
- [x] Preserve bridge-side tolerance for already-split same-turn sync text
  outputs.
- [x] Prevent extra same-turn text outputs from remaining failed or pending on
  the live path.

### 4. Verify and roll out

- [x] Run the focused unit suite for the touched runtime and bridge surfaces.
- [x] Redeploy the patched runtime to `gcp-coke`.
- [x] Replay the real WhatsApp `"你好"` scenario and confirm one handled output
  with no extra pending tail.
- [x] Replay the real WhatsApp timezone scenario and confirm
  `coke_settings.timezone=America/New_York`.

## Verification

- Local focused unit suite:
  - `pytest tests/unit/agent/test_agent_handler.py tests/unit/test_user_dao_timezone.py tests/unit/agent/test_message_util_clawscale_routing.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py tests/unit/test_timezone_tools.py -v`
- Expected evidence:
  - regression tests pass
  - no same-turn sync text outputs fail with
    `unexpected_extra_request_response_output`
  - timezone update succeeds even when `coke_settings` does not exist before
    the call
- Production evidence on `gcp-coke`:
  - shared WhatsApp `"你好"` path produces exactly one handled output for the
    causal event
  - shared WhatsApp timezone path persists
    `coke_settings.timezone=America/New_York`

## Risks

- Request/response aggregation could leak onto surfaces that expect push-mode
  multi-message behavior.
  - Mitigation: keep the runtime branch scoped to business ClawScale
    `request_response`.
- Future code paths could still emit already-split sync reply text.
  - Mitigation: keep bridge-side aggregation as a tolerance layer, not only a
    worker-side assumption.

## Notes

Keep the fix narrow: preserve request/response semantics as a single returned
reply string and do not change unrelated channel behavior.
