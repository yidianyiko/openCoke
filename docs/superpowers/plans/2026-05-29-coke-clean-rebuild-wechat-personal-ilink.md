# Personal WeChat iLink Per-User Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Replace the personal-WeChat shared-bot pairing-code flow with per-account iLink bot sessions, QR login, account-bound inbound webhooks, and context-token outbound replies.

**Architecture:** The standalone `provider_edges/wechat_personal_connector` owns iLink protocol state keyed by Coke account/session: QR login, bot token, bot id, user wxid, `get_updates_buf`, and latest context tokens. Coke remains the product authority: `IdentityAccess` binds the confirmed wxid to the web account, `ChannelReachability` owns channel state and delivery attempts, `ConversationRuntime` persists inbound payloads including `context_token`, and the web page only renders QR/status returned by the API.

**Tech Stack:** Python Flask/httpx/dataclasses/SQLAlchemy metadata checks, existing in-memory fakes for unit tests, Next.js customer page and Vitest tests.

---

## Protocol Facts Used

- `GET /ilink/bot/get_bot_qrcode?bot_type=3` starts one bot login and returns `qrcode` plus `qrcode_img_content`.
- `GET /ilink/bot/get_qrcode_status?qrcode=...` returns `wait`, `scaned`, `confirmed`, or `expired`; `confirmed` returns `bot_token`, `ilink_bot_id`, `ilink_user_id`, and optional `baseurl`.
- Business POSTs use `Content-Type: application/json`, `AuthorizationType: ilink_bot_token`, `Authorization: Bearer <bot_token>`, per-request random base64 decimal uint32 `X-WECHAT-UIN`, and `base_info.channel_version`.
- `POST /ilink/bot/getupdates` is a long poll with `get_updates_buf`; every returned non-null cursor must be persisted and used on the next poll to avoid duplicate messages.
- `POST /ilink/bot/sendmessage` must send `message_type: 2`, `message_state: 2`, text item, unique `client_id`, target `to_user_id`, and the inbound `context_token`.

## Files

- Modify: `provider_edges/wechat_personal_connector/app.py` for multi-session state, QR login/status endpoints, account-bound polling, and context-token send.
- Modify: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py` for failing connector contract tests.
- Modify: `coke/domains/channel_reachability/models.py` for QR/status/context-token fields on normalized/status models.
- Modify: `coke/domains/channel_reachability/service.py` for account-bound personal-WeChat connect/status/inbound and context-token outbound.
- Modify: `coke/domains/identity_access/service.py` and models/protocols only as needed for explicit web-account channel binding without pairing.
- Modify: `coke/providers/wechat_personal.py` for connector start/status/send payloads and inbound normalization.
- Modify: `coke/api/channel_routes.py` and `coke/api/provider_webhooks.py` for QR fields and account-bound inbound payloads.
- Modify: `coke/composition.py`, `coke/config.py`, and maybe `coke/app.py` following existing optional-service/adapter patterns.
- Modify: `web/lib/customer-wechat-channel.ts`, `web/lib/customer-wechat-channel.test.ts`, `web/app/(customer)/channels/wechat-personal/page.tsx`, and its test for QR display/status polling.

## Task 1: Connector Multi-Session Protocol

- [x] **Step 1: Write failing connector tests**

Run after editing tests:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
```

Expected: failures because `/login/start` does not accept `account_id`, state is global, send lacks `context_token`, and poll webhooks lack `account_id`/`context_token`.

- [x] **Step 2: Implement connector state**

Add per-session records in the existing JSON state file:

```python
{
    "sessions": {
        "<session_id>": {
            "account_id": "acct_1",
            "status": "waiting_for_scan",
            "qrcode": "qr_1",
            "qrcode_image": "data:image/png;base64,...",
            "token": "...",
            "base_url": "https://ilinkai.weixin.qq.com",
            "ilink_bot_id": "...@im.bot",
            "ilink_user_id": "...@im.wechat",
            "cursor": "",
            "context_tokens": {"wxid": "ctx"}
        }
    }
}
```

- [x] **Step 3: Verify connector tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
```

Expected: all connector tests pass.

## Task 2: Coke Channel Contract

- [x] **Step 4: Write failing API/domain/provider tests**

Update tests for:

- `POST /api/channels/wechat-personal/connect` returns `session_id`, `qrcode_id`, and `qrcode_image`, not `pairing_code`.
- `GET /api/channels/wechat-personal/login-status?account_id=...&session_id=...` maps `wait/scaned/confirmed/expired` to user-visible states.
- `/webhooks/wechat/personal` accepts `account_id`, `session_id`, `wxid`, `message_id`, `text`, and `context_token`; it binds `wxid` to the named account and records payload context.
- outbound `send_text` sends `account_id`, `to`, `text`, and `context_token`.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v
```

Expected: focused failures for missing QR/status/context-token support.

- [x] **Step 5: Implement Coke wiring**

Use existing schema only:

- `channel_identity.provider_subject` stores the confirmed `ilink_user_id`/wxid.
- `message.payload.context_token` stores latest inbound context tokens.
- `delivery_route.provider_address` remains the wxid route target.

- [x] **Step 6: Verify domain/API tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v
```

Expected: all channel reachability tests pass.

## Task 3: Web QR Flow

- [x] **Step 7: Write failing web tests**

Update web tests so pending state renders the QR image and Chinese status copy, never a pairing code.

Run:

```bash
cd web && pnpm test -- app/\\(customer\\)/channels/wechat-personal/page.test.tsx lib/customer-wechat-channel.test.ts
```

Expected: failures for missing QR fields and stale pairing copy.

- [x] **Step 8: Implement web QR UI**

Map clean API fields to:

```ts
{
  status: 'pending',
  session_id: '...',
  qrcode_id: '...',
  qrcode_image: 'data:image/png;base64,...',
  instructions: '扫码连接微信'
}
```

- [x] **Step 9: Verify web tests pass**

Run:

```bash
cd web && pnpm test -- app/\\(customer\\)/channels/wechat-personal/page.test.tsx lib/customer-wechat-channel.test.ts
```

Expected: focused web tests pass.

## Task 4: Full Verification And Commit

- [x] **Step 10: Run full unit tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 11: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: verification suggestions are reviewed; risk report does not block commit.

- [x] **Step 12: Mark plan complete and commit**

Keep `Plan Status` open until deployment smoke is either completed or explicitly
reported blocked, then:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-ilink.md provider_edges/wechat_personal_connector/app.py tests/unit/coke/provider_edges/test_wechat_personal_connector.py coke web
git commit -m "feat: connect personal wechat with per-user ilink bots"
```

## Task 5: Deployment Smoke

- [x] **Step 13: Deploy non-disruptively if credentials/runtime access are available**

Follow `docs/deploy.md`, preserving `coke-clean/.env`, keeping `evolution-*` and web up, and restarting the connector service after image update.

- [x] **Step 14: Live QR smoke**

Use the API as `olivers@coke.keep4oforever.com` and a second account to call personal-WeChat connect. Confirm both return real iLink QR images and distinct session ids/QR ids. Do not fake scan confirmation.

Deployment and smoke evidence:

- Clean stack was redeployed on `gcp-coke:/home/whoami/coke-clean`; `.env` was preserved, `coke-web` stayed up, and `coke-api` reached healthy state.
- The standalone `wechat-personal-connector` compose project was redeployed on `gcp-coke:/home/whoami/wechat-personal-connector`, preserving its `.env` and Docker volume state.
- `olivers@coke.keep4oforever.com` login returned HTTP 200, but the account already had a connected `wechat_personal` channel, so the connect endpoint correctly returned `connected` instead of issuing a new QR.
- Live QR proof used the unconnected existing account `635d3bdc1b024a08acf49940b91a9de5` and a verified fresh smoke account `6d8b73a5a59d43e5bc670dc7ae5e1907`; both returned `connection_state=connecting`, `connector_status=waiting_for_scan`, display-ready `data:image/png;base64,...` QR images, and distinct session/QR ids. No human scan was performed.
