# Resend Email Migration Design

Date: 2026-04-15

## Scope

This design replaces Coke's current Mailgun/SMTP email delivery path with a
direct Resend API integration, without changing the public Coke auth flow:

- `gateway/packages/api/src/lib/email.ts` remains the single email-delivery
  boundary used by Coke auth routes
- `gateway/packages/api/src/routes/coke-auth-routes.ts` keeps the existing
  registration, resend-verification, and password-reset behavior
- deployment env examples and production env on `gcp-coke` move from
  `MAILGUN_*` / `EMAIL_HOST` style configuration to `RESEND_API_KEY`

This migration does not change email content, auth route URLs, or frontend
behavior.

## Current State

The current email layer is provider-generic but optimized for old providers:

- `sendCokeEmail()` first tries Mailgun when `MAILGUN_API_KEY` and
  `MAILGUN_DOMAIN` are set
- otherwise it uses `nodemailer` SMTP with `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_USERNAME`, `EMAIL_PASSWORD`, and related TLS flags
- production on `gcp-coke` is already configured to send via
  `smtp.resend.com`, so the system is using Resend indirectly through SMTP

This works, but it leaves the code on the least expressive Resend path and
keeps obsolete Mailgun/SMTP configuration in both code and docs.

## Goal

Use Resend as the only supported Coke email provider and call it through the
official Node SDK.

The migration should:

1. preserve the `sendCokeEmail()` API used by Coke auth routes
2. remove all Mailgun and SMTP fallback logic from the repository
3. simplify configuration to `RESEND_API_KEY`, `EMAIL_FROM`, and
   `EMAIL_FROM_NAME`
4. support a production rollout on `gcp-coke` with a real send verification to
   `yidianyiko@foxmail.com`

## Design

### Backend integration boundary

`gateway/packages/api/src/lib/email.ts` stays as the only delivery helper
called by auth routes. Its implementation changes from:

- Mailgun HTTP request
- optional SMTP fallback via `nodemailer`

to:

- direct `Resend` SDK client call using `resend.emails.send(...)`

This keeps the route layer stable and limits the migration to one provider
adapter file plus its tests.

### Configuration contract

The new configuration contract is:

- `RESEND_API_KEY` required in environments that send email
- `EMAIL_FROM` optional, defaulting to `noreply@keep4oforever.com` for local fallback
- `EMAIL_FROM_NAME` optional, used to format `"Name" <sender@example.com>`

Removed from supported configuration:

- `MAILGUN_API_KEY`
- `MAILGUN_DOMAIN`
- `EMAIL_SERVICE`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_ENCRYPTION`
- `EMAIL_ENCRYPTION_HOSTNAME`
- `EMAIL_USERNAME`
- `EMAIL_PASSWORD`
- `EMAIL_ALLOW_SELFSIGNED`

For production, the intended sender should use a verified Resend domain. In the
current account, the verified sending domain is `keep4oforever.com`, so the
production sender should be `noreply@keep4oforever.com`.

### Error behavior

`sendCokeEmail()` should keep throwing when delivery fails. Route-level behavior
stays unchanged:

- registration still logs delivery failures and returns `201`
- resend-verification and forgot-password still depend on the existing route
  behavior in `coke-auth-routes.ts`

The helper should treat these conditions as configuration or send failures:

- missing `RESEND_API_KEY`
- Resend SDK returns an error object
- Resend SDK returns no email id

### Dependency changes

`gateway/packages/api/package.json` should:

- add `resend`
- remove `nodemailer`
- remove `@types/nodemailer`

`gateway/pnpm-lock.yaml` should be updated accordingly.

### Testing

Focused API tests should cover:

- missing `RESEND_API_KEY` raises a configuration error
- successful send calls Resend with the formatted `from` address
- default sender behavior still works when no env sender is set

Existing route tests should continue to pass because the route contract and
`sendCokeEmail()` call shape stay stable.

### Rollout

Rollout order:

1. land the code migration and local tests
2. update `~/coke/.env` on `gcp-coke`:
   - add `RESEND_API_KEY`
   - keep `EMAIL_FROM=noreply@keep4oforever.com`
   - remove obsolete Mailgun/SMTP vars
3. restart the Compose stack
4. verify Gateway health
5. trigger a real auth email send to `yidianyiko@foxmail.com`

### Validation target

The production verification is complete when:

- Gateway starts successfully with the new env contract
- a real Coke auth email request results in a successful send path
- the email reaches `yidianyiko@foxmail.com`
- the email contains the expected Coke verification or reset link

## Non-Goals

- introducing a generic multi-provider email abstraction
- changing auth-page copy or route behavior
- templating or redesigning the email HTML
- adding Resend webhooks, tags, or idempotency metadata in this migration

## Risks

1. The configured sender domain may not be verified in Resend.
   Mitigation: keep `EMAIL_FROM` explicit and use a real send verification after
   rollout.

2. Production env may still carry obsolete Mailgun/SMTP variables.
   Mitigation: clean them during rollout so the environment matches the new code
   contract.

3. A missing `RESEND_API_KEY` would break auth email delivery immediately.
   Mitigation: add explicit helper tests and verify Gateway health plus one real
   send after restart.
