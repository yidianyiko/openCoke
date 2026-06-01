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

Completed surfaces in this task: production deploy environment documentation,
the product/API feature tree, the SocialScheduling ownership registry entry for
the public resolver route, and this incident record.

- `zsh scripts/check` passed for the final Task 5 repository-docs state after
  adding the required ownership registry route entry.
- `git diff --check` passed for the final Task 5 diff.
