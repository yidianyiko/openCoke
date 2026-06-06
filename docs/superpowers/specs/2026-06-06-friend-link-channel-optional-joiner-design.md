---
title: Friend-link join without joiner channel
date: 2026-06-06
status: approved
kind: design
topic: friend-link-channel-optional-joiner
---

# Friend-link join without joiner channel

## Problem

The current clean SocialScheduling contract requires both sides to have a usable
personal channel before an active friendship can be established through a friend
link. In practice this creates a poor web-first flow:

1. A new user opens a public friend link.
2. The user registers or logs in.
3. The friends page calls `POST /api/friends/join`.
4. If the joining user has no usable channel, SocialScheduling returns
   `status="deferred_channel_required"` and no `friendship` row is written.
5. The friends page removes `?join=...`, leaving the user with no friend in the
   friend list and no durable completion state.

This behavior matched the earlier channel-centric design in
`docs/superpowers/specs/2026-06-01-public-friend-link-design.md`, but it no
longer matches the product requirement. A logged-in or claimed Coke user should
be able to add the friend immediately. Channel connection is still required
before chat delivery, reminders, and shared-reminder participant delivery can
work, but it should not block the friendship relationship itself.

## Approved Scope

Use Option A:

- The friend-link owner still must have a usable channel to create, publish, and
  resolve a public friend link.
- The joining user no longer needs a usable channel to establish an active
  friendship.
- The joining user must still be authenticated as a Coke account or have claimed
  an existing messaging-first account. Public anonymous join remains out of
  scope.
- Shared reminders, notifications, reminder delivery, and conversation replies
  continue to enforce their own channel reachability rules. An active friendship
  does not imply current reachability.

## Goals

- `POST /api/friends/join` creates an active friendship when the joining account
  has no usable channel.
- Existing active friendships remain idempotent and return `already_active`.
- Self-friendship remains forbidden.
- Friend-link owner reachability remains required.
- The friends page treats friend-link join as successful when the backend returns
  `created` or `already_active` and refreshes the friend list.
- New code and tests carry the current product contract only; the normal join
  path no longer depends on deferred friend-link completion.

## Non-goals

- Letting channel-less owners issue or publicly resolve friend links.
- Adding pending friend request or approval states.
- Allowing shared reminders to bypass participant channel checks.
- Changing onboarding-complete semantics; web-first onboarding still requires a
  usable channel and first inbound message.
- Migrating or backfilling historical users who previously received
  `deferred_channel_required`; this change affects future join attempts.

## Design

### SocialScheduling

`SocialSchedulingService._establish_from_link(...)` remains the single domain
path for friend-link establishment by token or link code. Its new sequence is:

1. Reject inactive links with `friend_link_disabled`.
2. Require the owner account to have a usable channel with
   `owner_channel_required`.
3. Reject self-friendship with `self_friendship_forbidden`.
4. Check for an existing active friendship and return `already_active` if one
   exists.
5. Create a new active `friendship` row and `friendship_created` notification
   fact.

The joiner reachability check is removed from this path. The active friendship
is a relationship fact, not a proof that both participants can currently receive
messages.

`establish_friendship_from_token(...)` and
`establish_friendship_from_code(...)` keep their public signatures. Their normal
results become `created` or `already_active`.

### Deferred Completion

The previous `deferred_channel_required` result and
`complete_deferred_friend_link(...)` path are not part of the new normal web
join behavior.

Implementation should remove stale deferred behavior where it is no longer
needed by current callers and tests. If an endpoint or adapter cannot be removed
cleanly in the first implementation slice, it must be left unreachable from the
normal join path and documented as obsolete follow-up, not preserved as an
alternate current product contract.

### API

`POST /api/friends/join` continues to accept either `public_token` or
`link_code`, derive `joiner_account_id` from the authenticated customer session,
and return:

```json
{
  "status": "created",
  "friendship_id": "<friendship-id>",
  "continuation": {}
}
```

or:

```json
{
  "status": "already_active",
  "friendship_id": "<friendship-id>",
  "continuation": {}
}
```

It should not return `deferred_channel_required` for an authenticated joiner who
lacks a channel.

Existing route errors remain:

- `unauthorized` from the customer account gate.
- `invalid_request` for missing/invalid token and code fields.
- `friend_link_not_found` or `friend_link_disabled` for missing/inactive links.
- `owner_channel_required` when the link owner is no longer reachable.
- `self_friendship_forbidden` when the joiner opens their own link.

### Web

`joinFriendByCode(...)` can keep a temporarily broad response type while backend
and web tests are updated, but the customer friends page should no longer treat
`deferred_channel_required` as the expected no-channel join outcome.

When the auto-join effect receives `created` or `already_active`, it shows the
normal success notice, refreshes the friend list, and strips `?join=...`.

If old deployed backend code returns `deferred_channel_required` during a rolling
deploy, the page may keep a defensive fallback message, but this fallback is not
the current product contract and should not drive new tests.

## Data Flow

```text
public /u/:code
  -> login/register/claim if needed
  -> /account/friends?join=:code
  -> POST /api/friends/join { link_code }
  -> SocialScheduling creates active friendship
  -> GET /api/friends refreshes list
```

Later channel connection is independent:

```text
channel connection
  -> ChannelReachability marks route usable
  -> future conversations/reminders/shared reminders can use the route
```

## Error Handling

Friendship creation failure must report the product reason rather than silently
falling back to an empty friend list. In particular:

- A channel-less joiner is not an error.
- A channel-less owner is an error because the public link should no longer be
  considered actionable.
- Shared reminder creation can still reject an active friend if that friend has
  no usable channel at scheduling time.

## Tests

Backend TDD starts by replacing the stale service expectation:

- A joiner with no usable channel can join an owner with a usable channel.
- The result is `created`.
- Both participants see each other in `list_friends(...)`.
- No deferred continuation is returned.

Then update route and web tests:

- `/api/friends/join` serializes `created` with a real friendship id for a
  channel-less joiner.
- The friends page success path refreshes the friend list for this result.
- Existing owner-channel, self-friendship, duplicate-active, and removal tests
  still pass.

Verification should include:

- `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`
- `web/app/(customer)/account/friends/page.test.tsx`
- Diff-aware verification routing with `zsh scripts/suggest-verification --base
  HEAD~1` and `zsh scripts/review-trigger --base HEAD~1`.

## Documentation Updates

Update `docs/product-requirements/current.md` so the Friendship requirement says
that active friendship creation requires an authenticated or claimed Coke user,
but does not require the joining user to already have a usable channel.

The requirement should keep the owner-side rule: only users with a usable
personal channel may issue or publicly expose friend links.

