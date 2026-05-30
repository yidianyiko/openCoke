# RR4 Provider Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace provider stubs with real HTTP-backed adapters and real Evolution WhatsApp webhook normalization behind Coke's canonical provider contract.

**Architecture:** Provider adapters remain edge anti-corruption modules: they normalize inbound provider payloads and perform outbound sends only. Channel identity, channel lifecycle, account provisioning, access gates, and delivery attempt persistence stay in IdentityAccess and ChannelReachability. Evolution WhatsApp is the primary live channel; WeChat personal, WeChat eCloud, and Linq are retained peer adapters with lighter real HTTP shapes.

**Tech Stack:** Flask webhook routes, synchronous `httpx`, `coke.domains.channel_reachability` provider dataclasses, pytest monkeypatched transports, existing `coke/schema.py` tables only.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Freshness Check:** Verified against `docs/superpowers/plans/2026-05-30-coke-runtime-readiness.md`, requirements §5.3/§5.4/§5.13, target architecture §3.1/§3.2/§3.3/§4/§8/§9/§14, `coke/schema.py`, and current provider/webhook code on 2026-05-30.

## File Structure

- Modify: `requirements.txt` to add `httpx` if it is not already available as a direct runtime dependency.
- Modify: `coke/providers/base.py` only for shared provider parsing/HTTP result helpers needed by adapters.
- Modify: `coke/providers/whatsapp_evolution.py` to parse real Evolution `messages.upsert` payloads and POST `sendText` to Evolution.
- Modify: `coke/providers/wechat_personal.py` to normalize ClawScale-style payloads and POST outbound text through an injected HTTP endpoint.
- Modify: `coke/providers/wechat_ecloud.py` to normalize gewe-style payloads and POST outbound text through an injected HTTP endpoint.
- Modify: `coke/providers/linq.py` to normalize SMS payloads and POST outbound text through an injected HTTP endpoint.
- Modify: `coke/api/provider_webhooks.py` only if the Evolution route does not pass raw JSON through adapter normalization and `accept_provider_inbound`.
- Modify: `tests/unit/coke/channel_reachability/test_provider_adapters.py` for adapter normalization and HTTP send contract tests.
- Modify: `tests/unit/coke/channel_reachability/test_provider_webhooks.py` for the real Evolution webhook route shape.

## Task 1: Evolution Inbound Normalization

**Files:**
- Modify: `tests/unit/coke/channel_reachability/test_provider_adapters.py`
- Modify: `coke/providers/whatsapp_evolution.py`

- [x] **Step 1: Write failing tests for real Evolution payloads**

Add tests that build payloads like:

```python
{
    "event": "messages.upsert",
    "instance": "coke",
    "data": {
        "key": {
            "remoteJid": "15555550123@s.whatsapp.net",
            "fromMe": False,
            "id": "EVT1",
        },
        "pushName": "Alice",
        "message": {"conversation": "hi"},
        "messageTimestamp": 1700000000,
    },
}
```

Assertions:
- `provider_subject == "15555550123"`
- `raw_event_id == "EVT1"`
- `text == "hi"`
- `received_at == datetime.fromtimestamp(1700000000, UTC)`
- full payload is preserved as immutable JSON evidence
- the extended text variant reads `data.message.extendedTextMessage.text`
- image/audio payloads normalize to `text == ""`
- `data.key.fromMe == True` raises `ChannelReachabilityError("provider_outbound_echo")`

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py -q
```

Expected: the new Evolution tests fail because the adapter still expects simplified `message_id`/`sender` fields and returns stub sends.

- [x] **Step 3: Implement Evolution normalization**

Implementation rules:
- require top-level `event == "messages.upsert"`
- require `data.key.remoteJid`, `data.key.id`, and `data.key.fromMe`
- strip `@s.whatsapp.net` and `@g.us` suffixes from `remoteJid`
- reject outbound echoes with `ChannelReachabilityError("provider_outbound_echo")`
- read text from `message.conversation` or `message.extendedTextMessage.text`
- treat media-only messages as accepted inbound with blank text and preserved payload
- parse `messageTimestamp` as UTC epoch seconds
- keep pairing-code extraction from explicit `pairing_code` or text token if already supported by existing tests

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py -q
```

Expected: provider adapter tests pass.

## Task 2: Real HTTP Send Adapters

**Files:**
- Modify: `requirements.txt`
- Modify: `tests/unit/coke/channel_reachability/test_provider_adapters.py`
- Modify: `coke/providers/base.py`
- Modify: `coke/providers/whatsapp_evolution.py`
- Modify: `coke/providers/wechat_personal.py`
- Modify: `coke/providers/wechat_ecloud.py`
- Modify: `coke/providers/linq.py`

- [x] **Step 1: Write failing send tests with mocked HTTP**

Add tests that construct adapters with injected base URLs/API keys and monkeypatched HTTP transports:
- Evolution sends `POST {base_url}/message/sendText/{instance}` with header `apikey` and body `{"number": route.provider_address, "text": text}`.
- Evolution 2xx maps to `DeliveryAttemptResult(status="sent" or "delivered", provider_message_id=<provider id>, error_code=None)` and preserves the caller's idempotency key in the request.
- Evolution 5xx and timeout map to `status == "failed"` with a user-safe `error_code`; never `delivered`.
- WeChat personal, WeChat eCloud, and Linq make real HTTP POSTs to their configured endpoint and map 2xx/failure the same way.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py -q
```

Expected: send tests fail because current adapters do not call HTTP.

- [x] **Step 3: Implement HTTP send helpers and adapters**

Implementation rules:
- use synchronous `httpx`
- constructors accept injected config, with no hardcoded secrets or live URLs
- Evolution constructor accepts `base_url`, `api_key`, `instance`, optional `timeout`, optional client
- Evolution request uses `apikey: <api_key>` and `Idempotency-Key: <idempotency_key>`
- success extracts provider message id from common response fields such as `key.id`, `id`, `messageId`, or `message_id`
- non-2xx and network exceptions return failed `DeliveryAttemptResult` with user-safe reason strings such as `provider_http_500` or `provider_network_error`
- never mark a failed HTTP/network send as delivered

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py -q
```

Expected: provider adapter tests pass.

## Task 3: Webhook Route Contract

**Files:**
- Modify: `tests/unit/coke/channel_reachability/test_provider_webhooks.py`
- Modify: `coke/api/provider_webhooks.py`

- [x] **Step 1: Write failing route test for Evolution JSON**

Add a Flask route test posting the real Evolution `messages.upsert` JSON to `/webhooks/whatsapp/evolution`. Assert the route calls `adapter.normalize_inbound(raw_payload)` and passes the returned `NormalizedInbound` to `reachability_service.accept_provider_inbound`.

- [x] **Step 2: Run focused webhook tests and verify RED if current behavior is wrong**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_webhooks.py -q
```

Expected: pass if the route already forwards raw JSON correctly; otherwise fail for the missing behavior.

- [x] **Step 3: Adjust route only if necessary**

Keep the route thin: raw JSON body → adapter normalization → `accept_provider_inbound` → structured identity facts. Do not add identity/channel logic to the route.

- [x] **Step 4: Run focused webhook tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_webhooks.py -q
```

Expected: webhook tests pass.

## Task 4: Full Verification, Plan Closeout, Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-rr4-provider-adapters.md`

- [x] **Step 1: Run full unit suite**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 2: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete; review-trigger is non-blocking risk evidence.

- [x] **Step 3: Mark this plan complete**

Update checkboxes and set:

```md
**Plan Status:** complete
```

- [x] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-rr4-provider-adapters.md requirements.txt coke/providers coke/api/provider_webhooks.py tests/unit/coke/channel_reachability
git commit -m "feat: implement real provider adapters"
```

Expected: one coherent RR4 commit containing plan, tests, adapter implementation, and route adjustments if any.
