---
kind: design
status: active
date: 2026-06-02
topic: email-delivery-port
---

# Email Delivery Port (Resend → Python identity_access)

## Problem

Web registration creates an `email_verification` auth artifact in Postgres
(`delivery="email"`, `delivery_state="pending"`) but nothing delivers it, so
users never receive a verification link. The frontend "resend" button is a
hardcoded stub returning `unsupported_operation` and never calls the backend.
There is no backend resend route either. Password-reset and claim artifacts have
the same latent gap.

## Root Cause (history)

Email delivery existed before the clean rebuild, implemented in the **`gateway`
submodule** (Node/TS) using **Resend.com**:

- `gateway/packages/api/src/lib/email.ts` — `new Resend(RESEND_API_KEY)` +
  `resend.emails.send(...)`, `EMAIL_FROM` / `EMAIL_FROM_NAME`.
- `gateway/packages/api/src/lib/customer-email.ts` — `sendCustomerVerificationEmail`,
  `sendCustomerPasswordResetEmail`, `sendCustomerClaimEmail`, building links under
  `${DOMAIN_CLIENT}/auth/...`.

Commit `d1e05b97 refactor: remove legacy coke runtime` removed the entire gateway
submodule. The clean rebuild moved auth to Python (`coke/domains/identity_access`)
but explicitly listed **"Email provider delivery"** as Out of scope
(`docs/superpowers/plans/2026-05-29-coke-clean-rebuild-identity-access.md:47`),
so the send path was never ported. The recovered old source still exists in stale
worktrees (e.g. `.worktrees/worker-d-interface-alias-cleanup/gateway/...`) and is
the behavioral reference for this port.

## Decisions (confirmed with user 2026-06-02)

1. **Synchronous send**, inline in the request path (matches old gateway). No
   outbox/worker indirection for auth emails.
2. **Restore all three emails**: email verification, password reset, account claim.
3. **Reuse the existing Resend account and API key** (still active). Same sender
   domain `noreply@keep4oforever.com`.

## Design

### Email sender

- New module `coke/domains/identity_access/email.py` (or `coke/email.py` if a
  cross-domain home is cleaner) exposing:
  - A `CustomerEmailSender` Protocol with `send_verification(to, token, email)`,
    `send_password_reset(to, token)`, `send_claim(to, token)`.
  - A `ResendEmailSender` implementation: HTTP `POST https://api.resend.com/emails`
    via `httpx` (already a dependency), `Authorization: Bearer <RESEND_API_KEY>`,
    JSON `{from, to, subject, html}`. Mirror old subjects/HTML link bodies.
  - A `NullEmailSender` that logs and no-ops, used when no API key is configured
    (local/dev/tests) so registration does not break offline.
- Links point at the **web origin** = `settings.public_base_url`
  (`COKE_PUBLIC_BASE_URL`, e.g. `https://coke.keep4oforever.com`):
  - verify: `{web}/auth/verify-email?token=<code>&email=<email>`
  - reset:  `{web}/auth/reset-password?token=<code>`
  - claim:  `{web}/auth/claim?token=<code>`
  - `<code>` is the value `verify_email` / `reset_password` / claim redeem look up
    (the artifact `code`; confirm against `_consume_artifact` / `get_artifact_by_code`).

### Service wiring

- `IdentityAccessService.__init__` gains `email_sender: CustomerEmailSender` and
  `public_base_url: str` (default localhost, like `SocialSchedulingService`).
- Send points:
  - `register_web_account` → after issuing the verification artifact, send
    verification email.
  - `issue_password_reset` → after issuing, send reset email.
  - claim issuance path (`coke/api/claim_routes.py` / corresponding service
    method) → send claim email **only when the claim targets an email address**;
    channel-only claim flows are unaffected.
  - `resend_artifact` → re-send the email matching the artifact type
    (verification vs password reset).

### Routes

- Add `POST /api/auth/email-verification/resend` `{email}`: re-send the account's
  current active (unconsumed, unexpired) verification artifact; if none exists,
  issue a fresh one and send. Returns `{accepted: true}` 202. Map "unknown email"
  to a generic accepted response to avoid account enumeration (match password-reset
  request semantics where reasonable).
- Frontend `web/lib/customer-auth.ts:resendCustomerVerification` replaces the
  `unsupported_operation` stub with a real POST to that route.

### Send-failure semantics

Match the old gateway: the account and artifact are persisted first, then the
email is sent. If Resend returns an error, surface a clear error code; because the
artifact already exists, the user (or admin) can recover via resend. Do not leave
the account in a half-created state.

### Config

- `Settings` gains `resend_api_key`, `email_from` (default
  `noreply@keep4oforever.com`), `email_from_name` (optional), read from
  `RESEND_API_KEY` / `EMAIL_FROM` / `EMAIL_FROM_NAME`.
- Production guard: require `RESEND_API_KEY` in production (mirror the
  `SiliconFlow_API_KEY` guard) so prod never silently drops verification mail.
  Non-production without a key falls back to `NullEmailSender`.

### Out of scope

- Async/outbox email delivery.
- HTML email templating beyond the old single-link bodies.
- Changing token/artifact lifecycle or verify/reset/claim redemption logic.

## Acceptance

- Real registration against a configured backend sends a Resend verification mail
  whose link verifies the account.
- Resend button triggers a real backend call that re-sends mail (no
  `unsupported_operation`).
- Password-reset request and claim (email-targeted) send their mails.
- Unit tests cover sender selection (Resend vs Null), link shapes, and each send
  point via a fake sender. `zsh scripts/check` + identity_access unit tests green.
