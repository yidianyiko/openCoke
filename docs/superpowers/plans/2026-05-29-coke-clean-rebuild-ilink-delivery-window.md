# iLink Delivery Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Make personal-WeChat proactive/render delivery honest inside the latest `context_token` window, retry eligible undelivered reminders on the next inbound, and persist `delivery_attempt.message_id` audit links.

**Architecture:** Keep iLink-specific send-window behavior inside ChannelReachability and the provider adapter boundary. Keep resend scheduling in the inbound webhook/conversation outbox path so the next user message refreshes the token before an `UndeliveredResendTurn` is enqueued. Keep output-class delivery state separate from turn disposition: reminders become undelivered, proactive fires discard, and notification recipients record undelivered/failed per recipient.

**Tech Stack:** Python, Flask blueprints, SQLAlchemy metadata/repositories, in-memory unit fakes, pytest.

---

## File Structure

- Modify `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py`: RED tests for missing/latest context-token send behavior, message-id attempt linkage, and `errcode=-14` reconnection.
- Modify `tests/unit/coke/channel_reachability/test_provider_webhooks.py`: RED test that a new inbound with pending undelivered fires enqueues an `UndeliveredResendTurn`.
- Modify `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`: RED test that undelivered notification recipient facts are returned for resend and failed/delivered recipients are excluded.
- Modify `tests/unit/coke/turn/test_turn_runner.py`: RED test that render delivery requests carry the outbound `message_id`.
- Create `tests/unit/coke/test_delivery_lifecycle_callbacks.py`: RED tests for `ret=-2` mapping to reminder undelivered, notification recipient undelivered, and proactive discard.
- Modify `tests/unit/coke/worker/test_notification_render_trigger.py`: RED test for worker support of `turn.undelivered_resend`.
- Modify `tests/unit/coke/llm/test_interaction_agent.py`: RED test that undelivered notification facts are visible in render context.
- Modify `coke/domains/channel_reachability/service.py`: let missing iLink context tokens become failed attempts, map session-expired provider errors to `reconnection_required`.
- Modify `coke/composition.py`: pass `message_id` into `send_text`, classify context-token-window failures as undelivered, and preserve proactive discard.
- Modify `coke/turn/runner.py`: add `DeliveryRequest.message_id`, attach committed outbound message ids to delivery requests, and aggregate output-class lifecycle writeback after delivery.
- Modify `coke/domains/conversation_runtime/service.py`: add a focused helper to enqueue render outbox records for inbound-triggered undelivered resend.
- Modify `coke/api/provider_webhooks.py`: after durable inbound record, enqueue resend for pending undelivered reminder fires using the refreshed token window.
- Modify `coke/domains/social_scheduling/{models,service}.py`: expose undelivered notification recipient facts for resend without inventing schema.
- Modify `coke/llm/agno_interaction_agent.py`: expose hydrated undelivered notification facts in render context.
- Modify `coke/worker/__main__.py`: route `turn.undelivered_resend` to `UndeliveredResendTurn`.
- Modify `coke/app.py`: pass the existing composed `reminder_service` and `social_scheduling_service` into provider webhook registration.

### Task 1: Write RED Tests

- [x] **Step 1: Add iLink send-window and audit tests**

In `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py`, add tests that:

```python
def test_wechat_personal_missing_context_token_records_failed_attempt_with_message_link():
    # Arrange a connected personal WeChat route and call send_text with
    # context_token=None and message_id="message_1".
    # Assert no exception, status == "failed", error_code == "context_token_required",
    # and attempt.message_id == "message_1".


def test_wechat_personal_session_expiry_marks_channel_reconnection_required():
    # Arrange an adapter that returns DeliveryAttemptResult(
    #     status="failed", error_code="ilink_send_failed_errcode_-14"
    # ).
    # Assert send_text persists a failed attempt and the active channel state is
    # "reconnection_required".
```

- [x] **Step 2: Add turn runner message-link test**

In `tests/unit/coke/turn/test_turn_runner.py`, add:

```python
def test_render_delivery_request_links_committed_outbound_message_id(harness):
    result = harness["runner"].run_render_turn(...)
    outbound = harness["runtime"].outbound_messages_for_turn(result.turn_id)
    assert harness["delivery"].deliveries[-1].message_id == outbound[0].id
```

- [x] **Step 3: Add delivery lifecycle mapping tests**

Create `tests/unit/coke/test_delivery_lifecycle_callbacks.py` with tests that call `OutputLifecycleDeliveryCallbacks.record_delivery(...)` using `DeliveryOutcome(status="failed", error_code="ilink_send_failed_ret_-2")` and assert:

```python
assert reminder_fire.delivery_result == "undelivered"
assert notification_recipient.delivery_state == "undelivered"
assert proactive_fire.fire_state == "discarded"
```

- [x] **Step 4: Add inbound-triggered resend outbox test**

In `tests/unit/coke/channel_reachability/test_provider_webhooks.py`, wire a fake reminder service whose `undelivered_resend_turn("acct_1")` returns fire ids and assert the webhook records inbound, then calls `enqueue_render_turn` with:

```python
topic="turn.undelivered_resend"
payload["trigger_type"] == "UndeliveredResendTurn"
payload["fire_ids"] == ["fire_1", "fire_2"]
```

- [x] **Step 5: Add notification resend tests**

Add tests that an inbound with pending undelivered notification recipients enqueues the same `UndeliveredResendTurn` with `notification_fact_ids`, that resend delivery updates `notification_recipient`, and that worker/render context hydrates those notification facts.

- [x] **Step 6: Add worker trigger routing test**

In `tests/unit/coke/worker/test_notification_render_trigger.py`, assert `_turn_trigger_from_event(...)` maps `topic="turn.undelivered_resend"` to `trigger_type == "UndeliveredResendTurn"`.

- [x] **Step 7: Run RED tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py \
  tests/unit/coke/channel_reachability/test_provider_webhooks.py \
  tests/unit/coke/turn/test_turn_runner.py \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py \
  tests/unit/coke/worker/test_notification_render_trigger.py \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py \
  tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: FAIL for missing implementation (`message_id` missing on `DeliveryRequest`, missing resend enqueue helper, missing worker topic, current context-token precheck, and current notification failure classification).

### Task 2: Implement Delivery Window Semantics

- [x] **Step 1: Update channel send attempts**

In `coke/domains/channel_reachability/service.py`, remove the pre-adapter `context_token_required` exception and always persist the provider result as a `DeliveryAttempt`. After a failed personal-WeChat send, if the error code denotes session expiry (`errcode_-14` or `session_expired`), save the channel state as `reconnection_required`.

- [x] **Step 2: Attach outbound message ids**

In `coke/turn/runner.py`, add `message_id: str | None = None` to `DeliveryRequest`. After `commit_reply`, read `outbound_messages_for_turn(turn_id)` and assign the committed message id to each delivery request. For waiting text, record one outbound message before delivery and pass its id.

- [x] **Step 3: Pass message ids into attempts**

In `coke/composition.py`, pass `request.message_id` into `ChannelReachabilityService.send_text(...)`.

- [x] **Step 4: Classify output delivery by error class**

In `coke/composition.py`, classify failed context-token-window outcomes (`context_token_required`, `*_ret_-2`) as undelivered. Keep reminders undelivered, notifications `undelivered`, and proactive fires discarded. Keep non-window notification failures as `failed`.

### Task 3: Implement Resend-On-Next-Inbound

- [x] **Step 1: Add render outbox enqueue helper**

In `coke/domains/conversation_runtime/service.py`, add `enqueue_render_turn(...)` that creates an `OutboxRecord` with caller-provided topic, idempotency key, payload, and traceparent.

- [x] **Step 2: Enqueue resend after inbound persistence**

In `coke/api/provider_webhooks.py`, accept optional `reminder_service` and `social_scheduling_service`. After `record_inbound(...)`, call `reminder_service.undelivered_resend_turn(accepted.account_id)` and `social_scheduling_service.undelivered_notification_resend_turn(accepted.account_id)`. If either returns ids, enqueue `turn.undelivered_resend` with a trigger id scoped to the inbound event so later inbound messages can retry again if delivery still fails.

- [x] **Step 3: Wire app and worker**

In `coke/app.py`, pass `reminder_service` and `social_scheduling_service` into `create_provider_webhook_blueprint(...)`. In `coke/worker/__main__.py`, include `turn.undelivered_resend` in render topics, map it to `UndeliveredResendTurn`, and hydrate any notification facts included in the resend payload.

### Task 4: Verify And Commit

- [x] **Step 1: Run focused tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py \
  tests/unit/coke/channel_reachability/test_provider_webhooks.py \
  tests/unit/coke/turn/test_turn_runner.py \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py \
  tests/unit/coke/worker/test_notification_render_trigger.py \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py \
  tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: all focused tests pass.

- [x] **Step 2: Run requested unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 3: Run requested integration suite**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: all integration tests pass, or report honestly if no integration suite exists or the local database is unavailable.

- [x] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-ilink-delivery-window.md coke tests/unit/coke
git commit -m "fix: enforce ilink delivery window lifecycle"
```

Verification evidence:

- Focused notification/resend tests: `64 passed in 2.46s`.
- Requested unit suite: `484 passed in 17.07s`.
- Requested integration suite: `46 passed in 4.57s`.
- Suggested surface verification: `clean-rebuild-backend` passed with `484 passed in 16.59s`; `clean-rebuild-web` passed with `51 passed (51)` / `214 passed (214)` and `pnpm build`; `repo-os-docs` passed with `check passed`.
