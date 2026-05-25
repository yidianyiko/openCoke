---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: smoke-design
---

# Friend management edge cases smoke - hunt design

## Why

Friend management is the gateway to Coke's multi-user features: shared
reminders, coach booking, and friend calendar facts all assume the friend graph
is correct and privacy-preserving. Existing smoke coverage mainly exercises the
happy path: Alice generates a link, Bob accepts, and the friendship becomes
active.

This smoke is a discovery hunt for friend-management edge cases users hit in
real flows: declining, cancelling, listing, removing, re-friending, self-link
claims, duplicate link submits, expired sessions, invalid codes, calendar access
after removal, display-name ambiguity, and retired account-control wording. That
account-control surface was retired in commits `af48532` and `763a22af`; this
hunt verifies it stays absent. The hunt produces evidence only. It does not fix
product code.

## Setup

- 3 fresh accounts in one batch:
  - `Alice Friend`
  - `Bob Friend`
  - `Carol Friend`
- Default display names are unique. FM-11 creates a controlled duplicate-name
  branch for Carol.
- LLM model stays `GLM-5.1 thinking-off`; do not swap model/provider.
- Before running the batch, verify bridge/gateway health per
  `.claude/skills/coke-agent-smoke/SKILL.md`. If the stack is down, stop as
  `BLOCKED-SETUP`.
- Setup helper primitives:
  - Provision accounts with `provision_account`.
  - Send chat turns with `send_as`.
  - Generate Alice's link through the agent first; use the internal
    `get_user_link` tool only as a setup fallback and record that fallback.
  - Create public link sessions only for cases that need session semantics
    such as expiry or same-session retry.
- Baseline assertion before cases run: no `friend_requests` or `friendships`
  rows exist for the batch accounts.

If setup fails, the runner records one `BLOCKED-SETUP` result and runs no cases.

## Cases

Cases run in this order so state builds naturally and destructive cases come
after list/assertion coverage. Each case snapshots before and after execution.

| # | Case | Turns / setup | Expected behavior | product_contract_unclear |
| - | ---- | ------------- | ----------------- | ------------------------ |
| FM-01 | Decline incoming friend request | Bob sends Alice a request via Alice link. Alice: `拒绝 Bob 的好友请求` | Exactly one `friend_requests` row moves to `rejected`; no active `friendships` row; Bob may receive a notification, but neither side should see a friendship. | false |
| FM-02 | Cancel sent friend request | Alice sends Bob a request via Bob link. Alice: `撤回我刚才发给 Bob 的好友申请` | Pending request moves to `cancelled`; Bob cannot accept it afterward; no friendship row appears. | false |
| FM-03 | List my friends | Create Alice-Bob active friendship. Alice: `我有哪些好友` | Agent calls friend-list path; reply reflects Bob only; `friendships` delta is empty. | false |
| FM-04 | List pending requests | Carol sends Alice a request; Alice asks `我的好友申请` | Agent calls request-list path; reply mentions Carol's pending request and does not include terminal requests from FM-01/FM-02 as actionable. | false |
| FM-05 | Remove friend | With Alice-Bob active. Alice: `删除好友 Bob` | Active friendship moves to `removed`; pending shared reminders tied to that friendship are invalidated if present; accepted historical shared reminders are not silently rewritten. | false |
| FM-06 | Re-friend after remove | After FM-05, Bob sends Alice a fresh request through a new or active Alice link; Alice accepts. | A new pending request can be accepted; one active friendship exists for Alice-Bob. Removed history is not resurrected as active by retrying the old accept action. | false |
| FM-07 | Friend self | Alice tries Alice's own link code/session. | Gateway/tool returns self-friend error; agent refuses clearly; no `friend_requests` or `friendships` rows added. | false |
| FM-08 | Same link used twice | Bob submits Alice's link twice before Alice acts, using the same public session or same user-link code. | Idempotent result: one pending request, no duplicate notification storm, second submit points at the existing pending request or replies that it is already pending. | false |
| FM-09 | Invalid link code | Bob: `我想加好友，邀请码是 not-a-real-code-...` | No friend request created; reply says the link/code is invalid or unavailable without inventing a target profile. | false |
| FM-10 | Retired account-control wording | Alice has Bob as friend. Alice: `屏蔽 Bob` and later `解除对 Bob 的屏蔽` | No friend or request state changes. Assistant must refuse or redirect without presenting account-control as an available Coke feature and without adding new data-table expectations. | false |
| FM-11 | Friend with same display name | Normal path: attempt to provision Carol with Bob's display name. Drift branch: if direct fixture seeding creates duplicate Bob names, Alice tries `删除好友 Bob` or calendar lookup by `Bob`. | Normal path rejects duplicate display name. Drift branch fails closed with ambiguity and no write/read leak; it must not pick one Bob silently. | false |
| FM-12 | View friend calendar after remove | Alice and Bob were friends, then Alice removes Bob. Alice: `看看 Bob 这周哪些时间空` | Calendar facts require active friendship; request is refused with no Bob reminder titles or busy metadata leaked. | false |
| FM-13 | Update display name and check other side's view | Alice-Bob active. Mutate Bob's customer display name to `Bobby Friend` through the supported profile surface if available, otherwise controlled Postgres fixture update. Alice: `我有哪些好友`; then old-name and new-name actions. | Friend list shows the current name, not a stale snapshot. New name resolves. Old name should either fail closed or ask for clarification; silent action against stale Bob is a finding. | true |
| FM-14 | Expired public link session | Create Alice public link session, then expire the session in Postgres before Bob submits it. | Public session claim returns expired; no friend request appears. If the chat user-link-code path is used instead, mark case `BLOCKED` because active user links do not model session expiry. | true |

## Per-case execution model

For each case:

1. Snapshot Mongo collections filtered by batch accounts where possible:
   `agent_sessions`, `inputmessages`, and `outputmessages`.
2. Snapshot Postgres tables filtered by the batch accounts:
   `customers`, `identities`, `user_links`, `link_sessions`,
   `friend_requests`, `friendships`, `shared_reminder_requests`,
   `reminder_projections`, `product_notifications`, and `delivery_routes`.
3. Run the case's setup and 1-3 user turns. Public link-session cases may call
   gateway HTTP routes directly to create or claim a session, but must still
   record any agent-visible turn used in the case.
4. Snapshot Mongo and Postgres again.
5. Compute deltas and evaluate per-case assertions:
   - expected row count and status transitions;
   - no duplicate active friendships for a pair;
   - no duplicate pending friend requests for a pair;
   - no durable write when expected behavior is refusal or clarification;
   - no friend calendar read without active friendship;
   - no reply claim of a write unless the DB confirms it.
6. Save transcript turns, DB deltas, tool trace excerpts, verdict, and
   `product_contract_unclear`.

Verdicts:

- `PASSED`: visible reply, tool trace, Mongo delta, and Postgres delta all match
  the case expectation.
- `FINDING`: the assistant, gateway, or DB state diverges from expectation.
- `BLOCKED`: setup, stack health, auth/provisioning, or unrelated gateway
  failure prevents the case from exercising the target behavior.

A finding does not stop the batch unless it corrupts a shared precondition. If
that happens, mark dependent cases `BLOCKED` and keep the original finding.

## Findings JSON shape

Write one JSON file per batch under
`artifacts/evidence/shared-reminder-agent-smoke/`:

- `friend-management-edge-<batch>.json`

```json
{
  "batch_id": "friend-management-edge-20260526t120000Z",
  "model": "GLM-5.1 thinking-off",
  "case_id": "FM-08-same-link-used-twice",
  "verdict": "FINDING",
  "bug_pattern": "FR2",
  "severity": "silent-bad-side-effect",
  "product_contract_unclear": false,
  "accounts": {
    "alice": {"coke_account_id": "ck_smoke_...", "display_name": "Alice Friend ..."},
    "bob": {"coke_account_id": "ck_smoke_...", "display_name": "Bob Friend ..."},
    "carol": {"coke_account_id": "ck_smoke_...", "display_name": "Carol Friend ..."}
  },
  "expected": "second submit reuses the existing pending request",
  "observed": "two pending friend_requests rows were created for Bob -> Alice",
  "turns": [
    {
      "speaker": "bob",
      "input_text": "我想加好友。这是对方的邀请码：AbCd...",
      "reply_text": "...",
      "elapsed_ms": 12345,
      "output_id": "..."
    }
  ],
  "postgres_delta": {
    "friend_requests": {"added": 2, "modified": 0, "removed": 0, "before": [], "after": []},
    "friendships": {"added": 0, "modified": 0, "removed": 0}
  },
  "mongo_delta": {
    "outputmessages": {"added": 1},
    "agent_sessions": {"modified": 1}
  },
  "agent_trace_excerpt": {
    "tool": "scheduling_domain",
    "intent": "send_friend_request_by_user_link_code",
    "tool_result": {"ok": true}
  }
}
```

Reuse existing bug-pattern tags where they fit:

- `A`: raw envelope leak.
- `B`: empty fallback.
- `C`: hallucinated side effect.
- `D1`: bad scheduling tool arguments.
- `D2`: backend needs an id the agent cannot supply.
- `F`: causal id hijacked by product notification.

New friend-management tags:

- `FR1`: wrong friend request or friendship state transition.
- `FR2`: link/session idempotency, invalid-code, self-link, or expiry bug.
- `FR3`: display-name uniqueness, stale name, or ambiguous-name resolution bug.
- `FR4`: privacy/authorization leak across removed or non-existent friendship.
- `FR5`: retired account-control wording caused a write or product claim.
- `NEW`: use only when none of the above fits; include a one-line definition.

## What the hunt codex must NOT do

- Do not modify product code in `agent/`, `connector/`, `dao/`, or `gateway/`.
- Do not try to fix bugs found by the hunt.
- Do not swap the LLM model or thinking mode.
- Do not add account-control tools, routes, tables, prompt affordances, or
  compatibility shims.
- Do not weaken expected behavior after seeing failures.
- Do not treat assistant text as proof without Mongo/Postgres verification.
- Do not leak Bob's calendar/reminder details in case logs beyond the minimal
  DB evidence needed to prove authorization behavior.
- Do not push to origin without explicit human sign-off.

## Reviewable summary

- The hunt covers 14 friend-management edge cases across request lifecycle,
  friendship lifecycle, link/session failure modes, calendar authorization, and
  display-name resolution.
- It uses three accounts: Alice, Bob, and Carol, with a controlled duplicate-name
  branch for Carol.
- Every case is DB-first: assistant replies are hypotheses until Mongo and
  Postgres deltas confirm them.
- Product-unclear behavior is limited to display-name mutation and expired
  public link-session setup, because those depend on surfaces outside the chat
  friend-code happy path.
- Retired account-control wording is tested only as a no-write refusal surface;
  the hunt must not recreate that feature.
- New `FR*` bug-pattern tags extend the existing smoke taxonomy without
  replacing the shared tags A/B/C/D1/D2/F.
