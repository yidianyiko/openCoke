---
kind: active_issue
status: open
surface:
  - identity-access
  - api
  - web
  - security
github_issue:
github_state:
github_url:
created_at: 2026-05-31
updated_at: 2026-05-31
---

# 2026-05-31 Quality Security Audit

## What Happened

The clean-rebuild API had two confirmed P0 security defects:

- P0 fixed: Web auth sent a raw password in the legacy `password_hash` field, and IdentityAccess stored/compared that value directly. The contract now accepts `password`, hashes it server-side with Argon2, and verifies the raw password on login/reset paths. Evidence: `web/lib/customer-auth.ts:198`, `coke/api/auth_routes.py:22`, `coke/domains/identity_access/service.py:70`, `coke/domains/identity_access/service.py:92`, `coke/domains/identity_access/service.py:424`, `coke/domains/identity_access/passwords.py:11`.
- P0 fixed: Customer-scoped routes trusted client-supplied account ids in request bodies or query strings. They now require `Authorization: Bearer <session_token>`, resolve the acting account through IdentityAccess, and pass that account id to customer domain services. Evidence: `coke/api/auth_helpers.py:8`, `coke/api/channel_routes.py:12`, `coke/api/reminder_routes.py:18`, `coke/api/friend_routes.py:16`, `coke/api/shared_reminder_routes.py:25`, `coke/api/calendar_import_routes.py:25`, `coke/api/claim_routes.py:85`, `coke/app.py:51`.

## Why It Matters

Plaintext credential storage makes password compromise equivalent to database compromise. Client-selected account ids let any caller act as another account across channel setup, reminders, friends, shared reminders, calendar import, access status, and pairing-code issuance.

## Affected Surfaces

- `identity-access`
- `api`
- `web`
- `channel-reachability`
- `reminder`
- `social-scheduling`
- `calendar-import`

## Prioritized Findings

- P0 fixed: Passwords were effectively plaintext. Fixed in `f07724c3` by adding `argon2-cffi`, hashing in IdentityAccess on register/reset, verifying on login, and changing the web/API contract from `password_hash` to `password`.
- P0 fixed: Customer routes trusted request ownership. Fixed in `f07724c3` by adding a shared bearer-session resolver and using it on customer channel, reminder, friend, shared-reminder, calendar-import, access-status, and pairing-code issuance routes.
- P1 remains: Provider webhook routes have no visible source authentication or signature verification before normalizing inbound payloads. `coke/api/provider_webhooks.py:43` selects the adapter and `coke/api/provider_webhooks.py:56` normalizes request JSON without a route-level shared-secret/signature gate. I did not fix this because the current provider adapter contract and schema do not define per-provider webhook credentials beyond outbound provider tokens.
- P2 remains: Some domain error details can still expose raw exception strings to API-visible facts or item results. Examples: `coke/domains/identity_access/service.py:193` to `coke/domains/identity_access/service.py:200` includes `str(error)` in a write-conflict fact; `coke/domains/reminder/service.py:63` to `coke/domains/reminder/service.py:66` returns `str(error)` for `ValueError` batch item failures.
- P2 remains: Web channel helpers still send redundant client account ids to channel endpoints. The server ignores those ids after `f07724c3`, so this is no longer an authz bypass, but the client contract is stale. Evidence: `web/lib/customer-wechat-channel.ts:224`, `web/lib/customer-wechat-channel.ts:237`, `web/lib/customer-wechat-channel.ts:251`, `web/lib/customer-wechat-channel.ts:270`. I did not edit this file because the task guardrail said another worker is editing web channel surfaces.

## Evidence

- TDD RED, password service: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_identity_access_service.py -v` failed with `38 failed, 12 passed` before implementation.
- TDD RED, auth routes: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_auth_routes.py -v` failed with `6 failed, 15 passed` before implementation.
- TDD RED, customer routes: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_channel_routes.py tests/unit/coke/reminder/test_reminder_routes.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/calendar_import/test_calendar_import_routes.py tests/unit/coke/identity_access/test_auth_routes.py -v` failed with `39 failed, 20 passed` before implementation.
- Focused GREEN, customer auth routes: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_channel_routes.py tests/unit/coke/reminder/test_reminder_routes.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/calendar_import/test_calendar_import_routes.py tests/unit/coke/identity_access/test_auth_routes.py -v` passed with `59 passed`.
- Full unit GREEN: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed with `422 passed`.
- Web GREEN: `cd web && pnpm test -- customer-auth.test.ts` passed with `51 passed` test files and `210 passed` tests.
- Suggested surface GREEN: `zsh scripts/verify-surface clean-rebuild-backend clean-rebuild-web repo-os-docs` passed `422 passed`, `51 passed` test files and `210 passed` tests, `pnpm build`, and `scripts/check`.

## Current Status

- Fixed in branch: password hashing and customer route session authorization.
- Open for leader: provider webhook source authentication contract, raw exception-string exposure cleanup, and stale web channel client request cleanup.

## Resolution

- Security fix commit: `f07724c3 fix: secure customer auth boundary`.
- Final audit closeout commit: this docs closeout commit.
