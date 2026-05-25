---
kind: incident
status: resolved
surface:
  - gateway-api
  - bridge
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

Resolved in gateway commit `827630c`. Product notifications now resolve the recipient's
latest active delivery route and call gateway `/api/outbound` directly. Missing
delivery routes now mark the notification failed instead of pretending delivery
succeeded.

## Resolution

- Fix commit: gateway `827630c`.
- Verification: `pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts src/scheduling/friendship-service.test.ts src/scheduling/user-link-service.test.ts src/scheduling/shared-reminder-service.test.ts`.
