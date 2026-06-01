---
title: Public friend links copied with placeholder host and retired route
date: 2026-06-01
status: resolved
kind: incident
surface: social-scheduling
---

# Public friend links copied with placeholder host and retired route

## What Happened

Copied friend links used `https://coke.example/friends/{public_token}`. That
host was a test placeholder, the path did not exist in the web app, and the
identifier was the private `public_token` instead of the public landing
`link_code`.

## Why It Mattered

The current product requirement says friend links must be openable. The broken
string prevented strangers from opening the public profile landing page and
starting the authenticated friendship flow.

## Affected Surfaces

- `SocialSchedulingService._link_view`
- `/api/friends/link`
- `/u/[code]`
- `/api/public/user-links/{code}`
- `/account/friends?join={code}`
- production deploy env

## Resolution

The implementation now builds backend friend links from `COKE_PUBLIC_BASE_URL`
and `/u/{link_code}`, exposes an unauthenticated public resolver for active
reachable friend links, and routes the web flow from the public landing page to
`/account/friends?join={code}` for direct clean-backend joining. Production
deployment configuration now carries
`COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com`, so production startup
does not silently create localhost friend links.

## Verification

Final verification for the full public friend-link change set:

- `.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/test_social_scheduling_tool_adapter.py -v`
  passed: 85 tests.
- `cd web && pnpm test lib/user-link-api.test.ts lib/customer-friends.test.ts 'app/u/[code]/page.test.tsx' 'app/(customer)/account/friends/page.test.tsx' lib/i18n.test.ts`
  passed: 33 tests.
- `zsh scripts/suggest-verification --base HEAD~1` completed and suggested
  `zsh scripts/verify-surface repo-os-docs` for the final evidence commit.
- `zsh scripts/review-trigger --base HEAD~1` completed with no human review
  required; it reported the final issue-record edit as a medium repo-OS risk.
- `PATH="$PWD/.venv/bin:$PATH" zsh scripts/verify-surface clean-rebuild-backend`
  passed: 732 tests.
- `zsh scripts/verify-surface clean-rebuild-web` passed: 217 tests and
  `pnpm build`.
- `zsh scripts/verify-surface deploy` passed.
- `zsh scripts/verify-surface repo-os-docs` passed.
- `git diff --check` passed.
