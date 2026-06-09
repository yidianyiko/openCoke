---
kind: active_issue
status: open
surface:
  - conversation-runtime
  - social-scheduling
  - wechat-personal-connector
  - production-smoke
created_at: 2026-06-09
updated_at: 2026-06-09
---

# 2026-06-09 Shared Reminder Invite Content Segment Lost To Recipient

## What Happened

At 2026-06-09 00:12 Asia/Shanghai (2026-06-08 16:12:51 UTC) `olivers` created a
shared reminder for `eva`:

- `shared_reminder` `ba722296-5e3b-4ac5-b0d9-9993103e3c34`
- title `和 eva 约Peter演讲`, local trigger `2026-06-11 15:00 Asia/Shanghai`,
  duration 15m, status `active`.

The durable record and the `shared_reminder_created` notification fact both
carried full content (title, time, participants). But the invite was rendered
into **two separate WeChat outbound message segments**, sent as two separate
`wechat_personal` ilink sends:

- `reply:1` text `olivers 和你共享了一个提醒` — delivery attempt status `sent`
  (885 ms, provider_message_id present).
- `reply:2` text `6月11日 15:00「和 eva 约Peter演讲」，时长15分钟` — delivery
  attempt status `failed`, `error_code = ilink_send_failed_ret_-2`.

Eva received only the contentless header segment. The segment that actually
states what/when was scheduled was never delivered, and was never re-sent on any
later attempt (no subsequent delivery attempt on Eva's route, no later outbound
message carrying the title).

## Why It Matters

Two distinct failures, both user/trust critical:

1. **Mid-segment content loss with no recovery.** A multi-segment notification
   delivered its first (contentless) segment and lost its content segment. The
   ilink `ret_-2` failure is classified as a session-window / context-token
   non-retryable error (`coke/turn/runner.py:135`
   `WAITING_NON_RETRYABLE_ERROR_FRAGMENTS`, `coke/composition.py:2605`
   `_is_context_token_window_failure`), so nothing retried or resent the lost
   content. The recipient is left with "someone shared a reminder" and no idea
   what was scheduled.

2. **False delivery confirmation to the creator.** The
   `shared_reminder_delivery_confirmed` receipt to `olivers` was emitted on
   first-segment success, before the content segment was even attempted, so the
   creator was told Eva received the shared reminder while Eva did not. Same
   trust class as `docs/issues/2026-06-07-shared-reminder-false-success.md`.

Delivery timeline (UTC):

- `16:13:01.357` seg1 (`reply:1`) sent
- `16:13:01.386` `shared_reminder_delivery_confirmed` fact created
- `16:13:01.393` delivery-confirmed receipt delivered to `olivers`
- `16:13:02.146` seg2 (`reply:2`) failed `ilink_send_failed_ret_-2`
- `16:13:02.152` Eva recipient row → `undelivered`
  (`recipient_channel_unavailable`)

This is intermittent, not a rendering defect: on Eva's route `reply:1` is
15/15 `sent`, and `reply:2` is 5 `sent` historically with this single `ret_-2`
failure. Earlier same-day shared reminders to Eva (`奇绩论坛` 14:21, `运动课`
11:34) delivered both segments successfully.

## Affected Surfaces

- `conversation-runtime` (notification render + multi-segment delivery)
- `social-scheduling` (shared-reminder invite + delivery-confirmed receipt)
- `wechat-personal-connector` (ilink `ret_-2` session-window send rejection)
- `production-smoke`

## Evidence

Production reads on `gcp-coke` / `coke-clean-postgres-1` (read-only psql via
container env), 2026-06-09:

- `shared_reminder` row `ba722296-...` (title/time/status intact).
- `notification_fact` `40cae580-...` (`shared_reminder_created`, full facts) and
  `16b6d3fa-...` (`shared_reminder_delivery_confirmed` to `olivers`).
- `notification_recipient` Eva `8ef2bee0-...` `undelivered` /
  `recipient_channel_unavailable`, `updated_at 16:13:02.152`.
- `message` rows for turn `1535c590-...`: seg `olivers 和你共享了一个提醒` and
  seg `6月11日 15:00「和 eva 约Peter演讲」，时长15分钟`.
- `delivery_attempt` Eva route `d4ba1d5e-...`: `reply:1` sent, `reply:2` failed
  `ilink_send_failed_ret_-2`.
- Aggregate on Eva route: `reply:1` 15 sent; `reply:2` 5 sent, 1 failed.

## Current Status

- Resolved in code; production deploy in progress (see Resolution).
- User decision (2026-06-09): record this issue first, then fix **both** the
  mid-segment content loss and the false delivery confirmation. Chosen
  mechanism: collapse product notifications to a single delivered segment.

## Resolution

Root cause shared by both failures: `TurnRunner._record_validated_output` built
one `DeliveryRequest` per rendered segment, so a system notification became N
separate provider sends and the recipient delivery state was recorded
per-segment (last-write-wins). The WeChat per-send context-token window
rejected the second send (`ret_-2`), stranding the content segment, while the
creator's `shared_reminder_delivery_confirmed` receipt fired on the
first-segment `delivered` state.

Fix: `TurnRunner._delivery_segments(trigger, segments)` collapses a multi-segment
render into a single delivered segment for every non-`InboundTurn` (system
product notification, reminder fire, proactive fire, undelivered resend) turn.
Interactive `InboundTurn` replies still deliver as ordered conversational
segments. With one segment per recipient there is exactly one provider send and
exactly one recipient delivery outcome, so the content can no longer be
stranded mid-notification and the delivery-confirmed receipt can only fire on
genuine full delivery.

- Code: `coke/turn/runner.py` (`_delivery_segments`, applied in
  `_record_validated_output`).
- RED→GREEN test:
  `tests/unit/coke/turn/test_turn_runner.py::test_notification_render_collapses_segments_into_single_delivery`
  (RED: two separate `reply:1`/`reply:2` deliveries; GREEN: one joined
  delivery, one outbound message).
- Regression guard kept green:
  `test_reply_segments_deliver_as_separate_ordered_messages` (inbound replies
  stay multi-segment).
- Full backend unit suite: `.venv/bin/python -m pytest tests/unit/coke -q` →
  844 passed.
- Repo-OS: `zsh scripts/check` → passed.

Fix commit and production smoke evidence recorded on deploy below.
