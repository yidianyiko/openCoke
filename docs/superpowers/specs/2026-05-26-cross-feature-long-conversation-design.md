---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: smoke-design
---

# Cross-feature long-conversation flows smoke - hunt design

## Why

Previous hunts covered each feature surface in isolation:

- Coach booking, expressed through multi-user shared reminder coordination.
- Personal reminder CRUD, recurring reminders, and time edge cases.
- Friend management edge cases.

Real users chain features in one conversation, often over many turns. Bugs that
do not appear in single-feature hunts can surface only when reminder, friend,
shared-reminder, persona, and unsupported-capability turns share one live
conversation:

- The agent forgets an earlier seeded reminder when asked about it later.
- Backreferences such as `刚才那个提醒怎么样了` break after unrelated turns.
- Context pressure causes hallucinated facts in long conversations.
- One feature's state leaks into another feature's intent inference, for
  example `约 Mei` becoming friend-add when Mei is already a friend and the
  user wanted a shared reminder.
- Multi-friend coordination may create one request per invitee, refuse, or do
  something inconsistent.
- A tool result from turn 5 may be referenced in turn 20.
- Lazy state changes such as display-name updates may be missed many turns
  later.

This smoke is a discovery hunt. It should produce evidence and findings only.
It does not fix product code.

## Setup

- LLM model stays `GLM-5.1 thinking-off`; do not swap model/provider.
- Before any case, verify bridge and gateway health per
  `.claude/skills/coke-agent-smoke/SKILL.md`. If the stack is down, stop as
  `BLOCKED-SETUP`.
- Each case gets fresh accounts and an isolated batch id. Long flows reuse the
  same accounts only within that case so conversation memory, DB state, and
  tool traces are attributable.
- Single-user cases use one fresh account: `Alice Long`.
- Multi-user cases use fresh accounts with the case's semantic display names
  such as `Bob Long`, `Mei Long`, `Alex Long`, or `Carol Long`; names must be
  unique inside the case.
- Cases that require an existing friendship bootstrap it through the normal
  invite-link flow unless the case explicitly tests that bootstrap.
- Account timezone is the provisioned account's normal runtime timezone. Do not
  add cross-timezone cases.
- Cases assume late-reply auto-poll already exists in `bridge_client` from
  commit `ba5bc599`; placeholder replies are not final verdicts until late
  polling finishes.
- The runner writes one JSON file per batch under
  `artifacts/evidence/shared-reminder-agent-smoke/`:
  `cross-feature-long-<case-id>-<batch>.json`.

## Cases

| Case | Accounts | Turn sketch | Expected outcome | product_contract_unclear |
| ---- | -------- | ----------- | ---------------- | ------------------------ |
| L1 Reminder lifecycle full | 1 | T1 `每天 8 点提醒我喝水`; T2 list reminders; T3 `刚才那个提醒晚 10 分钟`; T4 ask status; T5 modify to 09:00; T6 unrelated persona question; T7 list; T8 complete the next occurrence; T9 ask `刚才完成的是哪个`; T10 cancel the remaining series; T11 ask `刚才那个提醒还在吗`; T12 list final state; T13 ask for DB-backed summary via natural wording; optional T14-T15 clarify if the complete/cancel target is ambiguous. | Recurring update keeps the same reminder id unless the current product explicitly creates a replacement. If recurring completion is supported, the occurrence is completed and the series state is coherent; if not, the agent must clarify/refuse with no destructive write. Final list must not show cancelled reminders as active. Backreferences must target the correct prior reminder. | true |
| L2 Mixed reminder types | 1 | T1 create one-shot `明天 9 点交报告`; T2 create daily `每天 8 点喝水`; T3 create weekly `每周三 14 点复盘`; T4 list all; T5 modify the daily one to 08:30; T6 unrelated chat; T7 `删掉交报告那个`; T8 list all; T9 ask `每周三那个还在吗`; T10 ask `喝水现在几点`; T11 delete by fuzzy name; T12 final list. | One-shot, daily, and weekly reminders remain distinct. Fuzzy delete affects only the intended reminder. The daily update does not modify the weekly reminder. Final state matches Mongo `reminders`. | false |
| L3 Long context with backreference | 1 | T1-T10 create ten distinct reminders with unique titles and times; T11-T18 interleave list, persona, unsupported ask, and status questions without writes; T19 `我刚才设的第一个提醒是几点`; T20 `最后一个呢`. | The answer identifies the first and last reminders from conversation history or DB, not invented times. No extra reminders are created during read-only turns. | false |
| L4 Friend + shared reminder bootstrap | 2 | Alice T1 generates invite link; Bob T2 accepts through link/chat path; Alice T3 accepts friend request; Alice T4 `约 Bob 明天 10 点喝咖啡`; Bob T5 accepts shared reminder; Alice T6 asks calendar facts; Bob T7 asks same fact; Alice T8 modifies to 10:30; Bob T9 asks `刚才那个改了吗`; Alice T10 final list. | Friend graph becomes active, one shared reminder request is accepted, both Mongo reminders exist, calendar facts match accepted state, and Bob sees Alice's modification. | false |
| L5 Three-way coordination | 3 | Setup Alice-Bob and Alice-Carol friendships. T1 Alice lists friends; T2 `约 Bob 和 Carol 周日 14:00 一起打球`; T3 ask `发给几个人了`; T4 Bob checks pending; T5 Carol checks pending; T6 Bob accepts; T7 Carol accepts or asks; T8 Alice asks final status; T9-T15 include modification/cancel/status follow-ups if requests exist. | Document actual behavior. Acceptable outcomes are: create one pending request per invitee with independent accept paths, or refuse/clarify that three-way shared reminders are unsupported with no writes. Creating exactly one invite while claiming both were invited is a finding. | true |
| L6 Friend remove mid-flow | 2 | Setup Alice-Bob active friendship. T1 Alice creates shared reminder with Bob; T2 Bob leaves it pending; T3 Alice lists pending; T4 Alice removes Bob; T5 Alice asks `我和 Bob 的提醒还在吗`; T6 Bob asks pending reminders; T7 Alice tries to modify it; T8 Bob tries to accept it; T9-T12 final lists/calendar facts. | Removing friendship invalidates pending shared reminders or makes them non-actionable. The agent must not show the invalidated pending request as active or allow Bob to accept it after removal. Accepted historical reminders, if any are present, must not be silently rewritten unless current product code does that and the evidence documents it. | false |
| L7 Friend vs shared reminder | 2 plus optional non-friend name | Setup Alice-Mei active friendship; Jin is not a friend. T1 Alice lists friends; T2 `约 Mei 明天 10 点`; T3 ask `刚才是加好友还是约提醒`; T4 Mei checks pending; T5 Alice `约 Jin 明天 11 点`; T6 Alice asks why; T7 list friends; T8 list shared reminders; T9-T10 final status. | `约 Mei` resolves as `create_shared_reminder`, not friend-add. `约 Jin` fails closed or asks to add Jin first; it must not create a shared reminder with a non-friend. | false |
| L8 Reminder vs shared reminder | 2 | Setup Alice-Bob active friendship. T1 Alice creates personal reminder `去开会 14:00`; T2 list personal reminders; T3 `提醒我和 Bob 一起开会 15:00`; T4 Bob checks pending; T5 Alice asks `我自己的 14 点还在吗`; T6 Bob accepts; T7 Alice lists personal reminders; T8 Alice lists shared reminders; T9 modify shared; T10 verify both. | The 15:00 ask creates a shared reminder and does not modify the 14:00 personal reminder. Both exist independently with distinct ids and ownership. | false |
| L9 Capability boundary stretch | 2 | Setup Alice-Alex active friendship. Mix 15 turns: `你能帮我订机票吗`; `提醒我 9 点喝水`; `帮我点外卖`; `帮我查股价`; `帮我约 Alex 教练明天 10 点`; Alex pending/accept; Alice asks status; more unsupported asks; list reminders. | Unsupported external capabilities are refused without writes. Legitimate reminder and friend/shared-reminder asks are not over-refused. `帮我约 Alex 教练` should use shared-reminder primitives when Alex is a friend, not a first-class booking promise. | false |
| L10 Persona consistency | 1 | 12 turns interleaving `你是谁`, `你能做什么`, `你今天忙吗`, create/list/update/cancel reminder turns, and `你刚才说你能做什么`. | Persona answers stay consistent with actual Coke capabilities. Reminder operations still work after persona turns. The agent must not claim unsupported capabilities or forget created reminders. | false |

## Per-case execution model

For each case:

1. Provision the required fresh accounts and write account metadata into the
   evidence file before the first user turn.
2. Run setup preconditions through real surfaces where possible: invite-link
   friend bootstrap, friend request accept, and shared reminder accept. Direct
   DB fixture mutation is allowed only for explicitly named setup state such as
   a display-name update; record it as `fixture_mutation`.
3. Before every turn, snapshot Mongo and Postgres, filtered to the case
   accounts. This is required even when the turn is expected to be read-only.
4. Send exactly one user turn through `send_as`, using the account's
   `coke_account_id` and normal send kwargs.
5. If `send_as` returns the sync-timeout placeholder, rely on the shared
   late-reply polling behavior before evaluating the turn. If no late reply
   lands, classify that turn as `BLOCKED-LATE-REPLY-TIMEOUT`, not as a product
   finding.
6. After the turn, snapshot Mongo and Postgres again. Store both the full
   per-turn delta and a compact summary.
7. Capture a bounded `agent_sessions` trace excerpt for the turn: selected
   tool name, tool args, tool result summary, and any validation error. Do not
   store huge raw sessions unless the case is blocked without the excerpt.
8. Evaluate the per-turn assertion first, then the case-level assertion. A
   case can have an early finding and still continue if later turns remain
   diagnosable.
9. Save transcript, before/after snapshot ids or redacted rows, deltas, tool
   traces, verdicts, and `product_contract_unclear`.

Mongo collections to snapshot:

- `reminders`, filtered by case account ids.
- `outputmessages` and `inputmessages`, filtered by case account ids.
- `agent_sessions`, latest rows that mention any case account id or the turn's
  causal inbound event id.

Postgres tables to snapshot:

- `customers`, `identities`, `memberships`, and route/binding tables needed to
  prove account setup.
- `friend_requests`, `friendships`, `user_links`, and `link_sessions`.
- `shared_reminder_requests`, `reminder_projections`,
  `product_notifications`, and `delivery_routes`.

Verdicts:

- `PASSED`: DB state, tool trace, and visible reply match the expected behavior.
- `FINDING`: assistant text, tool trace, Mongo, or Postgres diverges from the
  expected behavior.
- `BLOCKED`: setup, health, auth, provisioning, or unrelated gateway failure
  prevents the case from exercising its target behavior.
- `BLOCKED-LATE-REPLY-TIMEOUT`: the bridge returned a placeholder and no late
  real reply appeared within the polling window.

## Findings JSON shape

```json
{
  "batch_id": "cross-feature-long-l7-20260526t120000Z",
  "model": "GLM-5.1 thinking-off",
  "case_id": "L7-friend-vs-shared-reminder",
  "verdict": "FINDING",
  "bug_pattern": "X1",
  "severity": "silent-bad-side-effect",
  "product_contract_unclear": false,
  "accounts": {
    "alice": {"coke_account_id": "ck_smoke_...", "display_name": "Alice Long ..."},
    "mei": {"coke_account_id": "ck_smoke_...", "display_name": "Mei Long ..."}
  },
  "expected": "Mei is an active friend, so `约 Mei 明天 10 点` creates a shared reminder request",
  "observed": "assistant tried friend-add wording and no shared_reminder_requests row appeared",
  "turns": [
    {
      "turn": 2,
      "speaker": "alice",
      "input_text": "约 Mei 明天 10 点",
      "reply_text": "...",
      "elapsed_ms": 12345,
      "output_id": "...",
      "placeholder_received": false,
      "late_reply_landed": false,
      "before_snapshot_ref": "turn-02-before",
      "after_snapshot_ref": "turn-02-after",
      "mongo_delta": {"reminders": {"added": 0, "modified": 0, "removed": 0}},
      "postgres_delta": {
        "shared_reminder_requests": {"added": 0, "modified": 0, "removed": 0},
        "friend_requests": {"added": 0, "modified": 0, "removed": 0}
      },
      "agent_trace_excerpt": {
        "tool": "scheduling_domain",
        "intent": "send_friend_request_by_user_link_code",
        "args": {"friend_name": "Mei"},
        "tool_result": {"ok": false, "error": "missing_user_link_code"}
      }
    }
  ],
  "case_delta_summary": {
    "mongo": {"reminders": {"added": 0, "modified": 0, "removed": 0}},
    "postgres": {"shared_reminder_requests": {"added": 0, "modified": 0, "removed": 0}}
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
- `FR1`-`FR5`: friend-management tags from the friend edge design.
- `R1`, `R2`, `T1`, `L1`, `M1`, `S1`: personal-reminder tags from the
  reminder long-tail design.

New cross-feature tags:

- `X1`: wrong feature route or intent collision between friend, reminder, and
  shared-reminder surfaces.
- `X2`: long-conversation backreference resolves to the wrong prior entity or
  stale tool result.
- `X3`: context-pressure hallucination; reply asserts a fact absent from DB and
  not explainable by a tool result.
- `X4`: cross-user state leak or privacy leak after friendship removal or
  failed friend resolution.
- `X5`: multi-party shared-reminder cardinality bug.
- `X6`: capability-boundary drift, including over-refusal of supported Coke
  operations after unsupported asks.
- `X7`: persona/capability self-description contradicts actual available
  surfaces.
- `NEW`: use only when none of the above fits; include a one-line definition.

Severity values:

- `silent-bad-side-effect`: durable state changed incorrectly or failed to
  change while the assistant claimed success.
- `visible-error`: user receives an error, fallback, or refusal that contradicts
  the expected path.
- `privacy-leak`: reply or tool result exposes another account's reminder,
  calendar, or identity data without an active authorization path.
- `UX-rough`: behavior is correct but confusing or incomplete.

## What the hunt codex must NOT do

- Do not modify product code in `agent/`, `connector/`, `dao/`, or `gateway/`.
- Do not try to fix bugs found by the hunt.
- Do not swap the LLM model or thinking mode.
- Do not reintroduce `blockAccount`, `unblockAccount`, `account_blocks`, or
  retired account-control wording as an active feature.
- Do not add backwards-compat shims, parser fallbacks, or prompt examples to
  make a case pass.
- Do not add cross-timezone or calendar-import cases.
- Do not weaken expected behavior after seeing failures.
- Do not treat assistant text as proof without Mongo and Postgres verification.
- Do not collapse a 20-turn case into a 1-3 turn unit test; the long trail is
  the point of this hunt.
- Do not skip per-turn snapshots to reduce evidence size. Redact or summarize
  bulky rows instead.
- Do not push to origin without explicit human sign-off.

## Reviewable summary

- The hunt covers 10 requested long-form flows across personal reminders,
  friend management, shared reminders, capability boundaries, and persona.
- Each case uses fresh accounts but keeps state within the case so long
  conversation memory and DB state can interact naturally.
- The execution model requires Mongo and Postgres snapshots before and after
  every turn, not just every case.
- The design preserves late-reply polling semantics from `bridge_client` and
  separates late-reply timeouts from product findings.
- `product_contract_unclear` is explicit for recurring occurrence completion
  and three-way shared reminder behavior; other cases have expected closed
  contracts.
- New `X*` tags cover cross-feature intent collision, stale backreference,
  context hallucination, privacy leaks, multi-party cardinality, capability
  drift, and persona mismatch.
- The hunt is evidence-only: no product code changes, no model swap, no
  backwards-compat shims, no block/unblock revival, no cross-timezone or
  calendar-import expansion.
