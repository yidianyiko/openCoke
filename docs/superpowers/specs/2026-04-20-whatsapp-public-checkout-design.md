# WhatsApp Public Checkout Design

Date: 2026-04-20

## Scope

This change lets a shared WhatsApp user renew paid access without logging into
the website.

It covers:

- shared-channel access gating for WhatsApp-provisioned customers
- a signed public checkout entrypoint that redirects directly to Stripe
- renewal-link generation for hard access-denied replies
- the existing Stripe webhook + subscription persistence path

It does not change:

- website email/password login
- claim-token onboarding for users who later want website access
- the Stripe subscription storage model
- admin-managed payment operations

## Current State

Today the system can auto-provision a `Customer` when a new user writes to the
shared WhatsApp channel, but payment still assumes a logged-in website user.

The current renewal chain has two blockers:

1. `POST /api/coke/checkout` requires Coke auth and rejects unauthenticated
   requests.
2. The checkout path also expects an owner identity with verified email, which
   shared WhatsApp users do not have by default.

As a result, the existing renewal URL is only useful for users who have already
claimed a website account. A WhatsApp-only user can hit the trial wall and be
shown a renewal URL, but that URL eventually redirects to login instead of
allowing payment.

There is also a runtime boundary issue in `route-message`: shared-channel users
are provisioned onto `customer_id`, while some access checks still hinge on the
older owner/`cokeAccountId` path. That needs to be normalized before renewal
behavior can be trusted.

## Goal

Make the shared WhatsApp renewal path work end-to-end without website login.

Required user experience:

1. A user writes to the shared WhatsApp number and is auto-provisioned.
2. The user can use the service during the trial window.
3. After trial expiry, the hard access-denied reply includes a payment link.
4. The user taps that link and lands directly in Stripe Checkout.
5. After successful payment, the existing webhook grants access to the same
   `customer_id`.
6. The next WhatsApp message from that user is handled normally again.

Logging into the website must remain optional rather than a prerequisite for
renewal.

## Design

### 1. Normalize shared WhatsApp access checks onto `customer_id`

Shared-channel users should be treated as customer-backed accounts even when no
website identity has been claimed yet.

For shared WhatsApp traffic:

- the stable service unit is `resolvedChannelCustomerId`
- access checks must use that `customer_id`
- the access decision must no longer depend on `resolvedCokeAccountId`
- `email_not_verified` must not block the WhatsApp runtime for shared users

That means the shared WhatsApp access decision becomes:

- `account_suspended` => blocked
- `subscription_required` => blocked with renewal URL
- otherwise => allowed

Email verification remains meaningful for website login and website-owned flows,
but it is not part of the shared WhatsApp renewal gate.

Personal channels keep their current semantics. This change is specifically
about customer-backed identities auto-created from shared WhatsApp ingress.

### 2. Add a signed public checkout entrypoint

Add a new public route:

- `GET /api/coke/public-checkout?token=<signed-token>`

This route is not a website session endpoint. It is a narrowly scoped payment
launcher.

Behavior:

1. Verify the signed token.
2. Extract the `customerId`.
3. Confirm the customer still exists and is eligible for renewal.
4. Create a Stripe Checkout Session for that `customerId`.
5. Redirect the browser to the Stripe hosted checkout URL.

The route does not create a Coke login session, customer auth session, or claim
state. It only creates a payment session.

The existing Stripe webhook remains unchanged in principle:

- it reads `session.metadata.customerId`
- it extends access for that same `customer_id`
- it relies on the existing subscription stacking logic

This keeps accounting and access extension on the current proven path.

### 3. Signed-token format and trust model

The public checkout token should be short-lived and purpose-bound.

Required token properties:

- `customerId`
- `tokenType = "action"`
- `purpose = "public_checkout"`
- `iat`
- `exp`

Recommended TTL:

- `24h`

Security model:

- the token only authorizes creating a checkout session for one customer
- it does not authorize website login
- it does not expose internal account state beyond what Stripe checkout already
  implies

This means a forwarded link can at worst let someone else pay on behalf of that
customer. It cannot take over the account or expose history. That trade-off is
acceptable for the WhatsApp renewal use case.

The token should use its own verification path and must reject any token whose
purpose is not exactly `public_checkout`.

For configuration, this token should reuse the existing customer action-token
secret family:

- `CUSTOMER_JWT_SECRET`
- fallback: `COKE_JWT_SECRET`

This avoids introducing a second payment-link secret while still keeping the
token safely separated by `purpose`.

### 4. Generate renewal links dynamically for access-denied replies

The renewal URL carried through the ClawScale bridge should become dynamic for
shared WhatsApp users.

When the shared WhatsApp access decision is `subscription_required`, gateway
should:

1. generate a signed public checkout token for the resolved `customer_id`
2. build a public checkout URL from that token
3. place that URL in the existing `renewalUrl` metadata field

The bridge already knows how to include `renewal_url` in the hard reply:

- `"Your subscription is required. Renew here: <url>"`

So the user-facing copy path does not need a parallel mechanism. This change is
primarily about ensuring the URL is now directly actionable for a WhatsApp-only
user.

### 5. Route eligibility rules

The public checkout route should accept:

- any `normal` customer referenced by a valid public checkout token

It must reject:

- unknown customers
- suspended customers
- invalid or expired tokens

It does not need to reject already-active subscriptions. Creating an additional
checkout for an active customer is acceptable because:

- the current billing model is one-time renewal
- the webhook already stacks access windows instead of overwriting them

This keeps the route simple and avoids fragile timing rules around trial or
active-renewal boundaries.

### 6. Success and cancel pages

The existing success/cancel pages remain the return targets from Stripe:

- `/coke/payment-success`
- `/coke/payment-cancel`

They should continue to work even when the user is not logged in. For this
feature, they are informational pages, not authenticated account surfaces.

No new post-payment login step is required. The meaningful state transition is
the Stripe webhook updating access for `customer_id`.

### 7. Error handling

User-facing error handling should stay narrow and explicit.

#### Invalid or expired public checkout token

Return a simple HTML page that says the payment link is invalid or expired and
tells the user to go back to WhatsApp and send another message to receive a new
link.

#### Suspended customer

Return a simple HTML page stating that the account is unavailable for renewal.
Do not redirect to Stripe.

#### Stripe checkout creation failure

Return a simple HTML page saying checkout could not be prepared right now and
the user should try again later from WhatsApp.

#### Website login

Never redirect the public checkout route to `/auth/login`. If the route cannot
continue, it must fail as a payment-link problem, not as a missing-login
problem.

## Non-Goals

- adding WhatsApp-based website login
- replacing email/password auth
- adding SMS OTP
- changing the Stripe webhook contract
- building a new payment dashboard for admins
- changing the wording of unrelated access-denied messages

## Risks

1. Shared-channel access checks could stay partially split between
   `resolvedChannelCustomerId` and `resolvedCokeAccountId`, causing inconsistent
   renewal behavior.
   Mitigation: make `customer_id` the explicit source of truth for shared
   WhatsApp access decisions and cover it with route-level tests.

2. A forwarded payment link could be used by another person.
   Mitigation: scope the token to payment only; do not mint login/session
   privileges from it.

3. Public checkout links could create many abandoned Stripe sessions if users
   repeatedly request them.
   Mitigation: generate signed links on denial, but create the Stripe session
   only on click, not during inbound message routing.

4. Success/cancel pages might still implicitly assume an authenticated user.
   Mitigation: keep them informational and verify they render without auth.

## Testing

Required coverage:

- shared WhatsApp customer access uses `customer_id` and returns
  `subscription_required` after the trial window
- shared WhatsApp access is not blocked by `email_not_verified`
- access-denied metadata carries a signed public renewal URL
- public checkout route:
  - redirects to Stripe when the token is valid
  - rejects invalid/expired tokens
  - rejects suspended customers
  - writes `customerId` into Stripe session metadata
- Stripe webhook still extends access for the target `customer_id`
- the next WhatsApp inbound after successful payment resumes normal routing
- payment success/cancel pages render without requiring an authenticated web
  session
