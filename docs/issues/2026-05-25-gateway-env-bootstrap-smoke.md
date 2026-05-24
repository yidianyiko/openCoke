---
title: Gateway env bootstrap breaks live shared-reminder smoke
kind: incident
date: 2026-05-25
status: fix_implemented_runtime_restart_needed
affected_surfaces:
  - gateway/packages/api/src/index.ts
  - gateway/packages/api/src/lib/reminder-runtime-client.ts
  - gateway/packages/api/src/scheduling/user-link-service.ts
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t164146Z.json
---

# Gateway env bootstrap breaks live shared-reminder smoke

## What happened

Smoke batch `20260524t164146Z` diverged in two places:

- Alice asked for her friend invitation link and the assistant returned
  `日程操作暂时无法完成。`. Direct gateway fallback to
  `/api/internal/scheduling/tools/get_user_link` failed with
  `DOMAIN_CLIENT is required`, even though Postgres showed an active
  `user_links` row for Alice.
- Alice created a shared reminder for Bob. The assistant again returned
  `日程操作暂时无法完成。`; Postgres showed the shared reminder request was
  created and immediately marked `cancelled` instead of remaining
  `pending_invitee_confirmation`.

## Why it matters

The live local stack health checks pass on ports `8090` and `4041`, but core
scheduling tools still fail because the gateway process does not have the env
needed to build public user-link URLs or authenticate to bridge internal
reminder routes. That makes a healthy-looking stack fail the user-path smoke.

## Evidence

- Gateway process cwd: `/data/projects/coke/gateway/packages/api`.
- Live gateway env contains `DATABASE_URL` and `CLAWSCALE_IDENTITY_API_KEY`,
  but not `DOMAIN_CLIENT` or `COKE_BRIDGE_API_KEY`.
- `POST /bridge/internal/reminders` without the bridge bearer returns `401`;
  with the repo root `.env` `COKE_BRIDGE_API_KEY`, the same bridge route
  succeeds.
- Phase 3 DB state:
  `shared_reminder_requests.status = cancelled`,
  `requester_reminder_id = null`, `invitee_reminder_id = null`.

## Current status

Root cause identified. The gateway package loads `dotenv/config` from its own
cwd, so local runs from `gateway/packages/api` miss the repository root `.env`.

## Fix

Implemented a gateway env bootstrap that loads `.env` from the package cwd,
`gateway/.env`, and the repository root without overriding explicit process
environment values. The API entrypoint imports this bootstrap before route
modules initialize.

Gateway fix commit: `74336cd`.

## Verification

- `pnpm --dir gateway --filter @clawscale/api test src/lib/gateway-env.test.ts`
  first failed because the bootstrap helper did not exist.
- `pnpm --dir gateway --filter @clawscale/api test src/lib/gateway-env.test.ts src/lib/reminder-runtime-client.test.ts src/scheduling/user-link-service.test.ts`
  passed after the fix.
- `pnpm --dir gateway --filter @clawscale/api build` passed.
- `git diff --check` passed.
- `pm2 restart coke-agent && sleep 4` passed.

Live smoke verification is blocked because the current gateway process is not
watch-reloading this code change, and the smoke rules do not authorize a
manual gateway restart. After gateway is restarted, rerun Phase 3 or a fresh
full batch to confirm `get_user_link` returns a public URL and
`create_shared_reminder` leaves the request pending instead of cancelled.
