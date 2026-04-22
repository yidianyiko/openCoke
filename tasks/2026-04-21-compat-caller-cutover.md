# Task: Compatibility Caller Cutover

- Status: Verified
- Owner: Codex
- Date: 2026-04-21

## Goal

Remove the remaining generic `/coke/*` compatibility entrypoints and paused
`/api/coke/*` auth compatibility endpoints while keeping the supported Coke
business payment flow working.

## Scope

- In scope:
  - removing legacy generic auth/channel wrapper pages under
    `gateway/packages/web/app/(coke-user)/coke/*`
  - removing the paused `gateway/packages/api/src/routes/coke-auth-routes.ts`
    compatibility router
  - moving remaining profile hydration from `/api/coke/me` to `/api/auth/me`
  - removing the `legacy-redirect-page` helper and empty wrapper directories
  - updating live operator docs and deployment script checks to point at the
    supported routes
  - broad web, API, deploy, repo-OS, and structure verification
- Out of scope:
  - removing Coke business payment surfaces such as `/coke/payment`,
    `/api/coke/subscription`, or `/api/coke/checkout`
  - rewriting historical docs or archived plans

## Touched Surfaces

- gateway-api
- gateway-web
- deploy
- docs
- repo-os

## Acceptance Criteria

- the legacy generic wrapper directories under
  `gateway/packages/web/app/(coke-user)/coke/` are removed, except for the
  supported `/coke/payment` business page
- `gateway/packages/api/src/routes/coke-auth-routes.ts` and
  `gateway/packages/web/components/legacy-redirect-page.tsx` are removed
- generic auth flows hydrate profile state from `/api/auth/me`
- live docs point users to `/auth/*` and `/channels/wechat-personal` instead of
  deleted legacy routes
- verification proves the repository no longer depends on the removed
  compatibility layers

## Verification

- `pytest tests/unit/test_no_compat_routes.py -v`
- `pnpm --dir gateway/packages/web test`
- `pnpm --dir gateway/packages/api test`
- `bash scripts/test-deploy-compose-to-gcp.sh`
- `pytest tests/unit/test_repo_os_structure.py -v`
- `zsh scripts/check`
