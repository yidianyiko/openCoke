# Email/Auth Closure Design

Date: 2026-04-14

## Scope

This design closes the remaining gaps in the Coke email-auth flow without
changing the overall Gateway-owned architecture:

- registration, email verification, resend verification, forgot password,
  and reset password remain in `gateway/packages/api`
- Coke user pages remain in `gateway/packages/web`
- deployment docs and env templates become explicit about the variables
  required for Coke email auth to work in production

## Problems To Close

1. Registration currently fails hard when verification email delivery fails,
   even though the account has already been created.
2. The verify-email page only reads `email` from the URL, so users who just
   registered or logged in can land on the page without a prefilled email and
   cannot immediately resend.
3. The login page has no direct forgot-password entry point.
4. Deployment guidance and env examples do not document the variables needed by
   Coke auth and email delivery, and one referenced env template does not
   exist.

## Design

### Backend registration behavior

Registration keeps account creation and ClawScale-user provisioning unchanged.
Verification email delivery becomes best-effort:

- create the account
- ensure the ClawScale user
- attempt to issue and send the verification email
- if sending fails, log the error and still return `201` with the auth payload

This preserves the newly created account and lets the user continue to the
verify-email page, where they can trigger resend. This avoids the current
"request failed but the email is already taken" behavior without introducing a
rollback path for partially provisioned personal tenants.

### Frontend email flow

The verify-email page should use the best available email source in this order:

1. `email` query parameter
2. stored Coke user profile in local storage
3. empty string

This keeps the resend action available immediately after register/login even
when the route has no query string. The login page also gets a direct
`/coke/forgot-password` link.

### Deployment/config documentation

Add a root deployment env example used by `docs/deploy.md`, and expand the
Gateway env example to include the Coke-specific variables:

- `COKE_JWT_SECRET`
- `DOMAIN_CLIENT`
- `MAILGUN_API_KEY`
- `MAILGUN_DOMAIN`
- `EMAIL_FROM`
- SMTP fallback variables
- Stripe variables already used by Coke payment routes

## Testing

- API route tests cover registration when verification email delivery throws.
- Web tests cover verify-email fallback to stored auth and the login page forgot
  password entry.
- Focused Vitest runs remain the verification gate for this closure work.
