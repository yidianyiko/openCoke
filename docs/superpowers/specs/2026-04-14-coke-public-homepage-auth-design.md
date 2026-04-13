# Coke Public Homepage and Auth Separation Design

## Goal

Turn the web root into a public Coke product homepage, make Coke user sign-in and registration feel like part of the same product surface, and isolate the administrator console under `/dashboard` so normal users are no longer dropped into admin-oriented UI.

## Problem

The current Next.js app serves the admin dashboard at `/`, which makes the first user-visible page feel like a console instead of a product site. The Coke user auth flow exists under `/coke/*`, but its visual design is sparse and disconnected from the public-facing experience. The admin login lives at `/login`, which keeps the operator flow too close to the public entry points.

## Scope

This change covers the web frontend in the `gateway` submodule:

- Replace the root route with a public Coke homepage.
- Keep Coke user auth and account routes under `/coke/*`.
- Restyle Coke login and registration to share the public product language.
- Move admin routes under `/dashboard/*`.
- Update admin navigation and auth redirects to the new namespace.

This change does not alter backend authorization rules or Coke account lifecycle APIs. It is a routing and frontend UX separation project.

## User Experience

### Public visitors

- Visiting `/` shows a Coke marketing homepage instead of the admin dashboard.
- The homepage keeps the current public product story: hero copy, platform coverage, feature sections, architecture section, and beta call-to-action.
- The homepage header and hero include clear `Register` and `Sign in` calls to action that route to Coke user pages.
- Public copy remains multilingual by presenting Chinese and English together rather than introducing a full localization framework.

### Coke users

- `/coke/login` becomes a branded auth page with the same visual language as the public homepage.
- `/coke/register` uses the same layout system and clearly explains the onboarding sequence: register, verify email, then continue to `/coke/bind-wechat`.
- Existing Coke account flows such as email verification, password reset, renewal, and WeChat binding remain under `/coke/*`.
- Successful Coke user sign-in continues to land on `/coke/bind-wechat`.

### Administrators

- The admin application moves from `/` and root-level routes to `/dashboard`.
- The member login moves from `/login` to `/dashboard/login`.
- Other admin pages move under the same namespace, for example `/dashboard/conversations` and `/dashboard/settings`.
- No public homepage element links users to admin screens.

## Routing Model

### Public and Coke user routes

- `/` — public Coke homepage
- `/coke/login` — Coke user sign-in
- `/coke/register` — Coke user registration
- `/coke/verify-email`
- `/coke/forgot-password`
- `/coke/reset-password`
- `/coke/renew`
- `/coke/bind-wechat`

### Admin routes

- `/dashboard` — admin dashboard home
- `/dashboard/login` — admin member login
- `/dashboard/register` — admin workspace registration if still needed
- `/dashboard/onboard` — admin onboarding if still needed
- `/dashboard/conversations`
- `/dashboard/channels`
- `/dashboard/ai-backends`
- `/dashboard/workflows`
- `/dashboard/end-users`
- `/dashboard/users`
- `/dashboard/settings`

## Architecture

### Public surface

Add a dedicated root page in the Next.js app that renders a product homepage for Coke. The page should be self-contained and intentionally public-facing rather than derived from admin dashboard components. It should reuse global styles where helpful, but introduce a Coke-specific visual shell and section components so the auth pages can share the same design system.

### Shared Coke public/auth styling

Introduce a small set of reusable Coke public UI helpers or components inside the web package. The shared surface should provide:

- a branded header with public navigation
- a gradient or atmospheric hero background
- a content container used by auth pages
- bilingual supporting copy patterns

This keeps the homepage, sign-in page, and registration page visually consistent without mixing them with the admin dashboard component set.

### Admin namespacing

Move the existing admin route tree under a `/dashboard` segment. The dashboard layout remains responsible for client-side member auth checks, but all redirects and nav links must target `/dashboard/*`. The root path must no longer depend on admin auth state.

## Visual Direction

- Preserve the product-first tone of the existing public site.
- Use stronger Coke branding than the current neutral slate auth cards.
- Keep mobile behavior simple: stack into a single column with forms first and supporting content second.
- Keep bilingual copy readable by pairing Chinese and English in short blocks rather than duplicating long sections unnecessarily.

## Error Handling

- Coke login and registration continue to surface API errors inline.
- Admin dashboard pages still redirect unauthenticated members to `/dashboard/login`.
- Public pages do not require auth and should never read admin storage state to decide whether they can render.

## Testing Strategy

- Add or update web tests to prove the public homepage exposes Coke auth entry points.
- Add or update Coke auth page tests to assert branded entry points and destination links still exist.
- Add or update admin layout tests and route-oriented assertions to confirm admin redirects target `/dashboard/login`.
- Run focused Vitest coverage for changed web files and a production Next.js build for the web package.

## Risks

- The `gateway` code lives in a git submodule, so implementation must happen inside the submodule workspace rather than only in the parent repository.
- Moving admin routes can break internal links if any root-relative dashboard paths are missed.
- If existing operators rely on old root paths, they will need the new `/dashboard` path.

## Non-Goals

- No backend auth model rewrite.
- No new role system or server-side route guard.
- No full i18n framework rollout.
- No change to the Coke user post-login destination beyond keeping `/coke/bind-wechat`.
