# Clawscale Personal WeChat Async Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make reminder and other proactive outputs reach the same personal `wechat_personal` chat thread as normal synchronous replies.

**Architecture:** Introduce a dedicated Clawscale push-route registry in Coke, update bridge inbound handling to keep that registry fresh, resolve proactive push metadata from it instead of `external_identities`, and run a bridge-side output dispatcher loop that pushes pending async messages to Gateway `/api/outbound`.

**Tech Stack:** Python 3.12, Flask, PyMongo, requests, pytest, MongoDB, TypeScript, Hono, PostgreSQL

---

## File Structure

### New files

- `dao/clawscale_push_route_dao.py`
  DAO for storing and resolving async Clawscale push routes.
- `tests/unit/dao/test_clawscale_push_route_dao.py`
  DAO tests for upsert, conversation lookup, and account-level fallback.

### Modified files

- `connector/clawscale_bridge/identity_service.py`
  Upserts trusted personal-channel push routes during inbound handling.
- `connector/clawscale_bridge/output_route_resolver.py`
  Resolves proactive push targets from the new DAO first, then legacy fallback.
- `connector/clawscale_bridge/output_dispatcher.py`
  Reused as the actual async push transport worker.
- `connector/clawscale_bridge/app.py`
  Starts the dispatcher loop in non-test runtime.
- `agent/util/message_util.py`
  Builds proactive Clawscale push metadata from conversation/account push routes.
- `conf/config.json`
  Adds or clarifies outbound dispatcher poll interval / config usage.
- `tests/unit/connector/clawscale_bridge/test_identity_service.py`
  Covers push-route upsert behavior.
- `tests/unit/connector/clawscale_bridge/test_output_route_resolver.py`
  Covers new route lookup order.
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  Covers dispatcher startup in app wiring where practical.
- `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
  Covers delivery success/failure and idempotent handling.
- `tests/unit/agent/test_message_util_clawscale_routing.py`
  Covers proactive metadata generation from push-route registry.
- `gateway/packages/api/src/routes/outbound.ts`
  Optional compatibility support for `external_end_user_id` alias.
- `gateway/packages/api/src/routes/outbound.test.ts`
  Covers outbound alias handling if implemented.

## Task 1: Add Clawscale push-route DAO

**Files:**
- Create: `dao/clawscale_push_route_dao.py`
- Test: `tests/unit/dao/test_clawscale_push_route_dao.py`

- [ ] **Step 1: Write the failing DAO tests**

Write tests for:

- `upsert_route(...)` stores or updates a conversation-scoped route
- `find_route_for_conversation(...)` returns the latest active match
- `find_latest_route_for_account(...)` returns the latest account-level fallback

- [ ] **Step 2: Run the DAO tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/dao/test_clawscale_push_route_dao.py -q`

Expected: FAIL because the DAO file and methods do not exist yet.

- [ ] **Step 3: Implement the DAO**

Add:

- constructor with Mongo collection `clawscale_push_routes`
- index creation helper
- `upsert_route(...)`
- `find_route_for_conversation(...)`
- `find_latest_route_for_account(...)`

- [ ] **Step 4: Re-run the DAO tests**

Run: `.venv/bin/python -m pytest tests/unit/dao/test_clawscale_push_route_dao.py -q`

Expected: PASS

## Task 2: Persist push routes from trusted inbound traffic

**Files:**
- Modify: `connector/clawscale_bridge/identity_service.py`
- Test: `tests/unit/connector/clawscale_bridge/test_identity_service.py`

- [ ] **Step 1: Write the failing identity-service tests**

Add tests covering:

- trusted personal inbound upserts a push route before waiting for reply
- legacy fallback path does not regress

- [ ] **Step 2: Run the targeted identity-service tests**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_identity_service.py -q`

Expected: FAIL on missing push-route persistence expectations.

- [ ] **Step 3: Implement push-route upsert in inbound handling**

Use trusted inbound metadata to write:

- `account_id`
- `tenant_id`
- `channel_id`
- `platform`
- `external_end_user_id`
- `conversation_id`
- `clawscale_user_id` when present

- [ ] **Step 4: Re-run the identity-service tests**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_identity_service.py -q`

Expected: PASS

## Task 3: Resolve proactive push metadata from push routes

**Files:**
- Modify: `connector/clawscale_bridge/output_route_resolver.py`
- Modify: `agent/util/message_util.py`
- Test: `tests/unit/connector/clawscale_bridge/test_output_route_resolver.py`
- Test: `tests/unit/agent/test_message_util_clawscale_routing.py`

- [ ] **Step 1: Write the failing resolver and message-util tests**

Add tests for:

- conversation-scoped route wins
- account-level route fallback works
- legacy `external_identities` fallback still works
- proactive output gets `route_via=clawscale` metadata without inbound input metadata

- [ ] **Step 2: Run the targeted tests**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_output_route_resolver.py tests/unit/agent/test_message_util_clawscale_routing.py -q`

Expected: FAIL on the new route lookup order.

- [ ] **Step 3: Implement the new lookup order**

Update `OutputRouteResolver` and `build_clawscale_push_metadata(...)` so that:

1. conversation route is preferred
2. account-level route is fallback
3. legacy `external_identities` lookup is last

- [ ] **Step 4: Re-run the targeted tests**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_output_route_resolver.py tests/unit/agent/test_message_util_clawscale_routing.py -q`

Expected: PASS

## Task 4: Start the Clawscale output dispatcher in bridge runtime

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `conf/config.json`
- Test: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write the failing runtime-wiring tests**

Add tests that prove:

- bridge app constructs the dispatcher in non-test mode
- dispatcher loop uses configured outbound URL/API key
- dispatch success marks output handled

- [ ] **Step 2: Run the targeted dispatcher/app tests**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_output_dispatcher.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -q`

Expected: FAIL because no dispatcher loop is started today.

- [ ] **Step 3: Implement dispatcher runtime wiring**

In non-test app startup:

- build `ClawScaleOutputDispatcher`
- start a daemon loop/thread polling pending push outputs
- use config values for outbound URL/API key and polling interval

- [ ] **Step 4: Re-run the dispatcher/app tests**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_output_dispatcher.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -q`

Expected: PASS

## Task 5: Make Gateway outbound contract explicit for external peer IDs

**Files:**
- Modify: `gateway/packages/api/src/routes/outbound.ts`
- Test: `gateway/packages/api/src/routes/outbound.test.ts`

- [ ] **Step 1: Write the failing Gateway outbound tests**

Cover one of these explicit decisions:

- accept both `end_user_id` and `external_end_user_id`, or
- rename the field and keep a compatibility alias

- [ ] **Step 2: Run the Gateway outbound tests**

Run: `pnpm --dir gateway/packages/api exec vitest run src/routes/outbound.test.ts`

Expected: FAIL on the new contract expectation.

- [ ] **Step 3: Implement the chosen compatibility behavior**

Keep transport semantics the same, but make the naming explicit so the route no longer implies internal `EndUser.id`.

- [ ] **Step 4: Re-run the Gateway outbound tests**

Run: `pnpm --dir gateway/packages/api exec vitest run src/routes/outbound.test.ts`

Expected: PASS

## Task 6: End-to-end regression coverage for personal reminders

**Files:**
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Modify: `tests/unit/agent/test_message_util_clawscale_routing.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_identity_service.py`

- [ ] **Step 1: Add one regression scenario for personal reminder async delivery**

The scenario should prove:

- personal inbound traffic creates a push route
- proactive message later gets Clawscale push metadata
- dispatcher sends it to Gateway outbound

- [ ] **Step 2: Run the focused regression suite**

Run: `.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_identity_service.py tests/unit/agent/test_message_util_clawscale_routing.py -q`

Expected: PASS

## Task 7: Manual verification checklist

**Files:**
- Modify: `docs/superpowers/specs/2026-04-08-clawscale-personal-wechat-async-push-design.md`
- Modify: `docs/superpowers/plans/2026-04-08-clawscale-personal-wechat-async-push-plan.md`

- [ ] **Step 1: Restart the three local services**

Run:

- `gateway api`
- `bridge app`
- `agent_runner`

- [ ] **Step 2: Verify synchronous reply still works**

Send a normal WeChat message such as `你是谁`.

Expected:

- Gateway logs inbound message
- Bridge `/bridge/inbound` returns `200`
- WeChat receives the reply

- [ ] **Step 3: Verify reminder/proactive async push works**

Send:

- `五分钟后提醒我吃饭`

Expected:

- immediate synchronous reply confirms scheduling
- later reminder messages are delivered over the same WeChat chat thread
- reminder `outputmessages` are marked `handled` instead of staying `pending`

- [ ] **Step 4: Verify logs show correct route metadata**

Check:

- reminder `outputmessages` have `route_via = clawscale`
- they include `tenant_id`, `channel_id`, and `external_end_user_id`

