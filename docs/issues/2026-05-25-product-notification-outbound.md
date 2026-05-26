---
kind: incident
status: resolved
surface:
  - gateway-api
  - bridge
  - agent-runtime
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Product Notifications Did Not Reach WeChat

## What Happened

A friend request was created for target account `ck_oO6k7XiefS3SePj8fsdUs`.
Postgres showed the `friend_requests` row and a `product_notifications` row
marked `delivered`, but the target user reported no proactive WeChat notice.

Production MongoDB showed the notification was enqueued as an `inputmessages`
document with `message_type=product_notification` and
`delivery_mode=request_response`. The agent then produced a fallback
`outputmessages` row with no top-level `customer_id`, no push `delivery_mode`,
and no outbound `output_id`, so the bridge output dispatcher could not claim it.

## Why It Matters

Friend request and shared reminder notifications are product-generated push
messages. Marking them delivered after only enqueueing them into the bridge made
the UI and database claim success while no WeChat delivery was attempted.

## Affected Surfaces

- `gateway-api`
- `bridge`

## Evidence

- `friend_requests.id=cmpjvx6ed0003p51uh6nobcu1`, requester
  `ck_CsFu-A91jbCSBwtizPx1K`, target `ck_oO6k7XiefS3SePj8fsdUs`, status
  `pending`, created at `2026-05-24 14:40:41.893 UTC`.
- `product_notifications.id=cmpjvx6eq0005p51u8p2309bi`, status `delivered`,
  delivered at `2026-05-24 14:40:41.964 UTC`.
- Mongo `inputmessages._id=6a130de977c9fa7c819ac9de` had
  `metadata.business_protocol.message_type=product_notification` and
  `delivery_mode=request_response`.
- Mongo `outputmessages._id=6a130defcdd3e3ab7a638a2c` remained `pending` with
  fallback text and no claimable push metadata.
- No matching gateway `/api/outbound` delivery existed for the notification.

## Current Status

Resolved in gateway commits `827630c` and `103e8c4`, then follow-up fixes for
confirmation context. Product notifications now resolve the recipient's latest
active delivery route and call gateway `/api/outbound` directly. Missing
delivery routes now mark the notification failed instead of pretending delivery
succeeded.

The follow-up production check showed Eva replied `确认`, but the agent treated
that message as ordinary appointment conversation context and did not call
`accept_friend_request`. The root cause was that outbound product notifications
were delivered through the gateway but were not threaded into the next inbound
turn as trusted product-notification context. Short confirmations therefore had
no deterministic link back to the pending friend request or shared reminder.

## Resolution

- Fix commits: gateway `827630c`, gateway `103e8c4`.
- Verification: `pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts src/scheduling/friendship-service.test.ts src/scheduling/user-link-service.test.ts src/scheduling/shared-reminder-service.test.ts`.
- Follow-up fix: gateway inbound routing now attaches the latest recently
  delivered, still-pending product notification to
  `metadata.product_notification`; agent runtime only treats short
  `确认/同意/接受/通过/拒绝` replies as product actions when that trusted context
  exists. The internal friend-request tool now resolves a single unnamed
  pending request and fails closed when multiple pending requests exist.
- Manual data repair: request `cmpjvx6ed0003p51uh6nobcu1` was accepted through
  `/api/internal/scheduling/tools/accept_friend_request`, creating friendship
  `cmpklyheu0002pb1t24ahoz7h` and delivering the accepted notification to the
  requester.
- Follow-up verification:
  `pnpm --dir gateway/packages/api test -- src/lib/route-message.test.ts src/routes/internal-scheduling-routes.test.ts`;
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py -q`;
  `pnpm --dir gateway/packages/api build`;
  `zsh scripts/verify-surface repo-os-docs worker-runtime`.

## 2026-05-25 Follow-up: Bridge Dropped Shared Reminder Context

Production showed a later short confirmation reply for a shared-reminder
notification still reached the agent without trusted product-notification
context. Gateway sent the context under `metadata.product_notification`, but
the bridge only read top-level `product_notification` and camelCase
`metadata.productNotification`. The snake_case metadata shape was therefore
dropped before persistence, so the agent saw `确认` as an ordinary user turn.

The bridge now preserves snake_case `metadata.product_notification` as the
canonical product-notification context for inbound turns. Verification evidence
is recorded in
`artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-title-context-20260525t134846Z.md`.

## 2026-05-26 Follow-up: Formatted Confirmation Was Not Pre-routed

Production showed Eva received a shared-reminder request at
`2026-05-26T01:22:32.655Z` and replied `确认` at
`2026-05-26T02:40:04Z`. The inbound Mongo record preserved
`metadata.product_notification`, but the runtime metadata did not include
`product_notification_input_text`. The deterministic product-notification
pre-router therefore evaluated the formatted input string
`（2026年05月26日10时40分 eva发来了文本消息）确认`, exceeded the short-decision
threshold, and did not preload `accept_shared_reminder`. The interaction model
then answered from stale conversation context about adding friends.

A narrow runtime hotfix fell back to extracting the latest raw user-turn text
from the formatted input whenever trusted product-notification context exists
and `product_notification_input_text` is absent. **This hotfix and the entire
deterministic product-notification pre-router were superseded by Spec A**
(`docs/superpowers/specs/2026-05-26-coke-focus-and-semantic-router-design.md`,
implementation commits 967138c4..4c173a6d). User-utterance intent is now
classified by a semantic interpreter over `(focus, current_utterance)`; the
formatted-prefix extraction is no longer load-bearing.
