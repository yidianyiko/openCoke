---
kind: active_issue
status: open
surface:
  - production-smoke
  - repo-os
severity: P2
created_at: 2026-06-09
updated_at: 2026-06-09
---

# 2026-06-09 P2: Clean Smoke Friend Phase Uses Retired Unauthenticated Route Shape

## What Happened

The production clean smoke rerun `latency_fix_20260609T071153Z` progressed past
first-contact and personal-reminder verification, then failed at the friendship
phase:

```
HTTP 401 from http://127.0.0.1:8000/api/friends/link?owner_account_id=...
{"error":{"code":"unauthorized","fact":{"reason":"missing_bearer_token","type":"unauthorized"}}}
```

## Why It Matters

The smoke harness is supposed to verify the deployed clean stack with real
account identities. It currently cannot exercise the friend/shared-reminder
phases through the product API because those routes now require a bearer session
token.

The failure also prevented the harness from writing a JSON evidence transcript
for this failed run; the outer `SmokeVerdictError` path printed JSON to stdout
but did not persist `artifacts/evidence/clean-smoke/<run-id>.json`.

## Affected Surfaces

- `production-smoke`
- `repo-os`

## Evidence

- Command: `python -m scripts.smoke.clean_smoke --mode webhook --run-id
  latency_fix_20260609T071153Z` inside the production `coke-api` container.
- Failure: `/api/friends/link` returned `401 missing_bearer_token`.
- Current route contract: `coke/api/friend_routes.py` calls
  `require_customer_account_id(...)`; `coke/api/auth_helpers.py` requires
  `Authorization: Bearer <session_token>`.
- Existing route tests explicitly reject missing sessions:
  `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`.
- Current harness code still calls `/api/friends/link?owner_account_id=...` and
  `/api/friends/join` with body account IDs but without authorization.

## Current Status

- Open.
- Not a blocker for the transaction-pinning fix; the repeated smoke had already
  verified the personal-reminder path before this later phase failed.

## Resolution

Pending. The harness should either mint/use real session tokens for the smoke
accounts or switch the friend phase to a product-supported public friend-link
flow. Its outer error path should also persist the transcript before returning
failure.
