# Disable Email Auth Design

Date: 2026-06-12
Status: approved

## Goal

Temporarily let web-first users register and enter the product without email
verification, and disable password recovery while email delivery is not part of
the active onboarding path.

## Scope

Add a runtime flag, `COKE_EMAIL_AUTH_ENABLED`, defaulting to enabled. When the
flag is disabled:

- Web registration creates the credential, session, and account access state as
  already email-verified.
- Registration does not create an `email_verification` artifact and does not
  send a verification email.
- The web registration page stores the returned session and routes directly to
  the requested internal `next` path or `/channels/wechat-personal`.
- Password reset request and completion are disabled.
- Email-verification resend is disabled.
- Login no longer surfaces email-verification recovery actions.
- Production startup and deploy scripts no longer require `RESEND_API_KEY`.

The existing verification and password-reset code stays in place behind the
enabled mode so the product can re-enable it by setting the flag back to true.

## Boundaries

This change does not disable messaging-first account claim/login-url mechanics.
Those paths are not the user's requested registration verification or password
recovery problem, and removing them would break existing account-claim flows.

`account_access.email_verification_state` remains in the schema and access
status response. In disabled mode, new web-first accounts are stored as
`verified`, so existing access gates continue to work without special frontend
exceptions.

## Verification

Backend verification must cover settings parsing, direct verified registration,
no verification artifacts/email calls in disabled mode, disabled reset/resend
routes, and the preserved enabled-mode behavior. Web verification must cover
direct registration routing and hidden password-recovery/verification-recovery
UI. Diff-aware repository verification must run before handoff.
