---
title: Public friend-link fix and clean-model alignment
date: 2026-06-01
status: draft
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

### Model mismatch (the core of the work)

The web client was written for the **retired gateway** model: open a *link
session* (`POST /sessions`), poll *session status*, and send a *friend request*
with a `pending → accepted` lifecycle.

The clean backend uses a **direct establishment** model:
`establish_friendship_from_token` / `establish_friendship_from_code` create the
friendship immediately, deferring completion (via friend-link continuations)
only when the joiner has no usable channel yet. `POST /api/friends/join`
already exposes this and accepts either `public_token` or `link_code`.

Decision (approved): **align the web to the clean direct-establishment model.**
Do not rebuild the gateway's link-session / friend-request subsystem. Delete the
web-side legacy that has no clean-backend counterpart.

## Goals

- A copied friend link points at the real web host and a route that exists.
- A stranger can open the link, see the owner, authenticate, and become a
  friend through the clean backend's existing join path.
- No resurrection of the retired link-session / friend-request machinery.

## Non-goals

- Friend-request approval semantics (`pending`/`accepted`/`rejected`). The clean
  model establishes (or defers) directly; there is no approval step.
- Owner avatars / taglines. The clean identity schema stores a display name
  only; the public profile exposes `tagline: null`, `avatarUrl: null`.
- Changing the owner's own friend-link panel beyond the corrected `url`.

## Design

### 1. Backend config — public base URL

Add to `coke/config.py` `Settings`:

- Field `public_base_url: str`.
- Sourced from env `COKE_PUBLIC_BASE_URL`, trailing slash stripped.
- Local/default value `http://localhost:4040` (matches the web's existing
  `NEXT_PUBLIC_COKE_WEB_URL` fallback in `web/app/u/[code]/qr/route.ts`).
- **Required in production**: when `app_env == "production"`, a missing/empty
  `COKE_PUBLIC_BASE_URL` raises `ConfigurationError`, mirroring the existing
  `SiliconFlow_API_KEY` production guard. The real value
  (`https://coke.keep4oforever.com`) is supplied by the environment, not
  hard-coded in source.

Thread it through composition:

- `build_runtime_from_settings` passes `settings.public_base_url` into
  `compose_coke_runtime`.
- `compose_coke_runtime` gains a `public_base_url: str` parameter (default
  `http://localhost:4040` for in-memory/test composition) and passes it to
  `SocialSchedulingService`.

### 2. Backend — correct the friend-link URL shape

- `SocialSchedulingService.__init__` gains `public_base_url: str` (default
  `http://localhost:4040`), stored as `self._public_base_url` (trailing slash
  stripped defensively).
- `_link_view` builds the payload from the **link code**, not the token:
  ```python
  qr_payload=f"{self._public_base_url}/u/{code}" if code else None,
  ```
  `code` is already fetched in `_link_view` when `include_public=True`. The
  `public_token` remains available for the authenticated join path.

This is the single change that fixes the copied-link string.

### 3. Backend — public link-resolution endpoint

**Service** (`coke/domains/social_scheduling/service.py`):

- New value object `PublicFriendLinkView` (in `models.py`) with
  `link_code: str`, `status: str` (`"active"`), `owner_display_name: str`.
- New method:
  ```python
  def resolve_public_friend_link(self, link_code: str) -> PublicFriendLinkView | None
  ```
  - Look up by `get_friend_link_by_code_hash(_hash_token(link_code))`.
  - Return `None` when the link is missing or `lifecycle != "active"`.
  - Resolve the owner name via `self.display_name_resolver(owner_account_id)`.

**Route** (`coke/api/public_friend_routes.py`, new):

- `create_public_friend_blueprint(social_scheduling_service)` with
  `url_prefix="/api/public/user-links"`. **Unauthenticated.**
- `GET /<code>`:
  - On hit → raw body
    ```json
    {
      "code": "<link_code>",
      "status": "active",
      "profile": { "displayName": "<name>", "tagline": null, "avatarUrl": null }
    }
    ```
    HTTP 200.
  - On miss → `SocialSchedulingError("friend_link_not_found")` →
    `{ "error": { "code": "friend_link_not_found" } }`, HTTP 404.
- Register the blueprint in `coke/app.py` alongside the others.

Raw bodies (no `{ok, data}` envelope) keep the endpoint consistent with the
rest of the coke Flask backend (`customerApi` returns parsed bodies directly).
The error-handler maps `friend_link_not_found` to **404** for this blueprint
(the landing page treats any non-200 as "link not active").

### 4. Web — align landing + completion to direct join

**`web/lib/user-link-api.ts`** — reduce to a single function:

- Keep `fetchUserLink(code)`, rewritten to consume the **raw body**: 200 →
  `{ ok: true, data: { code, status, profile } }`; any non-200 →
  `{ ok: false, error: 'link_not_active' }`.
- **Delete** `openLinkSession`, `getLinkSessionStatus`, `createFriendship`,
  and the session/friend-request helpers — retired-gateway legacy.

**`web/lib/api-types.ts`** — delete now-unused types:
`PublicLinkSessionResponse`, `PublicLinkSessionStatusResponse`,
`DirectFriendshipResponse`. Keep `PublicUserLinkResponse` (used by the landing
page).

**`web/app/u/[code]/page.tsx`**:

- Drop the `openLinkSession` call and the `link_session` query handling.
- Render owner profile + QR (`/u/{code}/qr`, already correct).
- Show "Log in to add friend" / "Create account to add friend" linking to
  `/auth/login` and `/auth/register` (the existing auth routes) with
  `next=/account/friends?join=<code>` (the `link_code`).

**`web/lib/customer-friends.ts`**:

- Add `joinFriendByCode(code: string)` → `POST /api/friends/join` with body
  `{ link_code: code }`, returning the friendship result.

**`web/app/(customer)/account/friends/page.tsx`**:

- Replace the `link_session` / `inviteToken` / `getLinkSessionStatus` /
  `createFriendship` / `linkSession` state with a one-shot **join-by-code**:
  - Read `?join=<code>`.
  - After the page confirms an authenticated session (existing
    `AUTH_ERRORS → loginNextPath` flow, with `next` carrying `?join=<code>`),
    call `joinFriendByCode(code)` once.
  - Surface the result: established → success notice; deferred (joiner has no
    usable channel yet) → an "added once you connect a channel" notice; error →
    failure notice. Then scrub `join` from the URL.
- The owner's link panel keeps using `friendLink.url`, now correct.

### 5. Docs and issue record

- `docs/issues/2026-06-01-friend-link-prefix.md` — incident: the four-way
  defect, affected surfaces, fix commit(s), verification.
- `docs/deploy.md` — document the required `COKE_PUBLIC_BASE_URL` env
  (production value `https://coke.keep4oforever.com`).
- `docs/product-specs/FEATURE_TREE.md` — add `GET /api/public/user-links/{code}`
  and the public-link → join flow.

## Data flow (after fix)

```
Owner: GET /api/friends/link
  → qr_payload = {COKE_PUBLIC_BASE_URL}/u/{link_code}     (copied link)

Stranger opens {host}/u/{link_code}
  → web GET /api/public/user-links/{link_code}
  → { code, status:"active", profile:{ displayName, null, null } }
  → renders owner + QR + auth CTAs (next=/account/friends?join={link_code})

Stranger logs in / registers, lands on /account/friends?join={link_code}
  → POST /api/friends/join { link_code }
  → establish_friendship_from_code → friendship created, or deferred if the
    new account has no usable channel yet (completes on channel connect)
```

## Error handling

- Missing/disabled link, public endpoint → 404 → landing page "link not
  active" panel.
- `COKE_PUBLIC_BASE_URL` unset in production → `ConfigurationError` at startup.
- Join when unauthenticated → existing `AUTH_ERRORS` redirect to login with the
  `join` code preserved in `next`.
- Join when the joiner has no channel → deferred result, not an error; surfaced
  as an informational notice.
- Self-join (owner opens own link) → `self_friendship_forbidden`, surfaced as a
  friendly notice rather than a hard failure.

## Testing

**Backend (pytest):**

- `Settings` / config: `COKE_PUBLIC_BASE_URL` default, trailing-slash strip,
  production-required guard.
- `SocialSchedulingService`: `qr_payload` shape `{base}/u/{link_code}`;
  `resolve_public_friend_link` for active / disabled / missing links.
- Public route: 200 raw body shape; 404 on unknown/disabled code.
- Update `test_social_scheduling_tool_adapter.py` /
  `test_social_scheduling_routes.py` fixtures that assert the old
  `coke.example/friends/...` payload.

**Web (pnpm test):**

- `user-link-api.test.ts`: `fetchUserLink` raw-body handling (200 + non-200).
- `app/u/[code]/page.test.tsx`: profile render + auth CTAs with `join` next.
- `account/friends/page.test.tsx`: join-by-code success / deferred / error.
- `customer-friends.test.ts`: `joinFriendByCode`; corrected `url` shape.

**Smoke:**

- The friendship / first-contact paths are covered by the `coke-agent-smoke`
  harness. The public-link → join browser flow is verified manually against the
  real web deploy as part of rollout.

## Affected files

- `coke/config.py`
- `coke/composition.py`
- `coke/domains/social_scheduling/service.py`
- `coke/domains/social_scheduling/models.py`
- `coke/api/public_friend_routes.py` (new)
- `coke/app.py`
- `web/lib/user-link-api.ts`
- `web/lib/api-types.ts`
- `web/lib/customer-friends.ts`
- `web/app/u/[code]/page.tsx`
- `web/app/(customer)/account/friends/page.tsx`
- tests for each surface above
- `docs/issues/2026-06-01-friend-link-prefix.md`, `docs/deploy.md`,
  `docs/product-specs/FEATURE_TREE.md`
