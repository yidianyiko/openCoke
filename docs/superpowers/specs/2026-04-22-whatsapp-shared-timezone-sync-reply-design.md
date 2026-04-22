# WhatsApp Shared Timezone And Sync Reply Repair Design

Date: 2026-04-22

## Scope

This repair closes two user-visible regressions on the shared WhatsApp
request/response path:

- timezone changes for synthetic shared-channel users must persist even when
  `coke_settings` does not exist yet
- same-turn text output must return to the user as one coherent reply instead
  of silently dropping later segments

It covers:

- `UserDAO` settings-write semantics for shared business accounts
- request/response text aggregation across the worker runtime and bridge
- focused regression coverage for both failures
- production verification on `gcp-coke`

It does not change:

- web UI or settings pages
- prompt wording or persona tuning
- push-mode outbound delivery behavior
- non-text multipart reply protocols

## Problem

The live WhatsApp E2E run exposed two distinct failures on the same user path.

### 1. Timezone updates fail for first-time shared users

Shared WhatsApp users are provisioned as synthetic Coke accounts on ingress.
Those accounts may not have a pre-created `coke_settings` document.

The timezone tool can correctly resolve `"纽约"` to `America/New_York`, but the
write path only succeeds when a settings document already exists. For a first-
time shared user, the runtime acknowledges the timezone change in conversation
while persistence fails underneath. The next reminder or time-based action then
falls back to the default timezone instead of the user-selected timezone.

### 2. Request/response turns lose later text segments

The shared WhatsApp bridge is operating in request/response mode, which means
one inbound message should produce one returned reply payload.

The worker runtime currently allows a turn to emit multiple text outputs in
sequence. That is valid for push-mode channels, but it breaks the shared
request/response contract. The first text output is handled, while later text
outputs for the same causal inbound event are marked failed or left pending
with `failure_reason=unexpected_extra_request_response_output`.

From a real user's perspective, the agent "said" more than one thing
internally, but only the first part arrived.

## Goal

Make the shared WhatsApp request/response path reliable for the two affected
behaviors.

Required user experience:

1. A new shared WhatsApp user says `"我现在在纽约，之后按纽约时间和我说"`.
2. The assistant replies normally in that same turn.
3. The resolved timezone persists to `coke_settings.timezone`.
4. Later reminder/time parsing uses `America/New_York` for that user.
5. A request/response turn that would otherwise emit multiple text outputs
   returns one combined text reply in order.
6. The runtime does not leave extra failed or pending text outputs for that
   same turn.

## Design

### 1. Make settings writes create `coke_settings` when missing

`UserDAO` should treat user settings as an upserted document keyed by
`account_id`, not as a record that must already exist.

Behavior:

- write timezone changes with `upsert=True`
- preserve existing settings fields when the document already exists
- create the minimal settings document when it does not
- treat a matched-or-upserted write as success, even if the timezone value is
  unchanged

This keeps the tool contract aligned with user intent: "set my timezone"
should succeed whether the settings document already exists, needs creation, or
already holds the same value.

### 2. Preserve request/response semantics as one returned text reply

The shared WhatsApp bridge should continue to behave like a single-response
channel. The repair should not redefine that channel as multi-message push.

The runtime therefore needs to normalize multiple same-turn text outputs into
one returned reply string for this specific surface.

Target behavior:

- scope the aggregation to `business` context plus ClawScale
  `request_response`
- buffer same-turn text chunks in generation order
- flush one combined text output when the turn finishes
- leave push-mode and non-text outputs unchanged

This makes the reply contract explicit at the worker boundary instead of
letting the bridge discover an impossible multi-output situation afterward.

### 3. Keep the bridge tolerant to already-split same-turn text output

The worker-side aggregation is the primary fix, but the bridge should also stay
robust if multiple pending sync text outputs already exist for the same causal
event.

Bridge-side handling should therefore:

- look up pending sync text outputs for the same inbound causal event
- combine them in order when forming the returned reply
- mark the consumed outputs handled together
- avoid producing `unexpected_extra_request_response_output` for this specific
  same-turn sync text case

This gives the request/response path a safe fallback during rollout and keeps
the bridge tolerant if a future code path temporarily reintroduces split text
output upstream.

## Non-Goals

- redesigning channel delivery contracts across all connectors
- changing how image, file, or structured outputs are represented
- building a visible timezone-management product surface
- changing personal-channel reply behavior

## Risks

1. Upserting settings could hide invalid caller assumptions if an unexpected
   account id reaches the DAO.
   Mitigation: keep the query key as `account_id`, only write the minimal
   settings shape, and rely on existing account provisioning paths.

2. Request/response aggregation could accidentally collapse output on surfaces
   that still expect multiple pushed messages.
   Mitigation: scope aggregation narrowly to shared business
   `request_response`.

3. Bridge-side aggregation could reorder or double-consume outputs if the
   pending lookup is stale.
   Mitigation: refresh pending sync outputs immediately before consume/mark and
   keep ordering tied to the causal event sequence.

## Verification

- Targeted unit tests:
  - `pytest tests/unit/agent/test_agent_handler.py tests/unit/test_user_dao_timezone.py tests/unit/agent/test_message_util_clawscale_routing.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py tests/unit/test_timezone_tools.py -v`
- Production E2E on `gcp-coke`:
  - replay `"你好"` through the real WhatsApp webhook and confirm one handled
    text output with no extra pending tail
  - replay `"我现在在纽约，之后按纽约时间和我说"` and confirm the assistant
    reply plus persisted `coke_settings.timezone=America/New_York`

## Outcome

This repair keeps the shared WhatsApp path within its existing product
contract:

- one inbound request gets one reply payload
- timezone changes persist for newly provisioned shared users
- the bridge stops losing user-visible text generated later in the same turn
