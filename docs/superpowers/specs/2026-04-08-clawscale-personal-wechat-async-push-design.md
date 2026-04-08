# Spec: Async Push Delivery for Personal `wechat_personal`

## Status

Proposed

## Summary

Restore the missing async outbound path for personal `wechat_personal` channels.

Today, synchronous request/response replies work because the inbound request carries full Clawscale routing metadata and the bridge waits for a direct reply. Scheduled reminders and other proactive outputs do not work end-to-end because they are generated later, outside that request context.

This spec introduces two explicit pieces:

- a dedicated Clawscale push-route registry for Coke-side async delivery
- a running Clawscale output dispatcher worker in the bridge process

The goal is to make reminder/proactive messages reach the same personal WeChat chat thread that produced the inbound message, without reintroducing personal-channel ownership writes into `external_identities`.

## Root Cause Analysis

### What works

The synchronous path is healthy:

1. Gateway receives inbound `wechat_personal` traffic.
2. Gateway forwards it to `/bridge/inbound`.
3. Bridge enqueues a Coke `inputmessage` with Clawscale metadata.
4. Coke processes the message.
5. `reply_waiter` finds the generated `outputmessage` with the matching `bridge_request_id`.
6. Bridge returns the reply synchronously to Gateway.
7. Gateway sends the text back over WeChat.

This was verified with both a synthetic request and real user traffic.

### What fails

The proactive path is broken in two separate places:

1. Reminder/proactive `outputmessages` are created with empty metadata.
2. Even if push metadata were present, no running worker consumes Clawscale push outputs and posts them back to Gateway.

### Evidence

Observed runtime evidence:

- Real reminder scheduling replies such as `提醒设好了` returned normally through the synchronous path.
- Later reminder outputs were written by Coke worker logs:
  - `到点啦，该吃饭了`
  - `记得按时吃，别饿着`
  - `那除了吃饭，今天还有什么想推进的目标吗`
- Those reminder `outputmessages` exist in Mongo with:
  - `status = pending`
  - `platform = wechat`
  - `metadata = {}`
- The same account has no rows in `external_identities`.
- `connector/clawscale_bridge/output_dispatcher.py` exists and is unit-tested, but is not started from `connector/clawscale_bridge/app.py` or any other runtime entrypoint.

### Why metadata is empty

Proactive outputs go through `agent/util/message_util.py`.

Its routing logic is:

1. If there is an inbound `inputmessage` in context, copy its metadata.
2. Otherwise, call `build_clawscale_push_metadata(user_id)`.

For reminders, there is no current inbound `inputmessage`, so the fallback path runs.

That fallback uses `connector/clawscale_bridge/output_route_resolver.py`, which currently resolves push routes through:

- `ExternalIdentityDAO.find_primary_push_target(account_id, source='clawscale')`

This is a legacy assumption from the shared-channel binding model.

In the personal-channel model:

- ownership source of truth is `ClawscaleUser -> owned personal channel`
- personal `wechat_personal` no longer writes ownership rows into `external_identities`

So the resolver returns `{}`, and reminder outputs are written with no Clawscale push metadata.

### Why messages still do not send even if metadata exists

Clawscale async push depends on a separate worker:

- query pending `outputmessages` with `metadata.route_via = 'clawscale'`
- POST them to Gateway `/api/outbound`
- mark them handled or failed

The worker implementation exists in `connector/clawscale_bridge/output_dispatcher.py`, but nothing starts it in production.

So the current system is missing both:

- route resolution for personal async outputs
- runtime dispatch for Clawscale push outputs

## Goals

- Deliver reminder/proactive outputs for personal `wechat_personal` channels.
- Keep synchronous request/response behavior unchanged.
- Stop depending on `external_identities` for personal-channel async routing.
- Preserve legacy shared-channel compatibility where it already exists.
- Reuse the existing Gateway `/api/outbound` surface instead of inventing a second outbound API.

## Non-Goals

- Redesigning personal-channel ownership.
- Reintroducing personal ownership writes into `external_identities`.
- Generalizing all channel types in this change.
- Replacing the synchronous `/bridge/inbound` request/response path.
- Building a full generic message bus for every future outbound transport.

## Approaches Considered

### Approach A: Reuse `external_identities` for personal async routing

Write synthetic or secondary `external_identities` rows for personal channels and keep `OutputRouteResolver` unchanged.

Pros:

- small patch
- least new code

Cons:

- re-couples ownership and delivery routing
- contradicts the personal-channel spec direction
- makes `external_identities` drift back into “source of truth by accident”

Decision: reject.

### Approach B: Introduce a dedicated Clawscale push-route registry and start the dispatcher

Persist trusted outbound push targets separately from ownership, and have async message delivery resolve through that registry.

Pros:

- clean separation of ownership vs delivery route
- works for reminders and other proactive outputs
- extends naturally to future personal channel types

Cons:

- adds one new DAO/model
- requires bridge runtime wiring

Decision: recommended.

### Approach C: Let Coke worker call Gateway outbound directly

Have reminder/proactive code bypass `outputmessages` and call Gateway immediately.

Pros:

- fewer moving parts in the short term

Cons:

- duplicates delivery behavior
- bypasses existing output queue semantics
- mixes conversation logic with gateway transport delivery

Decision: reject.

## Recommended Design

### 1. Add a dedicated Clawscale push-route registry

Add a new Mongo collection managed by Coke/bridge:

- `clawscale_push_routes`

Each row represents the best known async push target for a Coke user on Clawscale.

Suggested shape:

```json
{
  "source": "clawscale",
  "account_id": "69d3db920cb4b1810d8e5fca",
  "platform": "wechat_personal",
  "tenant_id": "tnt_...",
  "channel_id": "ch_...",
  "external_end_user_id": "o9cq...@im.wechat",
  "conversation_id": "conv_...",
  "clawscale_user_id": "csu_...",
  "status": "active",
  "last_seen_at": 1775622666,
  "updated_at": 1775622666
}
```

Rules:

- one latest active route per `(account_id, source, platform, conversation_id)`
- optionally also maintain an account-level latest route for fallback
- the route is delivery state, not ownership state

### 2. Upsert push routes on trusted inbound traffic

Whenever bridge accepts a trusted inbound personal WeChat message, it must upsert the push route using inbound metadata:

- `account_id`
- `tenant_id`
- `channel_id`
- `platform`
- `external_end_user_id`
- `conversation_id`
- `clawscale_user_id` if present

This happens in `IdentityService.handle_inbound(...)`, alongside the existing enqueue path.

This ensures that once a user has successfully talked through a personal channel, future reminders can find their push target even when no live inbound request is active.

### 3. Resolve proactive push targets from push-route registry, not `external_identities`

`build_clawscale_push_metadata(...)` must change behavior.

New resolution order:

1. If conversation-scoped Clawscale push route exists, use it.
2. Else if account-level latest Clawscale push route exists for `wechat_personal`, use it.
3. Else fall back to legacy `external_identities` primary push target for shared/legacy flows only.
4. Else return `{}`.

The output metadata written onto proactive `outputmessages` must include:

- `source = 'clawscale'`
- `route_via = 'clawscale'`
- `delivery_mode = 'push'`
- `tenant_id`
- `channel_id`
- `platform`
- `external_end_user_id`
- `conversation_id` when known
- `push_idempotency_key`

### 4. Start a Clawscale output dispatcher worker in bridge runtime

Bridge runtime must continuously dispatch pending async Clawscale outputs.

Behavior:

1. poll Mongo for pending `outputmessages` where:
   - `status = pending`
   - `metadata.route_via = 'clawscale'`
   - `metadata.delivery_mode = 'push'`
   - `expect_output_timestamp <= now`
2. POST each message to Gateway `/api/outbound`
3. mark:
   - `handled` on `200` or `409`
   - `failed` on non-success responses

This dispatcher should run as a background daemon thread or loop owned by bridge app startup in non-test mode.

The existing `ClawScaleOutputDispatcher` implementation is the correct foundation and should be reused rather than rewritten.

### 5. Keep Gateway outbound route, but make field naming explicit

Gateway already exposes:

- `POST /api/outbound`

It currently accepts `end_user_id`, but for WeChat personal this value is actually the external peer identifier, not the Gateway internal `EndUser.id`.

To avoid future confusion:

- v1 may keep the existing request field for compatibility
- the implementation/spec should explicitly document that the value is the channel-native peer id
- the preferred forward-compatible name is `external_end_user_id`

Gateway may accept both names during transition.

### 6. Preserve legacy behavior

Legacy shared-channel behavior remains supported:

- legacy/shared flows may still use `external_identities`
- the new personal async path must not require those rows

This change is additive for legacy routing and corrective for personal routing.

## Data Model Changes

### New Mongo collection

- `clawscale_push_routes`

Required indexes:

- unique or logically-upserted key on `(source, account_id, platform, conversation_id)`
- lookup index on `(source, account_id, platform, status, last_seen_at)`
- lookup index on `(source, tenant_id, channel_id, external_end_user_id)` if later needed for diagnostics

### No ownership model change

This spec does not change:

- `ClawscaleUser`
- `Channel.scope`
- `ownerClawscaleUserId`
- personal tenant creation

## API and Runtime Changes

### Bridge inbound

No external API contract change is required for `/bridge/inbound`.

Internal behavior changes:

- after trust resolution succeeds, bridge upserts push-route state before or alongside enqueue

### Bridge runtime

On app startup in non-test mode:

- construct `ClawScaleOutputDispatcher`
- construct a small polling loop using configured outbound URL/API key
- run it in the background

### Gateway outbound

Gateway `/api/outbound` remains the transport delivery ingress.

It should continue to:

- authenticate with `CLAWSCALE_OUTBOUND_API_KEY`
- resolve channel by `tenant_id + channel_id`
- send the text to the specified external WeChat peer through `wechat_personal`

## Failure Semantics

### Missing route

If no push route can be resolved for a proactive message:

- the output remains pending or is moved to failed according to the chosen implementation
- the system must log a precise reason, such as `missing_clawscale_push_route`

This must be visible in logs and testable.

### Dispatcher delivery failure

If Gateway `/api/outbound` returns non-success:

- mark the message `failed`
- preserve enough metadata to diagnose tenant/channel/peer target

### Idempotency

Each async push output must carry `push_idempotency_key`.

Gateway should continue treating repeated keys as safe duplicate delivery attempts.

## Acceptance Criteria

1. A personal `wechat_personal` user can send a message, schedule a reminder, and later receive the reminder over the same WeChat chat thread.
2. Reminder/proactive `outputmessages` for that user are written with non-empty Clawscale push metadata.
3. Personal async push no longer requires an `external_identities` row for the account.
4. Bridge process actively dispatches pending Clawscale push outputs without manual intervention.
5. Legacy request/response replies still work unchanged.
6. Legacy shared-channel flows continue to rely on old compatibility logic where needed.

## Out of Scope

- Removing the already-fixed backend label prefix from historical messages
- Multi-platform async push generalization beyond `wechat_personal`
- Member/admin UI for inspecting async push routes

