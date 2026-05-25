---
title: Remove friendship did not resolve friend name
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - gateway/packages/api/src/routes/internal-scheduling-routes.ts
  - gateway/packages/api/src/routes/internal-scheduling-routes.test.ts
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t040856Z.json
---

# Remove friendship did not resolve friend name

## What Happened

In `remove_friendship` batch `20260525t040856Z`, Alice and Bob became active
friends and Alice created a pending shared reminder. Alice then said
`把 Bob 从我的好友里删了。`

The agent called `remove_friendship` with `friend_name=Bob`, but the gateway
returned `friendship_not_found`. Postgres still showed the friendship as
`active` and the shared reminder request as `pending_invitee_confirmation`.

## Why It Matters

The agent naturally has a display name, not a friendship id. Remove-friendship
must resolve the active friendship by friend name just like friend-request and
shared-reminder actions resolve user-facing references.

## Root Cause

The internal scheduling route passed only `friendship_id` to
`removeFriendship`. When the model supplied `friend_name`, the route sent an
empty friendship id and the service failed closed.

## Fix

`remove_friendship` now resolves an omitted `friendship_id` by listing active
friendships for the actor and matching `friend_name` against the other account's
display name. Ambiguous or missing matches still fail closed.

## Verification

- `pnpm --filter @clawscale/api test -- internal-scheduling-routes.test.ts`
- `git -C gateway diff --check && git diff --check`
