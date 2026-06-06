# Friend-Add Personalized Feedback Design

created_at: 2026-06-07
status: accepted
track: H

## Problem

Eva's friend-link web flow already creates direct active friendships and
preserves the `join` code through login, but the post-join notice is generic.
For a successful Oliver link join, the Friends page currently says
`好友已添加。` instead of naming the added counterpart.

The repair is display-copy focused. It must not reintroduce pending
accept/reject friendship state, and it must keep self-friendship, disabled
link, invalid link, and auth-handoff failures distinct.

## Options Considered

1. Extend `FriendshipResult` with counterpart identity.
   - Pros: the domain service owns the join outcome; API routes and agent tool
     facts get the same concrete identity; the web notice can render before or
     after refresh without inference.
   - Cons: changes the join-result contract and therefore requires API,
     adapter, web-wrapper, and canonical route-index updates.

2. Resolve the counterpart from the refreshed friend list in the web page.
   - Pros: smaller backend diff; uses existing friend-list display names.
   - Cons: the join response still lacks enough identity for UI feedback,
     success copy depends on a second request, and the required API/adapter
     test cannot prove the join result itself is sufficient.

3. Let `coke/api/friend_routes.py` enrich only HTTP responses from
   `list_friends`.
   - Pros: keeps the domain model unchanged.
   - Cons: puts product-result shaping in an adapter, duplicates friend-list
     lookup rules, and leaves the agent tool adapter without counterpart facts.

Recommendation: use option 1.

## Design

`FriendshipResult` gains `counterpart_account_id` and
`counterpart_display_name`. For friend-link joins, the counterpart is the link
owner from the joiner's perspective. `SocialSchedulingService._establish_from_link`
sets those fields for both `created` and `already_active` results using the
existing `display_name_resolver`. The direct friendship model remains
unchanged: a successful join creates or reuses an active `friendship` row.

`/api/friends/join` and `/api/friends/complete-deferred` serialize the new
fields as `counterpart_account_id` and `counterpart_display_name`. The
`SocialSchedulingToolAdapter` includes the same fields in tool facts for
`establish_friendship_from_token`, keeping chat/tool feedback consistent with
web feedback.

The web wrapper extends `CustomerFriendshipJoin` to include the new fields.
`web/app/(customer)/account/friends/page.tsx` builds notices from i18n
templates:

- `created`: `已成功添加 {name}` / `Added {name}.`
- `already_active`: `{name} 已经在你的好友列表中。` /
  `{name} is already in your friends list.`

The page still refreshes friend data after a successful join and still scrubs
the URL only when auth was not redirected. Error handling becomes explicit:

- auth/access errors keep the login handoff with `join` preserved
- `self_friendship_forbidden` shows the self-friendship copy
- `friend_link_disabled` shows disabled-link copy
- `friend_link_not_found` shows invalid-link copy
- other failures keep the general action-failure copy

## Contract And Docs

`docs/product-specs/FEATURE_TREE.md` should note that authenticated friendship
join responses include the added counterpart identity for feedback. No runtime
topology or product invariant changes are needed; the direct-active friendship
invariant in `docs/ARCHITECTURE.md` remains current.

## Tests

Backend tests should first fail on the missing fields:

- service unit coverage for `created` and `already_active` join results carrying
  counterpart account id and display name
- route coverage for `/api/friends/join` serializing those fields
- tool-adapter coverage for `establish_friendship_from_token` exposing the same
  facts

Web tests should first fail on the generic copy:

- wrapper coverage for preserving counterpart identity from `/api/friends/join`
- Friends page coverage for logged-out handoff preserving `join`
- Friends page coverage for logged-in auto-join showing personalized `created`
  and `already_active` notices

Verification will run the touched backend tests, the Friends page and wrapper
web tests, `pnpm build` if feasible, and diff-aware verification routing.
