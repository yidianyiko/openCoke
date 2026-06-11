---
kind: active_issue
status: resolved
surface:
  - identity-access
  - customer-web
  - production
created_at: 2026-06-11
updated_at: 2026-06-11
---

# 2026-06-11 Email Verification Cross-Browser Expired Redirect

## What Happened

A newly registered customer opened the verification email link from a mail-app
browser and was redirected to the login recovery page with
`verification=expired` even though the backend verification request succeeded.

## Why It Matters

Email verification is the first required customer onboarding gate. Showing an
expired-link recovery state after a successful verification consumes the
single-use token, makes the next click fail for real, and leaves the user unable
to continue without a resend.

## Affected Surfaces

- `identity-access`
- `customer-web`
- `production`

## Evidence

- Production artifact for `791***@qq.com` was created at
  `2026-06-11 13:23:33 UTC`, expired at `2026-06-12 13:23:33 UTC`, and was
  consumed at `2026-06-11 13:23:51 UTC`.
- Nginx logs showed `GET /auth/verify-email?...` followed by
  `POST /api/auth/email-verification/verify` returning `200`, then an immediate
  `GET /auth/login?...&verification=expired`.
- A resent artifact showed the same pattern at `2026-06-11 13:42:40-43 UTC`:
  verification API returned `200`, then the browser landed on
  `verification=expired`.
- The configured email-verification TTL is 24 hours for both registration and
  resend; the customer copy incorrectly said 15 minutes.

## Root Cause

The backend consumed the verification artifact and marked the account verified,
but `/api/auth/email-verification/verify` returned only `account_id` and
`email`. The frontend then required a same-browser stored customer session to
continue. When the email was opened in a different browser context, the
frontend returned `verified_login_required`; the verify page mapped that failed
result to `verification=expired`.

After that first successful backend verification, the token was consumed, so
continuing to click the same link correctly hit the single-use artifact
protection and looked expired.

## Current Status

- Backend email verification now returns a fresh session token after successful
  verification.
- Frontend email verification accepts that returned session, so cross-browser
  email opens can continue without relying on localStorage from registration.
- Resend success copy now states the actual 24-hour validity window.

## Resolution

- Fix commit: `94417f55`.
- Deployed SHA: `6df5d8be1746071cf8afcb84bb0f500c577332d4`.
- Production evidence:
  `artifacts/evidence/email-verification-cross-browser/2026-06-11-production-smoke.md`.
- Production smoke created a temporary account, verified the deployed API
  returned `session_token`, used that token against
  `GET /api/auth/current-user` with status `200`, and cleaned up all temporary
  rows.
- Production web bundle check confirmed the old `15 minutes` / `15 分钟` copy is
  absent and the `24 hours` / `24 小时` copy is present.
- Verification:
  - `.venv/bin/python -m pytest tests/unit/coke/identity_access -q`
  - `cd web && pnpm test lib/customer-auth.test.ts lib/i18n.test.ts app/'(customer)'/auth/login/page.test.tsx app/'(customer)'/auth/verify-email/page.test.tsx`
  - `zsh scripts/suggest-verification --base HEAD~1`
  - `zsh scripts/review-trigger --base HEAD~1`
  - `zsh scripts/verify-surface clean-rebuild-backend clean-rebuild-web repo-os-docs`
