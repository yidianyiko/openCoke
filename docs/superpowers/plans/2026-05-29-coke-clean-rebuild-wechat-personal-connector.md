# WeChat Personal Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Stand up a standalone personal-WeChat connector edge for `wechat_personal` so the clean Coke stack can send and receive real WeChat messages when the human-owned WeChat session is logged in.

**Architecture:** Coke keeps `wechat_personal` as a provider adapter behind the canonical provider contract. The connector is a peer provider-edge service, outside Coke's app stack and outside Evolution, whose outbound HTTP endpoint matches `WeChatPersonalAdapter.send_text()` and whose inbound webhook posts the clean payload accepted by `/webhooks/wechat/personal`.

**Tech Stack:** Python Flask clean Coke API, `httpx`, SQLAlchemy schema metadata, Docker/Compose on `gcp-coke`, and the reachable ClawScale connector if it can be cloned and run without resurrecting legacy Coke bridge/gateway/app code.

---

### Task 1: Confirm The Clean WeChat Contract

**Files:**
- Read: `coke/providers/wechat_personal.py`
- Read: `coke/config.py`
- Read: `coke/composition.py`
- Read: `coke/api/provider_webhooks.py`
- Read: `coke/schema.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-connector.md`

- [x] **Step 1: Record outbound contract**

Confirm from `WeChatPersonalAdapter.send_text()`:

```text
POST <COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL>
Headers:
  Idempotency-Key: <provider idempotency key>
  Authorization: Bearer <COKE_PROVIDER_WECHAT_PERSONAL_API_KEY>   # only when configured
  X-API-Key: <COKE_PROVIDER_WECHAT_PERSONAL_API_KEY>              # only when configured
JSON:
  {"to": "<delivery_route.provider_address>", "text": "<visible text>"}
```

- [x] **Step 2: Record inbound contract**

Confirm from `WeChatPersonalAdapter.normalize_inbound()` and `provider_webhooks.py`:

```text
POST /webhooks/wechat/personal
Content-Type: application/json
Body:
  {
    "message_id": "<connector-stable message id>",
    "wxid": "<sender wxid>",
    "text": "<message text, blank allowed>",
    "pairing_code": "<optional web-first channel pairing code>"
  }
Response:
  202 with accepted/account/channel identity facts, or 400 with structured error.
```

- [x] **Step 3: Confirm schema boundary**

Verify the work maps only to existing `channel_identity`, `channel`, `delivery_route`, `message`, `turn`, and `delivery_attempt` tables in `coke/schema.py`. If a missing table or column is found, stop and report the schema gap instead of redefining schema.

### Task 2: Investigate ClawScale Connector Feasibility

**Files:**
- Read remote metadata: `https://github.com/yidianyiko/ClawScale.git`
- Optional local scratch: `/tmp/clawscale-investigate`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-connector.md`

- [x] **Step 1: Check remote reachability with a hard timeout**

Run:

```bash
timeout 20 git ls-remote https://github.com/yidianyiko/ClawScale.git HEAD
```

Observed: reachable, `d0cdf9bbaebba3d3361f06daafc31122016a06cb HEAD`.

- [x] **Step 2: If reachable, clone shallowly into scratch**

Run:

```bash
rm -rf /tmp/clawscale-investigate
timeout 60 git clone --depth 1 https://github.com/yidianyiko/ClawScale.git /tmp/clawscale-investigate
```

Observed: scratch clone succeeded in `/tmp/clawscale-investigate`.

- [x] **Step 3: Inspect runtime and API shape**

Read only the connector's top-level README, Docker/Compose files, environment examples, and route definitions. Identify whether it is a personal-WeChat login/session automation service, how it exposes QR login, the send-message route, inbound webhook configuration, and required secrets.

Observed: ClawScale is the old TypeScript gateway/customer platform, not a standalone clean connector. The reusable part is Tencent iLink protocol handling: QR login via `/ilink/bot/get_bot_qrcode`, QR polling via `/ilink/bot/get_qrcode_status`, outbound send via `/ilink/bot/sendmessage`, and inbound polling via `/ilink/bot/getupdates`.

- [x] **Step 4: Identify human-only login step**

Record the exact QR login surface or command. The agent cannot scan a QR code or create a real WeChat session; the user must scan it with the target WeChat phone account.

Observed: the human step is scanning the iLink QR returned by connector `/login/status` after `/login/start`.

### Task 3: Add Contract Tests Only If The Clean Adapter Has A Gap

**Files:**
- Test: `tests/unit/coke/channel_reachability/test_provider_adapters.py`
- Test: `tests/unit/coke/channel_reachability/test_provider_webhooks.py`
- Modify only if needed: `coke/providers/wechat_personal.py`
- Modify only if needed: `coke/api/provider_webhooks.py`

- [x] **Step 1: Write failing adapter/webhook test for the discovered connector shape**

If ClawScale emits or expects fields that can be normalized without violating the canonical contract, add one focused failing test showing the desired mapping.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py tests/unit/coke/channel_reachability/test_provider_webhooks.py -v
```

Observed: no clean adapter gap was found. Added failing tests for the new standalone provider-edge connector instead: send contract, auth, iLink inbound-to-clean webhook forwarding, and pairing-code forwarding.

- [x] **Step 2: Implement the minimal adapter mapping**

Change only the adapter or webhook normalization edge. Do not add legacy imports, connector code, fallback prose, keyword routing, schema forks, or domain behavior.

Observed: no Coke adapter/webhook change was needed. Implemented the standalone provider-edge connector outside the Coke runtime domains.

- [x] **Step 3: Verify the focused tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py tests/unit/coke/channel_reachability/test_provider_webhooks.py -v
```

Observed: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v` passed, `4 passed`.

### Task 4: Wire The Standalone Connector On gcp-coke If Feasible

**Files:**
- Remote inspect: `/home/whoami/coke-clean/.env`
- Remote inspect: possible env backups under `/home/whoami/`
- Remote create/modify only for connector service files outside Coke clean app stack
- Remote modify only if connector endpoint is known: `/home/whoami/coke-clean/.env`

- [x] **Step 1: Inspect live clean runtime before changes**

Use SSH to inspect the current `gcp-coke` containers, `/home/whoami/coke-clean/.env`, compose files, and exposed API URL. Do not touch `evolution-*`, DB data, or legacy app resurrection paths.

Observed: clean Coke API/worker/scheduler/outbox, Postgres, Redis, and Evolution containers were running. Only the clean API/worker were recreated after env wiring. Evolution containers and DB data were not changed destructively.

- [x] **Step 2: Locate or report missing WeChat secrets**

Check for surviving WeChat connector secrets in clean env or backups. Required names are whatever ClawScale's inspected runtime requires; the old known candidates are `CLAWSCALE_IDENTITY_API_KEY`, `CLAWSCALE_OUTBOUND_API_KEY`, `CLAWSCALE_WECHAT_CHANNEL_API_KEY`, `CHARACTER_WXID_*`, and `ECLOUD_*`. If needed secrets are gone, stop deployment and report the exact missing keys.

Observed: no surviving old WeChat/ClawScale secrets were found. The selected Tencent iLink connector path does not require those old keys; it needs a connector-local API key plus human QR login. A connector-local API key was generated in `/home/whoami/wechat-personal-connector/.env`.

- [x] **Step 3: Deploy connector as a standalone provider-edge service**

If runtime, secrets, and host access are sufficient, run the connector in its own container/compose project. Configure outbound send endpoint authentication and inbound webhook target to the clean Coke route:

```text
https://<clean-coke-api-host>/webhooks/wechat/personal
```

Observed: deployed standalone compose project `wechat-personal-connector` under `/home/whoami/wechat-personal-connector`, with inbound webhook target `http://host.docker.internal:8000/webhooks/wechat/personal`.

- [x] **Step 4: Configure clean Coke for connector outbound**

Set:

```env
COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL=<connector send endpoint>
COKE_PROVIDER_WECHAT_PERSONAL_API_KEY=<connector API key if required>
```

Recreate only the clean Coke API/worker containers needed to pick up env. Do not rebuild legacy app/gateway/bridge.

Observed: `/home/whoami/coke-clean/.env` now sets `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL=http://host.docker.internal:8095/send` and the generated connector API key. Recreated clean Coke API/worker only.

- [x] **Step 5: Surface QR login**

Bring the connector to the waiting-for-login state and record the exact URL, command output, or file path that shows the QR code for the user to scan.

Observed: connector is in `waiting_for_scan`. QR image exists at `/home/whoami/wechat-personal-connector/wechat-login-qr.png` on `gcp-coke` and was copied locally to `/tmp/wechat-login-qr.png`.

### Task 5: Verify What Can Be Verified Without Human QR Scan

**Files:**
- Test: `tests/unit/coke/channel_reachability/`
- Remote smoke: clean API container and connector container
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-connector.md`

- [x] **Step 1: Run focused repo tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v
```

Expected: all channel reachability tests pass.

Observed: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v` passed, `110 passed`.

- [x] **Step 2: Run full Coke unit tests if repo code changed**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

Observed: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed, `386 passed`.

- [x] **Step 3: Verify connector reachability from clean API container**

From the clean Coke API container, issue a non-destructive HTTP check against the connector send endpoint. Record the HTTP status and body. An auth/validation error still proves network reachability if it comes from the connector.

Observed: from `coke-clean-coke-api-1`, authenticated `POST http://host.docker.internal:8095/send` returned `409 {"error":"wechat_not_connected"}`, proving network/auth/payload wiring before human login.

- [x] **Step 4: Verify inbound route accepts the connector shape**

Post a synthetic JSON payload matching the clean contract to `/webhooks/wechat/personal` in a non-destructive test environment or with a known safe test identity. If live DB side effects would create a real account/channel unexpectedly, use local/unit verification instead and report that live inbound was intentionally not posted.

Observed: live synthetic invalid-pairing payload reached `/webhooks/wechat/personal` and failed closed with `400 {"error":{"code":"artifact_not_found"}}`. Positive 202 inbound requires a valid pairing code or existing bound WeChat identity; connector unit tests verified the exact accepted clean payload mapping without creating live state.

- [x] **Step 5: Record human handoff**

Document the exact human step:

```text
1. Open/scan the connector QR code with the intended personal WeChat account.
2. After login succeeds, send this WeChat message to Coke: 提醒我明天早上9点跑步
3. Verify clean DB receipt with a psql query against message/channel_identity rows.
```

- [x] **Step 6: Mark plan complete only after verification**

Set `Plan Status: complete` only after all feasible repo tests and runtime smoke checks have been run and read. If deployment is blocked by network, secrets, SSH, or QR scan, leave status as `blocked` and record the blocker.

Observed: all feasible repo and runtime smoke checks passed. Full live WeChat send/receive remains a human-only follow-up after the QR scan.
