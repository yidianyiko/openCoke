# Gateway Auth, Email Verification, and Stripe Payment Design

Date: 2026-04-10

## Context

Coke's user-facing auth currently lives in the Python Flask Bridge
(`connector/clawscale_bridge/user_auth.py`). User records are stored in
MongoDB, then a second provisioning call creates a matching
`ClawscaleUser` + `Tenant` in the Gateway's Postgres database. This
results in duplicated user state across two databases and two services.

This design consolidates auth, email verification, and payment into the
Gateway (TypeScript/Hono/Prisma). The Bridge becomes a pure business
translation layer that only receives inbound messages from the Gateway.

## Decisions

- Auth, email verification, password reset, and Stripe payment all move
  to the Gateway.
- All `/user/*` endpoints move from Bridge to Gateway.
- Bridge retains only `/bridge/inbound` (internal, called by Gateway).
- The old 269 users on the Volcano server are not migrated. The new
  system deploys fresh on GCP.
- `CokeAccount.id` (Prisma cuid) becomes the canonical user identifier
  across the entire stack: Gateway, Bridge, and Agent.
- Email must be verified before the user can bind WeChat or use the
  product.
- Payment model: one-time Stripe Checkout purchase unlocks 30 days of
  access. Price is configured in Stripe Dashboard, not in code.
- When a subscription expires, the Bridge does not call the LLM. It
  returns a hard-coded renewal prompt instead.
- Email delivery uses Mailgun (primary) or SMTP (fallback), following
  the pattern established in the LibreChat project at
  `/data/projects/LibreChat`.

## Data Model Changes

All changes are in the Gateway Prisma schema
(`gateway/packages/api/prisma/schema.prisma`).

### New enum: CokeAccountStatus

```prisma
enum CokeAccountStatus {
  normal
  suspended
}
```

### New model: CokeAccount

Replaces the MongoDB `users` collection for web-auth users.

```prisma
model CokeAccount {
  id              String            @id @default(cuid())
  email           String            @unique
  passwordHash    String            @map("password_hash")
  displayName     String            @map("display_name")
  emailVerified   Boolean           @default(false) @map("email_verified")
  status          CokeAccountStatus @default(normal)
  createdAt       DateTime          @default(now()) @map("created_at")
  updatedAt       DateTime          @updatedAt @map("updated_at")

  clawscaleUser   ClawscaleUser?
  subscriptions   Subscription[]
  verifyTokens    VerifyToken[]

  @@map("coke_accounts")
}
```

### New model: Subscription

Tracks each payment event and its corresponding access window.

```prisma
model Subscription {
  id                String   @id @default(cuid())
  cokeAccountId     String   @map("coke_account_id")
  stripeSessionId   String   @unique @map("stripe_session_id")
  amountPaid        Int      @map("amount_paid") // cents
  currency          String   @default("usd")
  startsAt          DateTime @map("starts_at")
  expiresAt         DateTime @map("expires_at")
  createdAt         DateTime @default(now()) @map("created_at")

  account CokeAccount @relation(fields: [cokeAccountId], references: [id], onDelete: Cascade)

  @@index([cokeAccountId])
  @@map("subscriptions")
}
```

### New enum: VerifyTokenType

```prisma
enum VerifyTokenType {
  email_verify
  password_reset
}
```

### New model: VerifyToken

Shared by email verification and password reset flows. Token is hashed
with SHA-256 (not bcrypt) so the hash is deterministic and can be used
for direct database lookup.

```prisma
model VerifyToken {
  id              String          @id @default(cuid())
  cokeAccountId   String          @map("coke_account_id")
  tokenHash       String          @unique @map("token_hash")
  type            VerifyTokenType
  expiresAt       DateTime        @map("expires_at")
  used            Boolean         @default(false)
  createdAt       DateTime        @default(now()) @map("created_at")

  account CokeAccount @relation(fields: [cokeAccountId], references: [id], onDelete: Cascade)

  @@index([cokeAccountId])
  @@map("verify_tokens")
}
```

### Modified model: ClawscaleUser

`cokeAccountId` changes from a free-form string (MongoDB ObjectId) to a
foreign key referencing `CokeAccount.id`. The existing `@@unique` on
`cokeAccountId` already enforces a one-to-one relationship. The only
schema change is adding the `account` relation field and its
`@relation` annotation.

```prisma
model ClawscaleUser {
  id            String   @id
  tenantId      String   @map("tenant_id")
  cokeAccountId String   @unique @map("coke_account_id")
  createdAt     DateTime @default(now()) @map("created_at")
  updatedAt     DateTime @updatedAt @map("updated_at")

  tenant         Tenant       @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  account        CokeAccount  @relation(fields: [cokeAccountId], references: [id], onDelete: Cascade)
  channels       Channel[]
  endUsers       EndUser[]
  deliveryRoutes DeliveryRoute[]
  conversations  Conversation[]

  @@unique([tenantId, cokeAccountId])
  @@index([tenantId])
  @@map("clawscale_users")
}
```

## API Design

All new endpoints live on the Gateway under `/api/coke/`.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/coke/register` | none | Create account, send verification email |
| POST | `/api/coke/login` | none | Authenticate, return JWT |
| POST | `/api/coke/verify-email` | none | Verify email with token |
| POST | `/api/coke/resend-verification` | none | Resend verification email |
| POST | `/api/coke/forgot-password` | none | Send password reset email |
| POST | `/api/coke/reset-password` | none | Reset password with token |
| GET  | `/api/coke/me` | Bearer JWT | Return current user profile + subscription status |

### Payment

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/coke/checkout` | Bearer JWT | Create Stripe Checkout session, return URL |
| POST | `/api/coke/stripe-webhook` | Stripe signature | Handle `checkout.session.completed` |
| GET  | `/api/coke/subscription` | Bearer JWT | Return current subscription status + expiry |

### WeChat Channel (moved from Bridge)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/coke/wechat-channel` | Bearer JWT | Create personal WeChat channel |
| POST | `/api/coke/wechat-channel/connect` | Bearer JWT | Start QR login |
| GET  | `/api/coke/wechat-channel/status` | Bearer JWT | Poll connection status |
| POST | `/api/coke/wechat-channel/disconnect` | Bearer JWT | Disconnect channel |
| DELETE | `/api/coke/wechat-channel` | Bearer JWT | Archive channel |

### Access Gates

WeChat channel endpoints require `emailVerified === true`. If not
verified, return `403 { error: "email_not_verified" }`.

WeChat channel `connect` additionally requires an active subscription
(a `Subscription` row where `expiresAt > now()`). If expired or missing,
return `402 { error: "subscription_required" }`.

## Flows

### Registration

```
User -> POST /api/coke/register { displayName, email, password }
  1. Validate input (email format, password >= 8 chars)
  2. Normalize email: lowercase + trim
  3. Check email uniqueness
  4. Hash password with bcrypt
  5. Create CokeAccount (emailVerified: false)
  6. Provision ClawscaleUser + Tenant inside the same Gateway transaction:
     - Create Tenant with slug "personal-{cokeAccountId}",
       name "{displayName}'s Workspace",
       settings { kind: "personal", ownerCokeAccountId, autoCreated: true }
     - Create ClawscaleUser with a generated cuid, linking to the new
       Tenant and CokeAccount
     - Create a default AiBackend (type: "custom") pointing to the
       Bridge inbound URL
     This is the same logic currently in
     gateway/packages/api/src/routes/coke-user-provision.ts
     (ensureClawscaleUserForCokeAccount), moved from an internal HTTP
     call to a direct function call within the Gateway.
  7. Generate 32 random bytes as plain token, SHA-256 hash it, store
     in VerifyToken (type: email_verify, TTL: 15 minutes)
  8. Send verification email with link:
     {DOMAIN}/coke/verify-email?token={plainToken}&email={email}
  9. Return JWT + user profile (emailVerified: false)
```

### Email Verification

```
User clicks link -> Frontend POST /api/coke/verify-email { token, email }
  1. SHA-256 hash the plain token
  2. Find VerifyToken by tokenHash + type "email_verify" + used false
  3. Check expiresAt > now
  4. Find associated CokeAccount, verify email matches
  5. Set CokeAccount.emailVerified = true
  6. Mark VerifyToken.used = true
  7. Return { ok: true }
```

### Login

```
User -> POST /api/coke/login { email, password }
  1. Find CokeAccount by email
  2. Verify password with bcrypt
  3. Check status === "normal"
  4. Return JWT + user profile (includes emailVerified, subscription status)
```

### Password Reset

```
User -> POST /api/coke/forgot-password { email }
  1. Find CokeAccount by email (if not found, return ok anyway to prevent enumeration)
  2. Generate token, hash, store VerifyToken (type: "password_reset", TTL: 15 min)
  3. Send reset email with link:
     {DOMAIN}/coke/reset-password?token={plainToken}&email={email}

User -> POST /api/coke/reset-password { token, email, newPassword }
  1. SHA-256 hash the plain token
  2. Find VerifyToken by tokenHash + type "password_reset" + used false
  3. Check expiresAt > now
  4. Find associated CokeAccount, verify email matches
  5. Update password hash
  6. Mark token used
  7. Return { ok: true }
  Note: existing JWTs (up to 7 days) remain valid. Accepted trade-off
  at current scale. See Security Considerations.
```

### Stripe Checkout

```
User -> POST /api/coke/checkout (Bearer JWT)
  1. Verify JWT, get CokeAccount
  2. Require emailVerified === true
  3. Create Stripe Checkout Session:
     - mode: "payment"
     - payment_method_types: ["card"] (add "alipay", "wechat_pay" only
       if configured in Stripe Dashboard; these require additional
       Stripe account setup)
     - The price must be a one-time Price in Stripe Dashboard, not a
       recurring Price. mode: "payment" will reject recurring prices.
     - success_url: {DOMAIN}/coke/payment-success
     - cancel_url: {DOMAIN}/coke/payment-cancel
     - metadata: { cokeAccountId: account.id }
  4. Return { url: session.url }
```

### Stripe Webhook

```
Stripe -> POST /api/coke/stripe-webhook
  1. Verify signature with STRIPE_WEBHOOK_SECRET
  2. Handle event "checkout.session.completed":
     a. Extract cokeAccountId from metadata
     b. Extract amount_total, currency
     c. Verify payment_status === "paid"
     d. Find the latest active Subscription for this account.
        If one exists and expiresAt > now, stack the new window:
        startsAt = existing expiresAt, expiresAt = existing expiresAt + 30 days.
        Otherwise: startsAt = now, expiresAt = now + 30 days.
     e. Create Subscription:
        - stripeSessionId: session.id (unique, prevents duplicates)
        - startsAt / expiresAt as computed above
        - amountPaid: session.amount_total
        - currency: session.currency
  3. Return 200
```

### Subscription Check at Bridge

When the Bridge receives an inbound message via `/bridge/inbound`, it
needs to know whether the user has an active subscription. Two options:

**Option chosen:** The Gateway includes subscription status in the
inbound payload it sends to the Bridge. The Gateway already resolves the
`cokeAccountId` when routing messages. It queries the latest
`Subscription` for that account and appends
`{ subscriptionActive: true/false, expiresAt: ... }` to the payload.

The Bridge checks this field:
- If `subscriptionActive === true`: proceed to LLM as normal.
- If `subscriptionActive === false`: skip LLM, return a hard-coded
  renewal message with the payment URL.

The Gateway always forwards the message to the Bridge regardless of
subscription status. It is the Bridge's responsibility to check the
`subscriptionActive` field and decide whether to invoke the LLM or
return the hard-coded renewal message.

This keeps the subscription query in the Gateway (where Prisma lives)
and avoids the Bridge needing to call back to Gateway or access Postgres
directly.

## JWT Design

- Signed with a secret stored in env var `COKE_JWT_SECRET`.
- Payload: `{ sub: cokeAccountId, email, iat, exp }`.
- Expiry: 7 days. No refresh token mechanism. When the token expires,
  the user must log in again. `/api/coke/me` returns the current
  profile but does not renew the token.
- Implemented using `jose` (already available in the Node.js ecosystem)
  or `jsonwebtoken`.

## Email Delivery

A shared email utility in `gateway/packages/api/src/lib/email.ts`:

- Checks for Mailgun config first (`MAILGUN_API_KEY` + `MAILGUN_DOMAIN`).
- Falls back to SMTP via Nodemailer (`EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_USERNAME`, `EMAIL_PASSWORD`).
- Templates: plain HTML strings for verification and password reset
  emails. No template engine needed at this stage.
- Env vars:
  - `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` (optional, for Mailgun)
  - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`
    (optional, for SMTP)
  - `EMAIL_FROM` (sender address, e.g., `noreply@coke.app`)

## Bridge Changes

### Removed from Bridge

- `user_auth.py` — deleted
- `gateway_user_provision_client.py` — deleted (provisioning now
  happens inside Gateway directly)
- All `/user/*` routes in `app.py` — deleted
- `agent/runner/access_gate.py` — deleted
- `agent/runner/payment/` — deleted

### Retained in Bridge

- `POST /bridge/inbound` — receives messages from Gateway with
  subscription status included in payload
- `connector/clawscale_bridge/message_gateway.py` — business logic
- `connector/clawscale_bridge/output_dispatcher.py` — sends replies
  back via Gateway
- `connector/clawscale_bridge/reply_waiter.py` — synchronous reply
  coordination

### New Bridge behavior

The inbound payload from Gateway gains a new field:

```json
{
  "cokeAccountId": "clxxxxxxxxxx",
  "subscriptionActive": true,
  "subscriptionExpiresAt": "2026-05-10T00:00:00Z",
  ...existing fields...
}
```

Bridge logic at the top of inbound handling:

```python
if not payload.get("subscriptionActive"):
    return {
        "status": "ok",
        "reply": "Your subscription has expired. Please renew at {payment_url}",
        "skip_llm": True
    }
```

## Agent Changes

### user_id Migration

The Agent currently reads `user_id` from
`session_state["user"]["_id"]` (a MongoDB ObjectId string). After
migration, this becomes `session_state["user"]["id"]` — a Prisma cuid
string from `CokeAccount.id`.

Affected files:
- `agent/runner/agent_handler.py`
- `agent/runner/context.py`
- `agent/agno_agent/workflows/prepare_workflow.py`
- `agent/agno_agent/workflows/post_analyze_workflow.py`
- `agent/agno_agent/tools/reminder_tools.py`
- `agent/agno_agent/tools/reminder/service.py`
- `agent/agno_agent/tools/reminder/validator.py`
- `agent/agno_agent/tools/timezone_tools.py`
- `agent/agno_agent/tools/context_retrieve_tool.py`
- `agent/agno_agent/utils/usage_tracker.py`

The change is mechanical: replace `session_state.get("user", {}).get("_id", "")`
with `session_state.get("user", {}).get("id", "")` throughout.

MongoDB collections (`inputmessages`, `outputmessages`, `conversations`,
`reminders`, `usage_records`, etc.) continue to use this ID as a string
foreign key. The format changes from a 24-char hex ObjectId to a 25-char
cuid, but since these fields are stored as plain strings, no schema
migration is needed.

## Frontend Changes

All pages under `gateway/packages/web/app/(coke-user)/coke/`:

- `register/page.tsx` — POST to `/api/coke/register` (was Bridge).
  After success, show "check your email" instead of redirecting to
  bind-wechat.
- `login/page.tsx` — POST to `/api/coke/login` (was Bridge).
- `bind-wechat/page.tsx` — calls `/api/coke/wechat-channel/*` (was
  Bridge). Gate on `emailVerified` and `subscriptionActive`.
- New page: `verify-email/page.tsx` — handles the verification link.
- New page: `forgot-password/page.tsx` — request reset email.
- New page: `reset-password/page.tsx` — set new password with token.
- New page: `payment-success/page.tsx` — confirmation after Stripe
  redirect.
- New page: `payment-cancel/page.tsx` — handle Stripe checkout
  cancellation, offer retry.
- `lib/coke-user-api.ts` — change base URL from Bridge to Gateway.

## Environment Variables

New env vars required on the Gateway:

```
# Auth
COKE_JWT_SECRET=          # Secret for signing JWTs
DOMAIN_CLIENT=            # Frontend URL for email links (e.g., https://coke.app)

# Email (one of these groups)
MAILGUN_API_KEY=          # Mailgun API key
MAILGUN_DOMAIN=           # Mailgun domain
EMAIL_FROM=               # Sender address

# Or SMTP
EMAIL_HOST=
EMAIL_PORT=
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=

# Stripe
STRIPE_SECRET_KEY=        # From Stripe Dashboard
STRIPE_WEBHOOK_SECRET=    # From Stripe Webhooks configuration
```

## File Structure

New files in the Gateway:

```
gateway/packages/api/src/
  lib/
    email.ts                    # Email sending utility
    coke-auth.ts                # JWT signing, password hashing, token generation
    coke-subscription.ts        # Subscription check helpers
  routes/
    coke-auth-routes.ts         # register, login, verify-email, reset-password
    coke-payment-routes.ts      # checkout, webhook, subscription status
    coke-wechat-routes.ts       # moved from Bridge proxy, direct implementation
```

## Security Considerations

- Passwords hashed with bcrypt (cost factor 10).
- Verification tokens: 32 random bytes via `crypto.randomBytes()`.
  Hashed with SHA-256 before storage. Plain token sent in email link.
  Lookup by SHA-256 hash (deterministic, allows direct DB query via
  the `@unique` index on `tokenHash`).
- Token TTL: 15 minutes for both email verify and password reset.
- Stripe webhook signature verified before processing.
- Stripe session ID unique index prevents duplicate subscription
  creation.
- Password reset does NOT invalidate existing JWTs. With a 7-day
  expiry, existing tokens remain valid until they naturally expire.
  Accepted trade-off at current scale. If needed later, add a
  `tokenVersion` counter to `CokeAccount` and include it in the JWT
  payload for validation.
- Email normalization: lowercase + trim on all inputs (register, login,
  verify, reset).
- Rate limiting on auth endpoints: defer to a later iteration. The
  current user volume (< 300) does not warrant it.

## Out of Scope

- Subscription-based recurring billing (Stripe Subscriptions API). The
  current model is manual renewal via one-time purchase.
- User profile editing (change email, change display name).
- 2FA / multi-factor authentication.
- Rate limiting on auth endpoints.
- Migration of existing 269 users from Volcano server.
- Admin dashboard for managing users or subscriptions.
