# One-Click Email Verification Design

Date: 2026-04-15

## Scope

This change removes manual verification-token entry from the Coke user email
verification flow and replaces it with a link-driven one-click verification
experience.

It covers:

- `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- related localized copy and page tests

It does not change the backend verification contract, the registration API, or
the email token format.

## Current State

Today the system already sends a verification link containing both `token` and
`email` query parameters. The backend verifies those values through
`POST /api/coke/verify-email`.

The user-facing problem is in the web flow:

- the `/coke/verify-email` page reads `token` and `email` from the query string
- it pre-fills a form with those values
- the user must still click a submit button
- the page still exposes a manual token input, which is not acceptable for the
  desired product UX

## Goal

Make the verification link itself the product action.

Required user experience:

1. User registers and receives a verification email.
2. User clicks the email link.
3. Verification runs automatically without exposing a token form.
4. On success, the user is redirected to the existing next step.
5. If the link is invalid, missing, or expired, the user is redirected to the
   login page and told to resend the verification email.

Manual token entry is considered a bug and must not remain in the UI.

## Design

### 1. Keep the backend verification contract unchanged

The backend route stays as:

- `POST /api/coke/verify-email` with `{ email, token }`

Reasoning:

- the contract already exists and is covered by tests
- the token remains one-time and POST-backed
- we avoid moving verification side effects into a `GET` route

The verify-email page will become an automatic client for this contract rather
than a token-entry form.

### 2. Convert `/coke/verify-email` into an automatic transition page

`/coke/verify-email` should no longer render:

- token input
- email input
- manual submit button
- resend button

Instead it should:

1. read `token` and `email` from the URL on mount
2. if either value is missing, redirect immediately to `/coke/login`
3. call `POST /api/coke/verify-email`
4. while the request is in flight, render a short “verifying” state
5. on success:
   - store auth from the response
   - redirect to `/coke/renew` when `subscription_active === false`
   - otherwise redirect to `/coke/bind-wechat`
6. on any verification failure:
   - redirect to `/coke/login`
   - include the email when available
   - include a query flag indicating verification-link failure

Recommended query shape:

- `/coke/login?email=<encoded>&verification=expired`

`expired` is the single user-facing bucket for:

- missing token
- missing email
- invalid token
- expired token
- malformed verification state

This keeps UX simple and avoids leaking unnecessary token semantics into the UI.

### 3. Add a login-page verification recovery state

The login page should support a recovery state driven by query parameters.

Expected behavior:

- read `email` from the query string and prefill the email input
- read `verification=expired`
- when present, show a clear message telling the user that the verification
  link is invalid or expired and that they should resend the verification email
- render a dedicated “Resend verification email” action on the login page

That resend button should:

- call `POST /api/coke/verify-email/resend` with the current email
- stay disabled if the email field is empty
- show a loading state while sending
- render the backend’s existing generic success copy after completion

The login form itself remains otherwise unchanged.

### 4. Localized copy changes

The i18n copy needs two additions:

- verify-email page loading copy for automatic verification
- login-page recovery copy for expired verification links and resend action

The verify-email page copy should stop mentioning token pasting entirely.

### 5. Error handling

User-facing handling should be intentionally narrow:

- no manual token fallback
- no token-specific debugging text
- no support contact branch for ordinary expiry

If automatic verification fails, the system should always route the user into
the login recovery state, where they can resend the email and continue.

### 6. Testing

Required coverage:

- verify-email page auto-submits when `token` and `email` exist
- verify-email page redirects without rendering token-entry UI
- verify-email page routes success to the correct next screen
- verify-email page routes failure to login with recovery query params
- login page pre-fills email from query params
- login page shows verification-expired recovery copy
- login page resend action calls the existing resend endpoint

Backend route tests should remain green without contract changes.

## Non-Goals

- changing the verification token storage model
- converting email verification to a backend `GET` callback
- redesigning registration or login layout
- changing password-reset behavior

## Risks

1. Client-side auto-verification could create redirect loops if the login page
   redirects back to verify-email for unverified users without preserving flow
   boundaries.
   Mitigation: only verify-email performs automatic verification; login keeps
   its current behavior and only shows resend recovery when explicitly asked by
   query parameters.

2. Missing query parameters in copied or truncated links could strand users.
   Mitigation: treat missing params exactly like expired links and send users to
   login with a resend path.

3. Removing the manual token form could hide useful debugging signals during
   development.
   Mitigation: preserve exact route/API tests while keeping the user-facing
   surface simple.
