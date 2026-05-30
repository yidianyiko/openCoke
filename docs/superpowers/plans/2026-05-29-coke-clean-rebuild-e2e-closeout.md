# Coke Clean Rebuild E2E Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Destructively retire the old `coke` production stack on `gcp-coke`, promote `coke-clean` as the primary public stack, reset the clean database for go-live, and run a personal-WeChat web-first end-to-end check with honest connector evidence.

**Architecture:** Treat this as an operational cutover, not a migration: preserve the Evolution provider stack, preserve `coke-clean`, delete only the old `coke` project and its data, and move nginx product traffic to clean API/web ports. Personal WeChat remains a provider adapter behind the clean ingress/egress tier; if the old bridge is the only live connector, the webhook test must be simulation-only and outbound delivery must be reported as blocked by missing connector configuration.

**Tech Stack:** Docker Compose on `gcp-coke`, nginx, Postgres 17, Redis 7.2, Flask/Gunicorn clean API, Next.js web client, pytest.

**Plan Status:** complete

**Verification Evidence:**
- Remote old-stack teardown: `docker compose -p coke down -v --remove-orphans`; final `docker ps` showed only `coke-clean-*` and `evolution-*`.
- Remote nginx cutover: backed up `/etc/nginx/sites-available/coke` to `/etc/nginx/sites-available/coke.before-clean-cutover-20260530T095312Z`; `nginx -t` passed and nginx reloaded.
- Remote clean DB reset: dropped/recreated `coke`, ran `coke-migrate`; post-reset database had 29 public tables and zero product rows before E2E.
- Remote health: clean API `/healthz` returned `{"ok":true}`; public `https://coke.keep4oforever.com/` and `/healthz` returned HTTP 200.
- Remote personal-WeChat simulation: `/api/auth/register`, email verification, pairing-code webhook, and reminder webhook all accepted under one web-first account; reminder row created; outbound delivery failed with `provider_not_configured`.
- Local web build: `cd web && pnpm build` passed.
- Local unit suite: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` — `380 passed`.
- Local diff check: `git diff --check` passed with no output.

---

### Task 1: Provider Connector Investigation

**Files:**
- Read: `coke/providers/wechat_personal.py`
- Read: `coke/config.py`
- Read: `coke/composition.py`
- Read: remote `/home/whoami/coke/.env*`
- Read: remote `/home/whoami/coke-clean/.env*`

- [x] **Step 1: Read the canonical personal-WeChat contract**

Confirm from the requirements and target architecture specs that `wechat_personal` is web-first, connection-first, and not a messaging-first auto-provisioning channel.

- [x] **Step 2: Read the clean adapter and environment mapping**

Confirm `WeChatPersonalAdapter` normalizes inbound from `wxid`, `text`, `message_id`, optional `pairing_code`, and sends outbound to `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL` with optional `COKE_PROVIDER_WECHAT_PERSONAL_API_KEY`.

- [x] **Step 3: Inspect live old and clean environment**

On `gcp-coke`, compare old `.env*` ClawScale/eCloud/character variables with clean `.env*` `COKE_PROVIDER_WECHAT_PERSONAL_*` variables.

- [x] **Step 4: Record the connector finding**

If no clean `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL` exists and the old bridge is the only ClawScale-shaped connector, record that deleting the old bridge removes live personal-WeChat connectivity and that Part 3 must use webhook-simulation mode.

### Task 2: Destructive Old Stack Teardown

**Files:**
- Remote delete: `/home/whoami/coke`
- Remote delete: old `/home/whoami/.env*.bak` matching the old stack, if present

- [x] **Step 1: Capture pre-teardown container evidence**

Run:

```bash
ssh gcp-coke 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

Expected: both `coke-clean-*` and old `coke-*` containers are visible, plus `evolution-*`.

- [x] **Step 2: Stop and remove old compose project with volumes**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke && docker compose -p coke down -v --remove-orphans'
```

Expected: old `coke` containers and old compose volumes are removed.

- [x] **Step 3: Force-remove lingering old containers**

Run:

```bash
ssh gcp-coke 'docker rm -f coke-coke-agent-1 coke-coke-bridge-1 coke-gateway-1 coke-mongo-1 coke-postgres-1 coke-redis-1 2>/dev/null || true'
```

Expected: no old containers remain.

- [x] **Step 4: Delete old code/data/logs and backup env files**

Run:

```bash
ssh gcp-coke 'rm -rf /home/whoami/coke /home/whoami/coke/.env*.bak /home/whoami/.env*.bak'
```

Expected: `/home/whoami/coke` no longer exists.

- [x] **Step 5: Confirm only clean and Evolution containers remain**

Run:

```bash
ssh gcp-coke 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

Expected: only `coke-clean-*` and `evolution-*` remain.

### Task 3: Promote Clean Stack And Reset Database

**Files:**
- Remote modify: `/etc/nginx/sites-available/coke`
- Remote build/run: `/home/whoami/coke-clean/web`
- Remote database: `coke-clean-postgres-1` database `coke`

- [x] **Step 1: Start clean web profile**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml --profile web up -d --build coke-web'
```

Expected: `coke-clean-coke-web-1` is running on `127.0.0.1:4042`, or build failure is captured and API-only status is reported.

- [x] **Step 2: Back up nginx site**

Run:

```bash
ssh gcp-coke 'sudo cp /etc/nginx/sites-available/coke /etc/nginx/sites-available/coke.before-clean-cutover-$(date -u +%Y%m%dT%H%M%SZ)'
```

Expected: backup file exists.

- [x] **Step 3: Route product traffic to clean API and clean web**

Update nginx so `/` proxies to `127.0.0.1:4042`, `/api/` proxies to `127.0.0.1:8000`, provider webhooks proxy to `127.0.0.1:8000`, dead old `/bridge/`, `/user/`, `/bind/`, `/gateway/`, `/auth`, `/health`, old `/api/ -> 4041`, and old `/ -> 4040` routes are removed, and `/evolution-api/ -> 8081` stays.

- [x] **Step 4: Validate and reload nginx**

Run:

```bash
ssh gcp-coke 'sudo nginx -t && sudo systemctl reload nginx'
```

Expected: syntax ok and reload succeeds.

- [x] **Step 5: Reset clean database and rerun migrations**

Run:

```bash
ssh gcp-coke 'docker exec coke-clean-postgres-1 psql -U coke -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''coke'\'' AND pid <> pg_backend_pid();" -c "DROP DATABASE IF EXISTS coke;" -c "CREATE DATABASE coke OWNER coke;" && cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate'
```

Expected: migrated clean database, 28 or more tables, zero product rows.

- [x] **Step 6: Restart clean runtime after DB reset**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml --profile web up -d coke-api coke-worker coke-scheduler coke-outbox-relay coke-web'
```

Expected: API, worker, scheduler, outbox relay, and web are running.

- [x] **Step 7: Health-check clean production**

Run:

```bash
ssh gcp-coke 'curl -fsS http://127.0.0.1:8000/healthz && curl -k -I https://coke.keep4oforever.com/'
```

Expected: API health is 200 and public site responds from clean web, or web deferral is recorded.

### Task 4: Personal-WeChat Web-First E2E

**Files:**
- Read: `coke/api/channel_routes.py`
- Read: `coke/api/provider_webhooks.py`
- Remote database: `coke-clean-postgres-1` database `coke`

- [x] **Step 1: Create or authenticate a web-first account**

Use clean `/api/auth/*` if the routes are available. If auth APIs are not exposed for this production slice, create the minimum web-first account rows through the clean schema and report that this is a direct DB setup path, not a public auth-route pass.

- [x] **Step 2: Connect a `wechat_personal` channel**

Use `/api/channels` with an existing web-first `channel_identity_id`, then `/api/channels/<id>/connect`. If the API cannot bind the identity without a real connector or auth path, report the exact failed call and reason; do not fake a live connector.

- [x] **Step 3: Simulate inbound webhook**

POST to `/webhooks/wechat/personal` with:

```json
{
  "wxid": "<bound-wechat-identity>",
  "message_id": "<unique-message-id>",
  "text": "提醒我明天早上9点跑步"
}
```

Expected: accepted as the existing web-first account, not auto-provisioned.

- [x] **Step 4: Verify database rows**

Query `account`, `channel_identity`, `channel`, `delivery_route`, `conversation`, `message`, `turn`, `reminder`, `delivery_attempt`, and `outbox` as applicable. Paste rows that prove account association, inbound message recording, reminder creation if the worker path completes, and outbound delivery status.

- [x] **Step 5: Classify outbound delivery**

If `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL` remains unset, record outbound delivery as blocked by missing connector configuration rather than delivered.

### Task 5: Local Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md`

- [x] **Step 1: Run local unit verification**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all tests pass.

- [x] **Step 2: Mark this plan complete**

Set `Plan Status` to `complete` only after remote cutover checks and local pytest pass, then check off completed steps.

- [x] **Step 3: Commit the plan and any code fixes**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md
git commit -m "ops: record clean production cutover closeout"
```
