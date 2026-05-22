---
kind: incident
status: resolved
surface:
  - gateway-web
created_at: 2026-05-22
updated_at: 2026-05-22
---

# 2026-05-22 Gateway Frontend Client Navigation Load Failure

## What Happened

The deployed gateway web frontend frequently showed the browser error page
`This page couldn't load` after clicking internal links such as Register,
Sign in, Demos, or customer-channel entry points. Directly opening the same
URLs returned 200 and rendered the page.

## Why It Matters

The failure made normal public-site and customer-auth navigation unreliable on
the production domain. It was not caught by direct HTTP route checks because
those checks did not exercise client-side navigation after hydration.

## Affected Surfaces

- `gateway/packages/web/components/locale-provider.tsx`
- `gateway/packages/web/app/public-site.css`
- Production gateway web container serving `https://coke.keep4oforever.com`

## Evidence

- Browser reproduction before the fix:
  - Home -> Register changed the URL to `/auth/register`, then showed
    `This page couldn't load`.
  - Playwright captured `PAGEERROR Failed to execute 'insertBefore' on 'Node'`
    and `PAGEERROR Failed to execute 'removeChild' on 'Node'`.
- The direct route check still returned 200, which narrowed the failure to the
  hydrated client navigation path rather than missing routes.
- Root cause: `LocaleProvider` imperatively removed the server-rendered
  `#locale-splash` node with `document.getElementById('locale-splash')?.remove()`.
  That node belongs to the React/Next DOM tree, so later app-router transitions
  tried to move or remove a node that was no longer a child.

## Current Status

Resolved and deployed as a narrow gateway-only hotfix.

## Resolution

- Fix commit in nested `gateway`: `047f77f Fix locale splash readiness`
- Production deployment: synced the two gateway web source files and rebuilt
  only the `gateway` compose service with `docker compose -f docker-compose.prod.yml up -d --no-deps --build gateway`.
- Runtime evidence after deployment:
  - `coke-gateway-1` recreated and healthy.
  - `http://127.0.0.1:4041/health` returned `{"ok":true,"version":"0.1.0"}`.
  - `http://127.0.0.1:8090/bridge/healthz` returned `{"ok":true}`.
  - Playwright verified Home -> Register, Home -> Sign in, Home -> Demos,
    Home -> WeChat setup, and Login -> Register without the `This page
    couldn't load` page or DOMException.
