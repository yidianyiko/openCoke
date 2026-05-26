---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: fix-design
---

# Friend management findings cluster - fix design

## Scope

This spec covers FM-01, FM-04, FM-10, FM-11, and FM-13 from
`artifacts/evidence/shared-reminder-agent-smoke/friend-management-edge-20260526t001527Z.json`.
No product code is changed here. Eventual work touches `worker-runtime` and
`gateway-api`, keeps `GLM-5.1 thinking-off`, adds no backwards-compat shims, and
does not reintroduce block/unblock account-control tools, routes, tables,
prompts, or UI affordances.

## 1. Layer trace per case

### FM-01 decline incoming

- Bob's setup turn attempted to send a friend request with tool arguments shaped
  as `{"intent": {"user_link_code": "...", "note": "FM01", "intent_name":
  "send_friend_request_by_user_link_code"}}`.
- `agent_runtime._normalize_scheduling_intent` did not recognize that shape as
  a scheduling intent and returned `scheduling intent could not be resolved`.
- No `friend_requests` row was created for Bob -> Alice.
- Alice's decline turn then called `reject_friend_request`, but gateway could
  not find a pending request by Bob and returned `friend_name_not_found`.

Primary root: worker-runtime intent normalization gap.
Secondary guard: gateway request resolver should still have direct tests for
decline-by-name once the setup request exists.

### FM-04 list pending

- Summary marks FM-04 as a finding with `reply_mentions_carol=False`.
- The trace excerpt in the same artifact shows `list_friend_requests` was called,
  the gateway returned Carol's pending request, and the assistant reply did
  mention `Carol Friend 26001527`.
- Current `gateway/packages/api/src/scheduling/friendship-service.ts` queries
  `friendRequest.findMany` for both requester and target sides.
- Current `agent/agno_agent/capabilities/scheduling.py` fallback summary only
  says the count of pending friend requests, not names.

Primary root: evidence inconsistency must be reconciled before a gateway list
query fix is accepted.
Minimal product hardening: make the deterministic friend-request summary include
current counterpart display names and actionable direction, so list-pending does
not depend on the final LLM mentioning Carol.

### FM-10 retired account-control wording

- `屏蔽 Bob` produced an unsupported `block_friend` intent and did not write.
- `解除对 Bob 的屏蔽` produced `{"operation": "remove_block", "friend_name":
  "Bob"}`. The inner scheduling worker then executed `remove_friendship`.
- Postgres changed the active Alice-Bob friendship to `removed`.
- The assistant claimed account-control behavior even though block/unblock was
  retired in `af48532` / `763a22af`.

Primary root: worker-runtime retired-intent guard missing.
Required behavior: block/unblock wording is refused or redirected as an
unsupported retired surface with no scheduling gateway mutation.

### FM-11 same display name

- Normal duplicate display-name creation was rejected.
- In the forced duplicate-name branch, Alice asked for Bob availability.
- Gateway returned calendar facts for one matching account and the assistant
  leaked availability instead of failing closed for ambiguity.
- The case also recorded friend writes, but part of the precondition was already
  contaminated by FM-10 removing Alice-Bob friendship. FM-11 must be rerun after
  FM-10 is fixed to separate true ambiguity behavior from prior state damage.

Primary root: gateway resolver primitive is missing or insufficiently enforced
for all friend-side read/write operations.
Secondary root: FM-10 state pollution may have hidden a second active Bob from
the resolver, so verification must include a clean duplicate-active-friend unit
case.

### FM-13 display-name update

- Bob's display name changed from `Bob Friend ...` to `Bobby Friend ...`.
- `Bobby Friend` calendar lookup resolved.
- Old-name lookup for `Bob` still resolved to Bobby because current resolver
  uses substring matching.
- `我的好友` first called `list_friend_calendar_facts` with an empty friend name,
  failed, then tried `list_friends`; the runtime returned the cached first
  scheduling result, so the list never refreshed.

Primary roots:

- Gateway resolver matching must be token-boundary based, not arbitrary
  substring based.
- Worker runtime should preselect `list_friends` for explicit friend-list
  requests so the model cannot call calendar facts first.

## 2. Root cause

This cluster is not N fully independent bugs, but it is also not solved by one
resolver alone.

One missing gateway primitive should resolve friend-side names for friend
request actions, friendship removal, friend calendar facts, shared-reminder
friend filters, and shared-reminder invitee lookup. It must be scoped by
operation type and actor role, read current Postgres profile rows, fail closed
for zero matches, ambiguous matches, inactive friendships, and role mismatch,
and never perform writes while resolving.

That primitive addresses FM-11 and the resolver part of FM-13, and gives FM-01
and FM-04 stable gateway-side tests. Two worker-runtime bugs remain:
retired account-control wording can reach mutation tools (FM-10), and
normalization/preselection misses valid model shapes or explicit list requests
(FM-01, FM-13).

## 3. Proposed fixes

### A. Gateway friend-side resolver primitive

Add a small gateway module, for example
`gateway/packages/api/src/scheduling/friend-target-resolver.ts`, with typed
entry points for pending friend-request actions, active friendship mutations,
active-friend reads, and shared-reminder friend lookup. Replace route-local
`resolveFriendRequestId`, `resolveFriendshipId`,
`resolveFriendAccountIdForLookup`, and `resolveInviteeAccountId` matching logic
with that shared resolver.

Matching policy:

- Normalize case and whitespace.
- Exact normalized display-name match wins only if unique.
- Token-boundary display-name match may resolve short names like `Bob` to
  `Bob Friend 26001527`.
- Arbitrary substring match is forbidden: `Bob` must not match `Bobby`.
- If more than one candidate matches at the selected strength, return
  `friend_name_ambiguous`.
- If no candidate matches, return `friend_name_not_found` or
  `friend_not_found` using existing public error names where possible.

Operation policy: accept/reject only target-owned pending requests; cancel only
requester-owned pending requests; active-friend operations only use active
friendships involving the actor. Keep explicit ids only for trusted internal
payloads, still validating actor ownership and status in the service layer.

### B. Deterministic friend-request list summary

Update the agent scheduling capability summary for `list_friend_requests` so a
successful list includes current counterpart names and direction: incoming
pending requests, outgoing pending requests, and optional terminal requests
clearly marked as not actionable. This is presentation hardening only; it must
not add query paths or mutate request state.

### C. Retired account-control guard

Add an unsupported-account-control detector before preselected scheduling
execution. It triggers on `屏蔽`, `拉黑`, `解除屏蔽`, `取消屏蔽`, `block`, and
`unblock` when used as account-control wording, returns a no-write result or
direct refusal, and prohibits `remove_friendship` for those turns. The reply may
suggest `删除好友` only if the user actually wants removal. Do not add retired
account-control aliases, tables, routes, or compatibility handlers.

### D. Scheduling intent normalization and preselection

Normalize common model-produced scheduling shapes without creating broad
compatibility shims: recognize nested `intent_name`, `tool_name`, `name`,
`operation`, or `action` only when the value is a current scheduling intent;
preserve current forced args (`user_link_code`, `friend_name`, `requester_name`,
`target_name`, `message`); map `note` to send-request `message`; and reject
retired account-control operations.

Preselection should route explicit friend-list requests to `list_friends`,
pending friend-request list requests to `list_friend_requests`, and friend
availability requests to `list_friend_calendar_facts`. For preselected turns,
avoid letting a first wrong model tool call cache a different scheduling result
for the rest of the turn.

## 4. Risk analysis

No block regression:

- Remove account-control wording from the mutation path; do not revive retired
  block behavior.
- `rg "block_account|unblock_account|blockAccount|unblockAccount|account_blocks"`
  after implementation must show only historical docs/migrations/issues, not new
  live code.

Passing cases to preserve:

- FM-02 cancel sent request: cancel-by-name still resolves a pending outgoing
  request.
- FM-03 list friends: list still reads active friendships and shows current
  names.
- FM-05 remove friend and FM-06 re-friend: removal remains available only for
  explicit remove/delete-friend wording, not account-control wording.
- FM-07 self-link, FM-08 idempotent link claim, FM-09 invalid link, FM-12
  calendar after remove, and FM-14 expired link session must remain unchanged.

- Too strict matching could break natural smoke phrases like `Bob` for
  `Bob Friend 26001527`; token-boundary matching preserves that.
- Too loose matching leaks or mutates the wrong friend; arbitrary substring
  matching must be removed.
- Ambiguity errors are product-visible. They should ask the user to choose, and
  they must not include private calendar or reminder details.
- Prompt-only retirement is insufficient because the model can still emit a
  mutation-shaped intent.
- Normalizing too many aliases becomes a compatibility shim. Only normalize
  current tool names and current argument names.
- FM-04 evidence disagreement means implementation should not delete or rewrite
  working gateway list behavior based only on the summary field.

## 5. Verification plan

Unit tests:

- Python worker-runtime: nested `intent_name=send_friend_request_by_user_link_code`
  normalizes with `user_link_code` and `message`; block/unblock wording does not
  preselect or execute `remove_friendship`; `我的好友` preselects `list_friends`;
  `我的好友申请` preselects `list_friend_requests`.
- Gateway resolver: `Bob` matches `Bob Friend 26001527`; `Bob` does not match
  `Bobby Friend 26001527`; duplicate active Bob matches return
  `friend_name_ambiguous`; ambiguity causes no write or calendar runtime read;
  request actions resolve only pending requests in the correct actor role; list
  friend requests returns current requester/target names.

Hunt rerun:

- Re-run friend-management edge with `GLM-5.1 thinking-off`.
- Required pass set: FM-01, FM-04, FM-10, FM-11, FM-13.
- Regression pass set: FM-02, FM-03, FM-05, FM-06, FM-07, FM-08, FM-09, FM-12,
  FM-14.
- Store fresh evidence under
  `artifacts/evidence/shared-reminder-agent-smoke/friend-management-edge-<timestamp>.json`.

Diff-aware routing: run `zsh scripts/suggest-verification --base HEAD~1`,
`zsh scripts/review-trigger --base HEAD~1`, and for this spec-only commit
`zsh scripts/check`.

## Reviewable summary

- The cluster needs one shared gateway friend-side resolver, but that resolver
  is not enough by itself.
- FM-01 is mainly worker-runtime normalization; FM-10 is a retired-intent guard;
  FM-11 and part of FM-13 need a fail-closed resolver; FM-13 also needs
  deterministic list preselection.
- FM-04's latest artifact has an internal trace/summary disagreement, so the
  fix should harden deterministic summaries and rerun evidence before claiming
  a gateway list-query bug.
- The implementation must not restore any block/unblock account-control surface.
