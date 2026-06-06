---
status: in-progress
created_at: 2026-06-07
spec: docs/superpowers/specs/2026-06-07-delivery-reliability-onboarding-design.md
scope:
  - Track B: waiting-message delivery recovery
  - Track F: notification recipient lifecycle
  - Track G: onboarding prompt wiring
---

# Delivery Reliability And Onboarding Plan

## Constraints

- Preserve the single user-facing producer invariant.
- Do not add typed renderers, keyword/regex routing, pending approval flows,
  compatibility shims, or legacy fallbacks.
- Do not regress `pending_async_reply`: waiting visibility must not materialize
  staged commands, close the input window, advance `last_closed_inbound_seq`, or
  create a durable interruption artifact.
- Implement strictly test-first. Each behavior change starts with a failing test.
- Commit small coherent changes on `fix/eva-rca-reliability` only.

## Phase 1: TDD Tests

- [ ] Add Track B waiting-delivery tests:
  - provider `failed/provider_network_error` leaves turn active, keeps staged
    commands unmaterialized, preserves `last_closed_inbound_seq`, persists a
    failed waiting delivery envelope, and later final reply transitions to
    `replied`;
  - retryable waiting failure uses logical intents `turn_id:waiting:1` and
    `turn_id:waiting:2`;
  - token/session-window failures do not retry.
- [ ] Run the focused Track B tests and confirm they fail for missing behavior:
  `.venv/bin/python -m pytest tests/unit/coke/worker/test_waiting_reply.py tests/unit/coke/turn/test_turn_runner.py -k "waiting or pending_async" -v`.
- [ ] Add Track F notification lifecycle tests:
  - invalid `NotificationTurn` output settles recipients failed;
  - completed notification render turn cannot leave a recipient pending;
  - reconciler settles stale pending recipients only after terminal completion.
- [ ] Run the focused Track F tests and confirm they fail for missing behavior:
  `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/test_delivery_lifecycle_callbacks.py tests/integration/coke/test_social_scheduling_notification_outbox_contract.py -k "notification" -v`.
- [ ] Add Track G onboarding tests:
  - first inbound with `onboarding_guidance_required` injects exactly one
    supported-capability onboarding block;
  - later inbound turns omit the block;
  - `first_guidance_sent_at` stamps only after a committed visible final
    onboarding reply, not waiting/no-reply/invalid/access-denied/provider-failed
    paths.
- [ ] Run the focused Track G tests and confirm they fail for missing behavior:
  `.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/identity_access -k "onboarding or guidance" -v`.

## Phase 2: Track B Implementation

- [ ] Extend delivery diagnostics data structures:
  - add optional delivery envelope fields to `DeliveryRequest`;
  - add nullable diagnostic columns to `schema.delivery_attempt` and a new
    migration;
  - extend `DeliveryAttempt`, repository serialization, and
    `ChannelReachabilityService.send_text()`;
  - measure adapter latency and persist source/intent/retry/trace/container/token
    diagnostics.
- [ ] Add context-token observation support in conversation runtime so waiting
  sends can record token source and age without mutating turn state.
- [ ] Centralize waiting delivery:
  - generate logical intents `turn_id:waiting:1` and `turn_id:waiting:2`;
  - persist/log buckettable waiting outcomes;
  - catch provider exceptions as failed waiting delivery evidence;
  - leave `pending_async_reply` open.
- [ ] Add bounded retry policy:
  - retry once only for retryable transport errors;
  - never retry token/session-window failures;
  - check the latest turn disposition before retry;
  - add per-route/account circuit breaker state.

## Phase 3: Track F Implementation

- [ ] Make `TurnRunner` settle notification recipients on every terminal
  `NotificationTurn` path: valid delivery, invalid output, no-reply retry
  failure, generic turn failure, start/lock failure, and supersession.
- [ ] Add SocialScheduling notification-recipient reconciler:
  - scan pending recipients older than threshold;
  - check terminal turn disposition through a runtime port;
  - settle failed/undelivered with structured informational facts only;
  - do not resend or perform actions.

## Phase 4: Track G Implementation

- [ ] Inject onboarding guidance facts from the identity gate and existing
  configured settings only when `onboarding_guidance_required` is true.
- [ ] Render a conditional `onboarding_guidance` prompt block in the Interaction
  Agent with only current product capabilities.
- [ ] Stamp first guidance only after committed visible final onboarding reply
  delivery; preserve the onboarding flag through async final replies and do not
  stamp on waiting, no-reply, invalid output, access-denied, superseded, or
  provider-failed paths.

## Phase 5: Docs And Verification

- [ ] Update `docs/ARCHITECTURE.md` for delivery attempt diagnostics, waiting
  retry boundary, notification terminal settlement/reconciler, and onboarding
  stamp semantics.
- [ ] Run focused tests for all touched behavior and make them pass.
- [ ] Run required unit scope:
  `.venv/bin/python -m pytest tests/unit/coke/worker tests/unit/coke/turn tests/unit/coke/identity_access tests/unit/coke/llm -v`, plus notification/integration tests touched.
- [ ] Run diff-aware routing:
  `zsh scripts/suggest-verification --base HEAD~1`.
- [ ] Run risk trigger report:
  `zsh scripts/review-trigger --base HEAD~1`.
- [ ] Follow the suggested verification surface and record real output.
- [ ] Commit implementation/docs/test changes in small coherent commits with
  `Co-Authored-By: Codex <noreply@openai.com>`.
