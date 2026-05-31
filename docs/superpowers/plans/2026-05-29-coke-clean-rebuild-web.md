# Coke Clean Rebuild: G-007 Route/Web Path Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix G-007 by exposing the missing canonical Python API route families and repointing the thin Next.js client away from stale route paths.

**Architecture:** Flask blueprints remain HTTP adapters over existing domain/service ports. Customer-scoped routes authenticate through `coke/api/auth_helpers.py`; internal routes use a shared static internal key and call injected runtime ports for delivery callbacks and reply pub/sub. The web client only calls canonical Python API route families from `docs/product-specs/FEATURE_TREE.md`.

**Tech Stack:** Flask blueprints, Python dataclass/service fakes in pytest, Next.js App Router client components, TypeScript helpers, Vitest/jsdom, pnpm.

---

Plan Status: complete

## File Structure

- Create: `coke/api/account_routes.py` - session-authenticated account identity, access status, and activation read routes over `IdentityAccessService`.
- Create: `coke/api/subscription_routes.py` - session-authenticated subscription/access status and checkout-link surfacing over `IdentityAccessService` account access reads.
- Create: `coke/api/internal_routes.py` - internal delivery callback and reply-wait routes over injected delivery-callback and reply-pubsub ports.
- Modify: `coke/api/claim_routes.py` - add the canonical `/api/claim/login-url/redeem` route so the web claim page uses `/api/claim/*`.
- Modify: `coke/app.py` - add optional service kwargs and additive blueprint registration for account, subscription, and internal routes.
- Create: `tests/unit/coke/identity_access/test_account_routes.py` - focused account route tests with fakes.
- Create: `tests/unit/coke/identity_access/test_subscription_routes.py` - focused subscription route tests with fakes.
- Create: `tests/unit/coke/test_internal_routes.py` - focused internal route tests with fakes.
- Modify: `tests/unit/coke/identity_access/test_auth_routes.py` - verify claim login-url route parity through the existing claim blueprint/app registration.
- Modify: `web/lib/customer-auth.ts` and `web/lib/customer-auth.test.ts` - repoint current-user/profile hydration to `/api/account/*`.
- Modify: `web/app/(customer)/account/subscription/page.tsx` and test - repoint status/checkout behavior to `/api/subscription/*`.
- Modify: `web/lib/customer-google-calendar-import.ts` - use `/api/account/access-status` for preflight and keep browser-only unavailable behavior until a real calendar auth start API exists.
- Modify: `web/app/(customer)/auth/claim/page.tsx` and test - call `/api/claim/login-url/redeem`.
- Modify: `docs/fitness/ownership-registry.yaml` - register ownership for the new API route files.
- Modify: this plan file - track TDD and verification status.

## Task 1: Backend Route Tests And Blueprints

- [x] **Step 1: Write failing backend route tests**

  Add tests asserting:

  ```python
  # tests/unit/coke/identity_access/test_account_routes.py
  client.get("/api/account/current-user", headers={"Authorization": "Bearer session_token"})
  client.get("/api/account/access-status", headers={"Authorization": "Bearer session_token"})
  client.get("/api/account/activation", headers={"Authorization": "Bearer session_token"})

  # tests/unit/coke/identity_access/test_subscription_routes.py
  client.get("/api/subscription/status", headers={"Authorization": "Bearer session_token"})
  client.post("/api/subscription/checkout-link", headers={"Authorization": "Bearer session_token"})

  # tests/unit/coke/test_internal_routes.py
  client.post("/internal/outbound/delivery-callback", headers={"Authorization": "Bearer internal-key"})
  client.get("/internal/reply-wait/inbound-1", headers={"Authorization": "Bearer internal-key"})
  ```

- [x] **Step 2: Run backend route tests and confirm RED**

  Run:

  ```bash
  /data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_account_routes.py tests/unit/coke/identity_access/test_subscription_routes.py tests/unit/coke/test_internal_routes.py -q
  ```

  Expected: tests fail with missing modules/routes.

- [x] **Step 3: Implement backend blueprints and app registration**

  Implement only these adapters:

  ```python
  app.register_blueprint(create_account_blueprint(identity_access_service))
  app.register_blueprint(create_subscription_blueprint(identity_access_service))
  app.register_blueprint(create_internal_blueprint(delivery_callback_service, reply_pubsub, internal_api_key))
  ```

  The route implementations call the injected services/ports directly, validate request shape, and return JSON. Do not add schema, fallback prose, or legacy aliases.

- [x] **Step 4: Run backend route tests and confirm GREEN**

  Run the same focused pytest command. Expected: all focused backend route tests pass.

## Task 2: Web Canonical Path Repointing

- [x] **Step 5: Write failing web path tests**

  Update tests to expect:

  ```ts
  customerApi.get('/api/account/current-user');
  customerApi.get('/api/account/access-status');
  customerApi.get('/api/subscription/status');
  customerApi.post('/api/subscription/checkout-link');
  customerApi.post('/api/claim/login-url/redeem', expect.any(Object));
  ```

- [x] **Step 6: Run focused web tests and confirm RED**

  Run:

  ```bash
  cd web && pnpm test -- --run web/lib/customer-auth.test.ts web/app/\(customer\)/account/subscription/page.test.tsx web/app/\(customer\)/auth/claim/page.test.tsx
  ```

  Expected: tests fail on the old `/api/auth/*` and `/api/auth/claim` calls.

- [x] **Step 7: Implement web path changes**

  Repoint the thin client to canonical paths, keep `customerApi` authorization behavior unchanged, and avoid moving business rules into web components.

- [x] **Step 8: Run focused web tests and confirm GREEN**

  Run the same focused web test command. Expected: all focused web tests pass.

## Task 3: Full Verification, Grep Proof, And Commit

- [x] **Step 9: Run required backend verification**

  Run:

  ```bash
  /data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
  ```

  Expected: all unit tests pass.

- [x] **Step 10: Run required web verification**

  Run:

  ```bash
  cd web && pnpm test
  cd web && pnpm build
  ```

  Expected: web tests and build pass.

- [x] **Step 11: Run grep-clean proof**

  Run:

  ```bash
  rg -n "/api/customer/subscription|/api/customer/google-calendar-import|/api/customer/agent-instance|/api/auth/claim|/api/auth/access-status|/api/auth/current-user" web
  ```

  Expected: no matches.

- [x] **Step 12: Run diff checks and commit**

  Run:

  ```bash
  git diff --check
  git add coke/api/account_routes.py coke/api/subscription_routes.py coke/api/internal_routes.py coke/api/claim_routes.py coke/app.py tests/unit/coke/identity_access/test_account_routes.py tests/unit/coke/identity_access/test_subscription_routes.py tests/unit/coke/test_internal_routes.py tests/unit/coke/identity_access/test_auth_routes.py web/lib/customer-auth.ts web/lib/customer-auth.test.ts web/app/\(customer\)/account/subscription/page.tsx web/app/\(customer\)/account/subscription/page.test.tsx web/lib/customer-google-calendar-import.ts web/app/\(customer\)/auth/claim/page.tsx web/app/\(customer\)/auth/claim/page.test.tsx docs/fitness/ownership-registry.yaml docs/superpowers/plans/2026-05-29-coke-clean-rebuild-web.md
  git commit -m "fix: align web with canonical api routes"
  ```

  Expected: one coherent commit on `fix/p1-routes`.

---

# Historical Note: Web Personal-WeChat QR Repair

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the live customer personal-WeChat connect page so a successful clean API connect response keeps the page on the QR scan screen, renders `qrcode_image`, and polls `login-status` by `account_id` + `session_id`.

**Architecture:** The web client remains a thin Next.js client over the Python API. The client maps the clean channel response shape into UI state, never invents backend channel state, never navigates away on connect/poll failures, and surfaces retry/refresh in place.

**Tech Stack:** Next.js App Router, React client components, TypeScript, Vitest/jsdom, pnpm, live HTTPS smoke via curl or Playwright when available.

---

Historical Status: in_progress (web fix deployed; live `login-status` poll is blocked by provider timeout)

## Current Repair Scope

- Modify: `web/lib/customer-wechat-channel.ts`
- Modify: `web/lib/customer-wechat-channel.test.ts`
- Modify: `web/app/(customer)/channels/wechat-personal/page.tsx`
- Modify: `web/app/(customer)/channels/wechat-personal/page.test.tsx`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-web.md`
- Deploy only the web build assets/service if the local fix verifies; keep `coke-clean`, `evolution-*`, connector services, and clean `.env` intact.

## Current Repair Steps

- [x] **Step 1: Diagnose the live and local client flow**

  Run these commands from the worktree root:

  ```bash
  git status --short
  rg -n "qrcode_image|session_id|connector_status|router\\.replace|login-status|wechat-personal" web/app web/lib
  cd web && pnpm test -- --run web/lib/customer-wechat-channel.test.ts web/app/\(customer\)/channels/wechat-personal/page.test.tsx
  ```

  Expected evidence: identify whether the page loses pending state because of response mapping, account/session lookup, polling, or navigation.

- [x] **Step 2: Write failing focused web tests**

  Add tests that use the exact live response fields:

  ```ts
  {
    account_id: 'acct_1',
    channel_id: null,
    connection_state: 'connecting',
    connector_status: 'waiting_for_scan',
    instructions: "scan this QR code with this user's own WeChat account",
    provider_type: 'wechat_personal',
    qrcode_id: 'qr_1',
    qrcode_image: 'data:image/png;base64,QR1',
    session_id: 'session_1',
  }
  ```

  The helper test must assert `qrcode_image` and `session_id` survive parsing. The page test must click the connect button, assert the QR `<img>` is rendered, assert `router.replace` was not called, and assert polling uses the pending `session_id`.

- [x] **Step 3: Run the focused tests and confirm they fail**

  Run:

  ```bash
  cd web && pnpm test -- --run web/lib/customer-wechat-channel.test.ts web/app/\(customer\)/channels/wechat-personal/page.test.tsx
  ```

  Expected: at least one new test fails for the current bug before production code changes.

- [x] **Step 4: Implement the minimal web fix**

  Update only the web channel client/page code needed to:

  ```ts
  // connect success
  setChannel({ status: 'pending', session_id, qrcode_image, connector_status, instructions });
  // poll
  getCustomerWechatChannelLoginStatus(session_id);
  // failures while pending
  preserve existing pending QR and show an in-place warning.
  ```

  Do not change the backend contract or add legacy/compatibility fields.

- [x] **Step 5: Verify local web and backend regression gates**

  Run:

  ```bash
  cd web && pnpm test
  cd web && pnpm build
  /data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
  ```

  Expected: all commands exit 0 with passing summaries.

- [x] **Step 6: Verify live data flow and browser behavior**

  Run the same API flow the page uses for `olivers`:

  ```bash
  curl -sS https://coke.keep4oforever.com/api/auth/login \
    -H 'Content-Type: application/json' \
    --data '{"email":"olivers@coke.keep4oforever.com","password_hash":"CokeTest-Olivers-2026!"}'
  curl -sS https://coke.keep4oforever.com/api/channels/wechat-personal/connect \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    --data '{"account_id":"ae02ff016fcd4d39a189e51c8c8a31e6"}'
  curl -sS "https://coke.keep4oforever.com/api/channels/wechat-personal/login-status?account_id=ae02ff016fcd4d39a189e51c8c8a31e6&session_id=$SESSION_ID" \
    -H "Authorization: Bearer $TOKEN"
  ```

  If Playwright/Chromium is available, log into the live page, click the connect action, and assert the QR `<img>` has a non-empty data URL and the URL remains `/channels/wechat-personal`. If browser tooling is unavailable, keep the component test as the UI proof and say so.

  Result: live connect returns HTTP 200 with non-empty `qrcode_image` and `session_id`; live Chromium/CDP clicked the connect action, stayed on `/channels/wechat-personal`, rendered a non-empty data-url QR image, and showed `waiting_for_scan`. The live `login-status` request returned HTTP 500; API logs show `httpx.ReadTimeout` in `coke/providers/wechat_personal.py` while polling the provider adapter. The web client preserves the QR in-place on poll errors, but the backend/provider timeout prevents proving a successful live poll in this run.

- [x] **Step 7: Commit, deploy, health-check, and cleanup test accounts**

  Run:

  ```bash
  git diff --check
  git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-web.md web/lib/customer-wechat-channel.ts web/lib/customer-wechat-channel.test.ts web/app/\(customer\)/channels/wechat-personal/page.tsx web/app/\(customer\)/channels/wechat-personal/page.test.tsx
  git commit -m "fix: keep wechat QR connect page pending"
  ```

  Deploy non-disruptively using `docs/deploy.md`, confirm:

  ```bash
  curl -sS -o /dev/null -w '%{http_code}\n' https://coke.keep4oforever.com/auth/login
  ```

  Then reset `olivers` (`ae02ff016fcd4d39a189e51c8c8a31e6`) and `lizihao` (`635d3bdc1b024a08acf49940b91a9de5`) personal-WeChat channels to `not_connected` and remove sessions/channels created during testing.

- [ ] **Step 8: Close the plan**

  After verification and cleanup pass, mark every current repair checkbox complete and set `Plan Status: complete`.

  Not complete yet: the web repair is deployed and verified, but the required live `login-status` poll proof did not pass because the API timed out while calling the provider adapter.

---

# Prior Completed Plan: Web + Personal WeChat Pairing

Prior Plan Status: complete

## Goal

Make the live Coke web app usable for a two-account personal-WeChat test on
gcp-coke by restoring the web service, wiring web-first personal-WeChat pairing
codes through the clean API and connector webhook path, provisioning two
verified test accounts, deploying non-disruptively, and verifying the live
flows.

## Constraints

- Build only on `coke/schema.py`; do not add or fork schema.
- Do not add compatibility shims, legacy imports, fallback prose, keyword
  routing, or auto-provisioning for `wechat_personal`.
- Keep backend ownership boundaries:
  - `IdentityAccess` owns `auth_artifact` and `channel_identity`.
  - `ChannelReachability` owns `channel`, route status, provider connect state.
  - Web is a thin client over the Python API.
- Only shared runtime file edit allowed outside owned surfaces is `coke/app.py`
  if a blueprint registration change is required.
- Use `/data/projects/coke/.venv/bin/python` and run pytest from repository
  root.
- Commit small coherent changes on the current branch; do not push.

## Steps

- [x] Confirm current service/deploy failure shape from local compose/deploy
      files and live `gcp-coke` process state without printing secrets.
- [x] Write failing backend tests for web-first personal-WeChat connect:
      - channel connect route issues or reuses a pending `pairing_code`;
      - channel status surfaces pending `pairing_code`, expiry, and
        instructions;
      - inbound `/webhooks/wechat/personal` accepts connector payloads with
        `pairing_code` and passes them to channel reachability;
      - reachability binds an unbound `wxid` only when a valid code is present
        and rejects unbound messages without a valid code.
- [x] Run the new backend tests and capture the expected failures.
- [x] Implement backend pairing support:
      - add identity-access lookup/ensure methods for unconsumed
        `pairing_code` artifacts;
      - add reachability service pending-connect behavior for
        `wechat_personal`;
      - expose a clean API route for `POST
        /api/channels/wechat-personal/connect`;
      - include pending pairing fields in channel status responses.
- [x] Run the backend tests again and keep the relevant unit suite green.
- [x] Write failing web tests for the clean auth/channel API contract and the
      channels page pairing-code display.
- [x] Implement web thin-client changes:
      - map login/register/profile to the clean Python auth API;
      - map the WeChat channel helpers to the clean channel status/connect
        API;
      - display pairing code, expiry/state, and instructions instead of a QR
        code for personal-WeChat pairing.
- [x] Run web tests/build for the touched web surfaces.
- [x] Fix deployment stability:
      - remove `coke-web` profile gating from the clean compose service;
      - remove deploy-script behavior that deletes `coke-web`;
      - preserve existing clean `.env` values while adding required web/API
        public URLs;
      - include web health evidence in deploy verification.
- [x] Run diff-aware repository verification and the broad unit command:
      - `zsh scripts/suggest-verification --base HEAD~1`;
      - `zsh scripts/review-trigger --base HEAD~1`;
      - `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`.
- [x] Commit verified local code/docs/test changes.
- [x] Deploy non-disruptively to `gcp-coke` while preserving `.env`,
      connector, and Evolution services.
- [x] Provision verified active test accounts for:
      - `olivers`;
      - `lizihao`.
- [x] Verify live behavior:
      - `/healthz` returns 200;
      - `http://127.0.0.1:4042/auth/login` returns 200 on the host;
      - `https://coke.keep4oforever.com/auth/login` returns 200 through nginx;
      - both test accounts can log in through `/api/auth/login`;
      - connect issues a real pairing code;
      - simulated connector POST to `/webhooks/wechat/personal` binds a test
        `wxid` to the correct account and connects the channel;
      - follow-up message creates the expected conversation/turn/reminder
        evidence, or record the exact blocker if the runtime cannot complete
        reminder creation.
- [x] Update this plan with completed checkboxes and set Plan Status to
      `complete` only after verification passes.

## Verification Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
cd web && pnpm test
cd web && pnpm build
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

## Live Smoke Commands

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4042/auth/login
curl -sS -o /dev/null -w '%{http_code}\n' https://coke.keep4oforever.com/auth/login
curl -sS https://coke.keep4oforever.com/healthz
```
