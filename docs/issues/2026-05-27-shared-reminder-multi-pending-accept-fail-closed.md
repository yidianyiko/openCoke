---
kind: issue
status: open
title: Shared reminder accept fails closed when invitee has duplicate pending invites
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - agent-runtime
  - scheduling-domain
  - production-smoke
---

# Shared Reminder Accept Fails Closed on Duplicate Pending Invites

## Problem

Production user `olivers` (`ck_SXk_J0U0V5JKcK09QHEuo`) received two shared
reminder invites from `李梓豪` (`ck_CsFu-A91jbCSBwtizPx1K`) for the same title
and the same fire time, then replied three times in a row to accept. Every
reply was answered with the focused-semantic fail-closed message
`"我没法可靠判断你要同意还是拒绝这条请求，请再明确回复同意或拒绝。"`.

User-visible transcript:

```
14:07:50 olivers→ 确认       ←我没法可靠判断你要同意还是拒绝…
14:08:04 olivers→ 同意       ←我没法可靠判断…
14:08:20 olivers→ 我同意     ←我没法可靠判断…
```

## Upstream State

Postgres `shared_reminder_requests` (invitee = olivers):

| id | requester | title | fire_at (UTC) | status | idempotency_key |
| --- | --- | --- | --- | --- | --- |
| `cmpo43gom0002mv1uwm189de3` | 李梓豪 | 数学课 | 2026-05-28 12:00 | pending_invitee_confirmation | `create_shared_reminder:37ce08f8…` |
| `cmpo527yn000bmv1uutaf2jvs` | 李梓豪 | 数学课 | 2026-05-28 12:00 | pending_invitee_confirmation | `create_shared_reminder:be4659a3…` |

Both `product_notifications` (`shared_reminder_request`) were delivered to
olivers. The Mongo `inputmessages` for olivers' three replies carry a
gateway-bundled `metadata.product_notification`:

```json
{
  "ambiguity": "multi_pending",
  "candidates": [
    {
      "request_id": "cmpo527yn…",
      "request_type": "shared_reminder_request",
      "delivered_at": "2026-05-27T14:07:38.968Z",
      "allowed_actions": ["accept", "reject"],
      "actor_account_id": "ck_CsFu-A91jbCSBwtizPx1K",
      "summary_for_llm": "李梓豪邀请你参加「数学课」，时间2026-05-28 20:00，预计60分钟。请确认或拒绝。"
    },
    {
      "request_id": "cmpo43gom…",
      "request_type": "shared_reminder_request",
      "delivered_at": "2026-05-27T13:40:37.376Z",
      "allowed_actions": ["accept", "reject"],
      "actor_account_id": "ck_CsFu-A91jbCSBwtizPx1K",
      "summary_for_llm": "李梓豪邀请你参加「数学课」，时间2026-05-28 20:00，预计60分钟。请确认或拒绝。"
    }
  ]
}
```

Both candidate summaries are byte-for-byte identical because the gateway pre-bakes
`summary_for_llm` from title + local time + duration only — `delivered_at` is the
only discriminator visible to the agent.

## Root Cause

Agent runtime path:

1. `connector/clawscale_bridge/message_gateway.py:163-164` attaches the
   gateway-bundled multi_pending `product_notification` (with two `candidates`)
   as `metadata.product_notification`.
2. `agent/agno_agent/runtime/focus.py:31-49` `build_focus_channel` sees
   `len(actions) > 1` and returns
   `FocusChannel(current=None, ambiguity="multi_pending", candidates=(a, b))`.
3. `agent/agno_agent/runtime/agent_runtime.py:595-608` `_focus_current_action`
   falls back to `candidates[0]` when `current is None`, so
   `_focus_has_actionable_candidates` returns `True`.
4. `agent/agno_agent/runtime/semantic_interpreter.py:54-67` prompt explicitly
   tells the LLM: "If the focus is missing, stale, **multi-candidate**, or the
   reply is unclear, return 'ambiguous'." The LLM correctly returns `ambiguous`
   for a multi-candidate focus regardless of how unambiguous the utterance is.
5. `agent/agno_agent/runtime/agent_runtime.py:661-669`
   `_should_fail_closed_focused_semantic` then returns `True`, and
   `_focused_semantic_failure_result` (lines 615-658) produces the fixed
   summary `"我没法可靠判断你要同意还是拒绝这条请求，请再明确回复同意或拒绝。"`
   with `required_questions=("同意还是拒绝这条请求？",)`.

The system is *correctly* fail-closed: there are two equally-valid pending
invites and the utterance carries no signal about *which* invite is being
accepted. But the user-visible clarification mis-describes the ambiguity — it
asks olivers to say "accept or reject" again, even though that part was never
unclear. The actual missing signal is *which of the two invites*.

## Scope

In scope: the agent runtime downstream clarification path. Surface both
candidates with a delivered-at discriminator, and ask the user to pick by
delivery time or title disambiguator.

Out of scope (separate follow-up): gateway shared-reminder create does not
deduplicate `(requester, invitee, title, fire_at, timezone, duration)` when an
existing `pending_invitee_confirmation` row already covers the same offer.
That is what produced the duplicate pair in the first place. To be filed as a
separate gateway issue once this clarification fix lands.

## Plan

`docs/superpowers/plans/2026-05-27-multi-pending-focus-clarification.md`.

## Verification Plan

- Unit: agent runtime multi_pending fail-closed path produces a
  `semantic_focus_multi_pending` `ReplyContract` whose visible reply lists each
  candidate by `delivered_at` and `summary_for_llm` and asks the user to choose
  one.
- Unit: single-candidate ambiguous fail-closed path keeps the existing summary
  and question unchanged.
- Production smoke: keep the existing two pending invites, have olivers reply
  with a generic accept utterance, verify the new visible reply enumerates both
  invites with their delivery times. Then have olivers reference a single
  invite (e.g. by delivery time) and verify the accept completes durably.

## Status

Open. Issue, plan, code, and verification land in a single change set per
project rules.
