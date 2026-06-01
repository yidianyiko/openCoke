---
title: Public friend-link fix and clean-model alignment
date: 2026-06-01
status: approved
kind: design
topic: public-friend-link
---

# Public friend-link fix and clean-model alignment

## Problem

A friend link copied from the web account page has the form:

```
https://coke.example/friends/friend_link_tJm4MJt4NQ3Vdaq5ntJtmHG_-K9Qhsif
```

This is broken in four distinct ways:

1. **Wrong host.** `coke.example` is a unit-test placeholder that leaked into
   production code at `coke/domains/social_scheduling/service.py:773`:
   ```python
   qr_payload=f"https://coke.example/friends/{token}" if token else None,
   ```
2. **Wrong path.** The link uses `/friends/{token}`, but the web app has no
   `/friends/[token]` route. The only public friend-landing route is
   `web/app/u/[code]/page.tsx`, i.e. `/u/{link_code}`.
3. **Wrong identifier.** The link embeds the `public_token`, but the landing
   route and the QR route (`web/app/u/[code]/qr/route.ts`) are keyed on
   `link_code`.
4. **Missing backend resolver.** The landing page resolves a link through
   `GET /api/public/user-links/{code}` (and `POST .../sessions`), but the clean
   backend (`coke/app.py`) registers no `/api/public/...` blueprint. Those
   endpoints exist only in the retired gateway worktree.

The copied string surfaces verbatim: backend `qr_payload`
(`coke/api/friend_routes.py:123`) → web `customer-friends.ts:100` (`url`) →
`account/friends/page.tsx:123` (`navigator.clipboard.writeText(friendLink.url)`).

### Model reality (channel-centric)

The web client was written for the **retired gateway** model: open a *link
session*, poll *session status*, send a *friend request* with a
`pending → accepted` lifecycle.

The clean backend uses a **channel-centric direct establishment** model:

- `establish_friendship_from_code` / `_establish_from_link`
  (`service.py:588-627`) requires **both** the owner and the joiner to have a
  usable messaging channel. The owner is checked at link issue/reset
  (`service.py:79`, `service.py:109`) and again at join (`service.py:597`).
- When the joiner has **no usable channel**, the join returns
  `status="deferred_channel_required"` with `continuation={"friend_link_id":...}`
  (`service.py:600-606`). That continuation only auto-completes the friendship
  if it is **persisted onto a claim artifact** and later consumed on
  channel-connect (`identity_access/service.py:400-420`; proof:
  `tests/unit/coke/channel_reachability/test_channel_reachability_service.py:351-421`).
  `POST /api/friends/join` does **not** persist it — it only serializes it in
  the response (`friend_routes.py:127-134`).

### Scope decision (approved)

**Option 1 — correctness + immediate join for channel-connected joiners.**

- Fix the link string (host / path / identifier) and add the missing public
  resolver so the link opens and shows the owner.
- For a joiner who already has a usable channel, `POST /api/friends/join`
  establishes the friendship immediately.
- For a joiner with **no** channel, surface an honest "connect a messaging
  channel first" message. Do **not** fabricate auto-completion the
  channel-centric model does not wire up.
- Make the friends page resilient for channel-less accounts instead of
  hard-failing.

**Explicitly out of scope (would be a later Option 2):** persisting the
`friend_link_id` continuation through the claim flow so a brand-new joiner's
friendship auto-completes when they first connect a channel. That touches the
identity-access claim wiring and web claim UX and is tracked as follow-up.

## Goals

- A copied friend link points at the real web host and a route that exists.
- A stranger can open the link and see the owner.
- A joiner who has a usable channel becomes a friend through the existing join
  path.
- A channel-less joiner gets a truthful next-step, not a silent dead end.
- No resurrection of the retired link-session / friend-request machinery.

## Non-goals

- Friend-request approval semantics (`pending`/`accepted`/`rejected`).
- Auto-completing a deferred friendship on later channel-connect (Option 2).
- Owner avatars / taglines (clean identity stores a display name only).

## Design

### 1. Backend config — public base URL

Add to `coke/config.py` `Settings`:

- Field `public_base_url: str`, env `COKE_PUBLIC_BASE_URL`, trailing slash
  stripped.
- Non-production fallback: `http://localhost:4040` (matches the web's existing
  `NEXT_PUBLIC_COKE_WEB_URL` fallback).
- **Required explicitly in production**: `app_env == "production"` with a
  missing/empty `COKE_PUBLIC_BASE_URL` raises `ConfigurationError`, mirroring
  the `SiliconFlow_API_KEY` guard. Do not let the local fallback mask a missing
  production value.

**Deploy generation must set it** (review blocker): `scripts/deploy-compose-to-gcp.sh`
writes the production `.env` (around lines 297-310) consumed by
`docker-compose.prod.yml` (api + worker services). Add
`COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com` there so the
production-required guard does not break the deploy.

### 2. Backend — thread the base URL through both compositions

`build_runtime_from_settings` builds **two** runtimes: the main runtime and the
interactive child-runtime factory (`composition.py:1391-1406` and
`composition.py:1438-1453`); the worker uses the interactive factory. Pass
`settings.public_base_url` into **both** `compose_coke_runtime(...)` calls.

`compose_coke_runtime` gains `public_base_url: str = "http://localhost:4040"`
and forwards it to `SocialSchedulingService`.

### 3. Backend — correct the friend-link URL shape

- `SocialSchedulingService.__init__` gains `public_base_url: str`
  (default `http://localhost:4040`), stored trailing-slash-stripped as
  `self._public_base_url`.
- `_link_view` builds from the **link code**, not the token:
  ```python
  qr_payload=f"{self._public_base_url}/u/{code}" if code else None,
  ```

This single change fixes the copied-link string. The same `qr_payload` also
feeds the agent/tool friend-link facts (`composition.py:2095-2103`), so those
become correct too.

### 4. Backend — public link-resolution endpoint

**Service** (`service.py`):

- New value object `PublicFriendLinkView` (`models.py`):
  `link_code: str`, `status: str` (`"active"`), `owner_display_name: str`.
- New method `resolve_public_friend_link(self, link_code: str) -> PublicFriendLinkView | None`:
  - Look up via `get_friend_link_by_code_hash(_hash_token(link_code))`.
  - Return `None` if the link is missing, `lifecycle != "active"` (disabled
    links keep the same row/hash — `service.py:128-144` — so the lifecycle check
    is load-bearing), **or the owner no longer has a usable channel**
    (`self.reachability.has_usable_channel(owner_account_id)` is False) — so the
    page never renders a CTA for a join that must fail.
  - Otherwise resolve the owner name via `self.display_name_resolver(...)`.

**Route** (`coke/api/public_friend_routes.py`, new):

- `create_public_friend_blueprint(social_scheduling_service)`,
  `url_prefix="/api/public/user-links"`. **Unauthenticated.**
- `GET /<code>`:
  - Hit → raw body, HTTP 200:
    ```json
    {"code":"<link_code>","status":"active",
     "profile":{"displayName":"<name>","tagline":null,"avatarUrl":null}}
    ```
  - Miss/inactive → `{"error":{"code":"friend_link_not_active"}}`, **HTTP 404**.
- Register the blueprint in `coke/app.py`.
- Registration must happen whenever `social_scheduling_service` is present,
  outside the `identity_access_service`-gated friend/shared-reminder block.
  The authenticated `/api/friends/*` and `/api/shared-reminders/*` routes still
  require `identity_access_service`; this public resolver does not.

Raw bodies (no `{ok,data}` envelope) match the rest of the coke Flask backend
(`customerApi` returns parsed bodies directly). Enumeration risk is bounded: the
endpoint only returns a display name for an active link whose owner is
reachable; codes are 24-byte url-safe tokens.

### 5. Web — align landing + completion to direct join

**`web/lib/user-link-api.ts`** — reduce to one function:

- `fetchUserLink(code)` consumes the **raw body**: 200 →
  `{ok:true, data:{code,status,profile}}`; any non-200 →
  `{ok:false, error:'link_not_active'}`.
- **Delete** `openLinkSession`, `getLinkSessionStatus`, `createFriendship`
  (retired-gateway legacy; grep confirms only this file + the two pages + tests
  consume them).

**`web/lib/api-types.ts`** — delete now-unused `PublicLinkSessionResponse`,
`PublicLinkSessionStatusResponse`, `DirectFriendshipResponse`. Keep
`PublicUserLinkResponse`.

**`web/app/u/[code]/page.tsx`**:

- Drop `openLinkSession` and `link_session` handling.
- Render owner profile + QR (`/u/{code}/qr`, already correct) + CTAs to
  `/auth/login` and `/auth/register` (existing auth routes) with
  `next=/account/friends?join=<code>`.

**`web/lib/customer-friends.ts`**:

- Add a small clean-route error normalizer. Any backend body shaped as
  `{error:{code:string}}` must become `{ok:false,error:code}` before page code
  interprets it. This applies to the existing link/list/reset/disable/remove
  wrappers too; otherwise `owner_channel_required` and auth failures look like
  successful data because `customerApi` parses non-2xx JSON bodies.
- Add `joinFriendByCode(code)` → `POST /api/friends/join` body
  `{link_code: code}`. Because `customerApi` returns the parsed JSON body even
  on non-2xx (`customer-api.ts:47-56`), the wrapper must inspect the body:
  - `{error:{code}}` → `{ok:false, error: code}` (covers
    `owner_channel_required`, `self_friendship_forbidden`,
    `friend_link_disabled`, `friend_link_not_found`, `unauthorized`,
    `invalid_request`).
  - otherwise → `{ok:true, data:{status, friendship_id, continuation}}`, where
    `status` may be `created`/`already_active`/`deferred_channel_required`.

**`web/app/(customer)/account/friends/page.tsx`**:

- **Resilience fix:** treat `owner_channel_required` from
  `getCustomerFriendLink()` as a non-fatal "no shareable link yet" state (show a
  "connect a messaging channel to get your link" note) rather than failing the
  whole page. Still load the friends list and run the join.
- Replace the `link_session`/`inviteToken`/`getLinkSessionStatus`/
  `createFriendship`/`linkSession` machinery with a one-shot **join-by-code**:
  - Read `?join=<code>`.
  - On confirmed auth (existing `AUTH_ERRORS → loginNextPath`, with `next`
    carrying `?join=<code>`), call `joinFriendByCode(code)` once.
  - Surface by result: `created`/`already_active` → success notice;
    `deferred_channel_required` → "connect a messaging channel first" notice;
    `{error}` → the matching failure notice. Then scrub `join` from the URL.

### 6. Docs and issue record

- `docs/issues/2026-06-01-friend-link-prefix.md` — incident: four-way defect,
  channel-centric model reality, Option-1 scope, affected surfaces, fix
  commit(s), verification.
- `docs/deploy.md` — required `COKE_PUBLIC_BASE_URL`
  (`https://coke.keep4oforever.com`).
- `docs/product-specs/FEATURE_TREE.md` — `GET /api/public/user-links/{code}`
  and the public-link → join flow.

## Data flow (after fix)

```
Owner (channel connected): GET /api/friends/link
  → qr_payload = {COKE_PUBLIC_BASE_URL}/u/{link_code}     (copied link)

Stranger opens {host}/u/{link_code}
  → web GET /api/public/user-links/{link_code}
  → 200 { code, status:"active", profile } (only if link active AND owner
    reachable), else 404 "link not active"
  → renders owner + QR + auth CTAs (next=/account/friends?join={link_code})

Stranger logs in / registers, lands on /account/friends?join={link_code}
  → POST /api/friends/join { link_code }
  → joiner has a usable channel → friendship created (or already_active)
  → joiner has no channel → status deferred_channel_required → honest
    "connect a messaging channel first" notice (no auto-complete in Option 1)
```

## Error handling

- Missing/disabled link, or owner unreachable → public endpoint 404 → landing
  "link not active" panel.
- `COKE_PUBLIC_BASE_URL` unset in production → `ConfigurationError` at startup;
  deploy script supplies it.
- Join unauthenticated → existing `AUTH_ERRORS` redirect to login with `join`
  preserved in `next`.
- Join with no joiner channel → `deferred_channel_required` (a normal 200 body,
  not an error) → informational notice.
- Owner lost channel after issue → `owner_channel_required` (400 `{error}`) →
  surfaced as a friendly notice. (Mostly pre-empted by the public-resolve owner
  reachability check.)
- Self-join → `self_friendship_forbidden` → friendly notice.
- Channel-less authenticated user opening `/account/friends` → no longer breaks;
  link panel shows the "connect a channel" note, friends list still loads.

## Testing

**Backend (pytest):**

- Config: `COKE_PUBLIC_BASE_URL` default, trailing-slash strip,
  production-required guard.
- `SocialSchedulingService`: `qr_payload == {base}/u/{link_code}`;
  `resolve_public_friend_link` for active / disabled (hard test) / missing /
  owner-unreachable.
- Public route: 200 raw-body shape; 404 on unknown/disabled/unreachable code.
- Update fixtures asserting the old `coke.example/friends/...` payload
  (`tests/unit/coke/test_social_scheduling_tool_adapter.py`,
  `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`).

**Web (pnpm test):**

- `user-link-api.test.ts`: `fetchUserLink` raw-body (200 + non-200).
- `app/u/[code]/page.test.tsx`: profile render + auth CTAs with `join` next.
- `customer-friends.test.ts`: `joinFriendByCode` error-body vs success/deferred;
  corrected `url` shape.
- `account/friends/page.test.tsx`: join-by-code created / deferred / error;
  channel-less (`owner_channel_required`) resilience.

**Smoke:**

- Friendship / first-contact paths are covered by the `coke-agent-smoke`
  harness. The public-link → join browser flow is verified manually against the
  real web deploy during rollout.

## Affected files

- `coke/config.py`
- `coke/composition.py`
- `coke/domains/social_scheduling/service.py`
- `coke/domains/social_scheduling/models.py`
- `coke/api/public_friend_routes.py` (new)
- `coke/app.py`
- `scripts/deploy-compose-to-gcp.sh`
- `web/lib/user-link-api.ts`
- `web/lib/api-types.ts`
- `web/lib/customer-friends.ts`
- `web/app/u/[code]/page.tsx`
- `web/app/(customer)/account/friends/page.tsx`
- tests for each surface above
- `docs/issues/2026-06-01-friend-link-prefix.md`, `docs/deploy.md`,
  `docs/product-specs/FEATURE_TREE.md`
