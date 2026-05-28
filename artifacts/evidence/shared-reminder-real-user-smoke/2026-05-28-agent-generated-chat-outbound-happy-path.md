---
kind: verification_report
created_at: 2026-05-28T06:45:00Z
marker: server-smoke-20260528T063241Z
status: passed_cleaned_up
---

# Agent-Generated Chat Outbound Happy Path Smoke

Date: 2026-05-28
Environment: production GCP compose stack
Deployed root commit before smoke: `a374b5c4`
Deployed gateway commit before smoke: `fc8621b`

## Happy Path Contract

The production real-user smoke skill was updated to match the current
implementation:

1. Gateway creates the domain row.
2. Gateway stores `product_notifications.payload.facts` and `facts_hash` only.
3. Gateway enqueues `message_type=product_notification` to the bridge.
4. The worker Interaction Agent writes push `outputmessages` with the same
   facts and `notification_id`.
5. The bridge dispatcher posts that output to Gateway `/api/outbound`.
6. Gateway sends through the provider and reconciles
   `product_notifications.status='delivered'`.

A `product_notifications` row or created domain row alone is not sufficient
evidence.

## Accounts And Routes

- olivers: `ck_SXk_J0U0V5JKcK09QHEuo`, route
  `bc_6a16459b790c7841638352b4`, active.
- eva: `ck_oO6k7XiefS3SePj8fsdUs`, route
  `bc_6a12926c96ac676d087d7da0`, active.
- Friendship: `cmpokdm2o0001p61ufcacdomb`, active.

## Initial Direction Check

Marker: `server-smoke-20260528T062142Z`

olivers -> eva created shared reminder
`sr_a46602566387def5d93f6165ab6aa81a1012eda1`, then cleanup cancelled it.

Creation notification `cmpp3zfj60007pb1u94belu2b` proved the product
notification event reached the worker, but the generated `outputmessages` row
`6a17dfe22789b0238d706512` failed the updated happy path:

- status: `failed`
- message: `hey，我是 Coke。你的健康搭子～ 有什么健康目标想聊聊的吗？`
- outbound delivery: `failed`
- provider error: `wechat_send_failed ret=-2`

Cancellation for the same marker produced a facts-derived message in
`outputmessages` row `6a17e1c82789b0238d706716`, but the provider delivery also
failed with `wechat_send_failed ret=-2`.

This direction was not used as passing happy path evidence. The marked shared
reminder was cancelled through Scheduling at `2026-05-28T06:33:14.583Z`.

## Passing Direction

Marker: `server-smoke-20260528T063241Z`

eva sent through `/bridge/inbound`:

```text
帮我约olivers，上海时间2029年1月2日10:00，标题是验收测试-server-smoke-20260528T063241Z，持续5分钟。
```

Bridge response:

```json
{"business_conversation_key":"bc_6a12926c96ac676d087d7da0","causal_inbound_event_id":"smoke_create_server-smoke-20260528T063241Z","ok":true,"output_id":"6a17e2222789b0238d70677f","reply":"系统刚才没能生成回复，请稍后再试一次。"}
```

The creator-facing synchronous reply fell back, but the durable domain write
and receiver push path succeeded.

Created shared reminder:

- id: `sr_9e21e5151022007d6497ef750ac71bf30adfcbf8`
- title: `验收测试-server-smoke-20260528T063241Z`
- status before cleanup: `active`
- fire_at: `2029-01-02 02:00:00`
- creator: `ck_oO6k7XiefS3SePj8fsdUs`
- receiver: `ck_SXk_J0U0V5JKcK09QHEuo`

Creation product notification:

- id: `cmpp4c27i000rpb1ub1qb99zt`
- recipient: `ck_SXk_J0U0V5JKcK09QHEuo`
- kind: `shared_reminder_created`
- status: `delivered`
- attempts: `0`
- last_error: empty
- facts_hash: `sha256:a33a92cff0345b8e254594acb1690e482e95d2964fa43a1b130abb2834c83403`
- business_conversation_key: `bc_6a16459b790c7841638352b4`
- delivered_at: `2026-05-28 06:35:23.632`

Creation worker output:

- id: `6a17e22b2789b0238d70678c`
- status: `handled`
- notification_id: `cmpp4c27i000rpb1ub1qb99zt`
- idempotency_key: `product_notification:cmpp4c27i000rpb1ub1qb99zt`
- message:
  `eva 给你创建了一个共享提醒：验收测试-server-smoke-20260528T063241Z，时间是 2029年1月2日 10:00，时长5分钟，记得查看哦～`

Creation outbound delivery:

- id: `cmpp4cgy4000upb1u7fz6rxap`
- status: `succeeded`
- error: empty
- text matched the worker output.

Gateway logs in the create window showed:

```text
POST /api/outbound -> 200
```

## Cancellation And Cleanup

Cancelled through the canonical Scheduling tool as eva:

```json
{"ok":true,"data":{"id":"sr_9e21e5151022007d6497ef750ac71bf30adfcbf8","status":"cancelled","cancelledAt":"2026-05-28T06:37:17.577Z"}}
```

Final shared reminder state:

- id: `sr_9e21e5151022007d6497ef750ac71bf30adfcbf8`
- status: `cancelled`
- cancelled_at: `2026-05-28 06:37:17.577`

Cancellation product notification:

- id: `cmpp4ex81000ypb1uyh2p1hmj`
- recipient: `ck_SXk_J0U0V5JKcK09QHEuo`
- kind: `shared_reminder_cancelled`
- status: `delivered`
- attempts: `0`
- last_error: empty
- facts_hash: `sha256:3bd21c36110c595ad2503636014e97ea7c66eaced545f7fec77582957e07cef9`
- business_conversation_key: `bc_6a16459b790c7841638352b4`
- delivered_at: `2026-05-28 06:37:24.09`

Cancellation worker output:

- id: `6a17e2a22789b0238d706811`
- status: `handled`
- notification_id: `cmpp4ex81000ypb1uyh2p1hmj`
- idempotency_key: `product_notification:cmpp4ex81000ypb1uyh2p1hmj`
- message:
  `eva 取消了你之前收到的共享提醒：验收测试-server-smoke-20260528T063241Z（2029年1月2日 10:00），已取消～`

Cancellation outbound delivery:

- id: `cmpp4f1jr0011pb1u45z383p4`
- status: `succeeded`
- error: empty
- text matched the worker output.

Gateway logs in the cancellation window showed:

```text
POST /api/internal/scheduling/tools/cancel_shared_reminder -> 200
POST /api/outbound -> 200
```

## Conclusion

The updated happy path passed for the eva -> olivers real-user direction:
domain write, facts-only product notification, worker-authored push message,
outbound dispatch, provider success, notification reconciliation, and cleanup
were all verified against production data.

Residual finding: the creator-facing synchronous reply for the create turn
returned a fallback even though the durable create and receiver push succeeded.
That is outside the product-notification happy path verified here, but should
be tracked separately if creator-visible immediate replies are required for
this flow.
