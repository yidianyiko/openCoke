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
  access. Price is created in Stripe Dashboard and selected at runtime via
  `STRIPE_PRICE_ID`; amount and currency are not hard-coded.
- When a subscription expires, the Bridge does not call the LLM. It
  returns a hard-coded renewal prompt instead.
- Inbound message access is based on the combined account state:
  `status === "normal"`, `emailVerified === true`, and active
  subscription.
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
  @@index([cokeAccountId, expiresAt])
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

All authenticated `/api/coke/*` endpoints load the CokeAccount from the
JWT and require `status === "normal"`. If suspended, return
`403 { error: "account_suspended" }`.

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
     - line_items: [{ price: process.env.STRIPE_PRICE_ID, quantity: 1 }]
     - `STRIPE_PRICE_ID` is required at startup. It must point to the
       Dashboard-created one-time Price for the 30-day Coke access product.
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
     d. Process the session in a database transaction that serializes by
        CokeAccount. The transaction must lock the account row before
        reading subscriptions, e.g. Postgres `SELECT id FROM coke_accounts
        WHERE id = $1 FOR UPDATE` via Prisma `$queryRaw` inside
        `$transaction`.
     e. Inside the lock, find the latest active Subscription for this
        account. If one exists and expiresAt > now, stack the new window:
        startsAt = existing expiresAt, expiresAt = existing expiresAt + 30
        days. Otherwise: startsAt = now, expiresAt = now + 30 days.
     f. Create Subscription:
        - stripeSessionId: session.id (unique, prevents duplicates)
        - startsAt / expiresAt as computed above
        - amountPaid: session.amount_total
        - currency: session.currency
        If the unique `stripeSessionId` constraint is hit, treat it as an
        already-processed webhook and return 200.
  3. Return 200
```

### Subscription Check at Bridge

When the Gateway routes a personal Coke inbound message to the Bridge, it
must resolve the `CokeAccount` and compute access before calling the
Bridge. The access lookup returns:

- `accountStatus`
- `emailVerified`
- `subscriptionActive`
- `subscriptionExpiresAt`
- `accountAccessAllowed`
- `accountAccessDeniedReason`
- `renewalUrl`

`accountAccessAllowed` is true only when all of these are true:

- `CokeAccount.status === "normal"`
- `CokeAccount.emailVerified === true`
- latest `Subscription.expiresAt > now()`

The Bridge checks `accountAccessAllowed`, not only
`subscriptionActive`:

- If `accountAccessAllowed === true`: enqueue the message and let the
  Agent/LLM run as normal.
- If `accountAccessAllowed === false`: do not enqueue the message, do not
  call the Agent/LLM, and return a hard-coded response based on
  `accountAccessDeniedReason`.

Supported denied reasons:

- `email_not_verified`: ask the user to verify email in the Coke web app.
- `subscription_required`: ask the user to renew at `renewalUrl`.
- `account_suspended`: tell the user the account cannot currently use the
  service.

`renewalUrl` is a frontend URL, not a Stripe Checkout Session URL. It is
computed by the Gateway as `COKE_RENEWAL_URL` when set, otherwise
`{DOMAIN_CLIENT}/coke/renew`. The `/coke/renew` page requires login and
then calls `POST /api/coke/checkout` with the user's JWT to create the
Stripe Checkout Session.

The Gateway always forwards the message to the Bridge regardless of
access status. It is the Bridge's responsibility to check
`accountAccessAllowed` and decide whether to enqueue work for the Agent.

This keeps the subscription query in the Gateway (where Prisma lives)
and avoids the Bridge needing to call back to Gateway or access Postgres
directly.

Gateway implementation detail: `gateway/packages/api/src/lib/route-message.ts`
already resolves `resolvedCokeAccountId` before `runBackend(...)`. Before
calling the Bridge-backed custom backend for a personal Coke channel, it
must load `CokeAccount` and latest subscription, compute the fields above
through `coke-account-access.ts`, and include them in the `metadata`
object passed to `generateReply(...)`.

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
- `agent/runner/access_gate.py` — deleted after its call sites are
  removed from the Agent dispatcher.
- `agent/runner/payment/` — deleted after Stripe checkout creation is
  moved to Gateway `/api/coke/checkout`.
- `access_control` payment-provider config in `conf/config.json` is
  removed or ignored; Agent startup must not import payment providers.

### Retained in Bridge

- `POST /bridge/inbound` — receives messages from Gateway with
  account access fields included in payload metadata
- `connector/clawscale_bridge/message_gateway.py` — business logic
- `connector/clawscale_bridge/output_dispatcher.py` — sends replies
  back via Gateway
- `connector/clawscale_bridge/reply_waiter.py` — synchronous reply
  coordination

### New Bridge behavior

Gateway calls the Bridge custom backend endpoint with access fields inside
the `metadata` envelope. The Bridge normalizes these into snake_case
internally before applying the gate:

```json
{
  "messages": [{ "role": "user", "content": "hello" }],
  "metadata": {
    "cokeAccountId": "clxxxxxxxxxx",
    "cokeAccountDisplayName": "Alice",
    "accountStatus": "normal",
    "emailVerified": true,
    "subscriptionActive": true,
    "subscriptionExpiresAt": "2026-05-10T00:00:00Z",
    "accountAccessAllowed": true,
    "accountAccessDeniedReason": null,
    "renewalUrl": "https://coke.app/coke/renew"
  }
}
```

Bridge logic at the top of inbound handling:

```python
if not inbound.get("account_access_allowed"):
    reason = inbound.get("account_access_denied_reason")
    if reason == "subscription_required":
        reply = f"Your subscription has expired. Please renew at {inbound.get('renewal_url')}"
    elif reason == "email_not_verified":
        reply = "Please verify your email in the Coke web app before chatting."
    elif reason == "account_suspended":
        reply = "This account cannot currently use Coke. Please contact support."
    else:
        reply = "Coke account access is not available right now."
    return {
        "status": "ok",
        "reply": reply,
        "skip_llm": True
    }
```

This replaces the old Agent-side `AccessGate` dispatch path. The
implementation must also remove:

- `from agent.runner.access_gate import AccessGate` from
  `agent/runner/message_processor.py`
- `self.access_gate = AccessGate()` from `MessageDispatcher.__init__`
- `self.access_gate.check(...)` and the `gate_denied` / `gate_expired`
  dispatch returns from `MessageDispatcher.dispatch`
- the `gate_denied` / `gate_expired` branches in
  `agent/runner/agent_handler.py` that call
  `dispatcher.access_gate.get_message(...)`

## Agent Changes

### User Context Migration

The migration is not only a session-state key replacement. Today the
Agent resolves inbound messages through Mongo `users._id` before
workflows run:

- `connector/clawscale_bridge/message_gateway.py` writes
  `inputmessages.from_user = cokeAccountId`.
- `agent/runner/message_processor.py` calls
  `UserDAO.get_user_by_id(top_message["from_user"])`.
- `dao/user_dao.py` currently returns `None` for non-ObjectId strings.

Without an Agent user-context adapter, Bridge-enqueued messages from
Gateway will become `user_not_found` before the workflows can read
`session_state["user"]["id"]`.

Required Agent identity behavior:

1. `inputmessages.from_user` remains the canonical `CokeAccount.id`
   string for Gateway-originated Coke users.
2. `inputmessages.to_user` remains the Mongo character ObjectId string
   for the configured character. Character lookup continues to use
   `UserDAO.get_user_by_id`.
3. Add an Agent identity helper, for example
   `agent/runner/identity.py`, with:
   - `get_agent_entity_id(entity)`: returns `entity["id"]` when present,
     otherwise `str(entity["_id"])`.
   - `resolve_agent_user_context(user_id, input_message)`: for legacy
     24-char Mongo ObjectId users, load Mongo `users`; for trusted
     ClawScale/Gateway messages (`metadata.source === "clawscale"` and
     platform `business`), synthesize a user context from payload
     metadata:
     `{ "id": cokeAccountId, "_id": cokeAccountId, "nickname":
     cokeAccountDisplayName || sender || cokeAccountId[-6:],
     "is_coke_account": true }`.
   - If `user_id` is not a Mongo ObjectId and the message is not trusted
     ClawScale/Gateway input, fail with `invalid_user_id` instead of
     silently treating it as missing.
4. Update `MessageAcquirer` to use this helper for `from_user`. It must
   no longer call `UserDAO.get_user_by_id` for `CokeAccount.id`.
5. Update all Agent code that reads IDs for message queries, relation
   keys, reminders, usage tracking, and output messages to call
   `get_agent_entity_id(...)` or read `session_state["user"]["id"]`.
   Compatibility `_id` stays present in the synthesized user context only
   so older code paths do not crash during the migration.

Affected files:

- `agent/runner/message_processor.py` — user resolution, conversation
  talker `db_user_id`, `read_all_inputmessages`, and AccessGate removal.
- `agent/runner/context.py` — relation key creation/lookup must use
  canonical IDs, not raw `["_id"]`.
- `agent/runner/agent_handler.py` — new-message checks and output sending
  must use canonical IDs; remove gate branches.
- `agent/util/message_util.py` — business-message display names must come
  from message metadata or the synthesized user context because Mongo
  `users` will not contain Coke accounts.
- `agent/runner/agent_background_handler.py` — any relation/reminder path
  that loads `relations.uid` through `UserDAO.get_user_by_id` must switch
  to the identity helper or explicitly skip CokeAccount synthetic users
  until Postgres-backed user lookup exists.
- `agent/agno_agent/workflows/prepare_workflow.py`
- `agent/agno_agent/workflows/post_analyze_workflow.py`
- `agent/agno_agent/tools/reminder_tools.py`
- `agent/agno_agent/tools/reminder/service.py`
- `agent/agno_agent/tools/reminder/validator.py`
- `agent/agno_agent/tools/timezone_tools.py`
- `agent/agno_agent/tools/context_retrieve_tool.py`
- `agent/agno_agent/utils/usage_tracker.py`

Workflows and tools should read `session_state["user"]["id"]`. MongoDB
collections (`inputmessages`, `outputmessages`, `conversations`,
`relations`, `reminders`, `usage_records`, etc.) continue to use this ID
as a string foreign key. The format changes from a 24-char hex ObjectId
to a Prisma cuid, but these fields are stored as strings, so no Mongo
schema migration is required.

## Frontend Changes

All pages under `gateway/packages/web/app/(coke-user)/coke/`:

- `register/page.tsx` — POST to `/api/coke/register` (was Bridge).
  After success, show "check your email" instead of redirecting to
  bind-wechat.
- `login/page.tsx` — POST to `/api/coke/login` (was Bridge).
- `bind-wechat/page.tsx` — calls `/api/coke/wechat-channel/*` (was
  Bridge). Gate on the combined account access result: normal account,
  verified email, and active subscription.
- New page: `verify-email/page.tsx` — handles the verification link.
- New page: `forgot-password/page.tsx` — request reset email.
- New page: `reset-password/page.tsx` — set new password with token.
- New page: `payment-success/page.tsx` — confirmation after Stripe
  redirect.
- New page: `payment-cancel/page.tsx` — handle Stripe checkout
  cancellation, offer retry.
- New page: `renew/page.tsx` — destination for Bridge renewal prompts.
  If no valid JWT is present, send the user to login and return here
  after login. Once authenticated, call `POST /api/coke/checkout` and
  redirect to the returned Stripe Checkout URL.
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
STRIPE_PRICE_ID=          # One-time 30-day Price ID from Stripe Dashboard
STRIPE_WEBHOOK_SECRET=    # From Stripe Webhooks configuration
COKE_RENEWAL_URL=         # Optional; defaults to ${DOMAIN_CLIENT}/coke/renew
```

## File Structure

New files in the Gateway:

```
gateway/packages/api/src/
  lib/
    email.ts                    # Email sending utility
    coke-auth.ts                # JWT signing, password hashing, token generation
    coke-subscription.ts        # Subscription check helpers
    coke-account-access.ts      # Combined status/email/subscription access helpers
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
- Stripe webhook stacking runs inside a transaction that locks the
  `CokeAccount` row before reading and creating `Subscription` rows. This
  prevents two distinct paid sessions for the same account from computing
  overlapping access windows.
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
