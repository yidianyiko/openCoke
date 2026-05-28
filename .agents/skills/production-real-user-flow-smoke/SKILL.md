---
name: production-real-user-flow-smoke
description: Use when verifying Coke production behavior by simulating real account messages or actions on the server, especially direct friendship creation, active shared-reminder creation/cancel flows, notification delivery, and cleanup of test reminders.
---

# Production Real User Flow Smoke

## Purpose

Verify the deployed Coke path with real account identity, real delivery routes,
and live services. Use this only when the user explicitly asks for server-side
simulation or production verification. Prefer a marked test title and clean up
future reminders created by the smoke.

The current product-notification happy path is:

1. Gateway creates a domain row such as `shared_reminders`.
2. Gateway stores a `product_notifications` row with structured
   `payload.facts` and `payload.facts_hash`; Gateway must not store final
   user-visible prose there.
3. Gateway enqueues a `message_type=product_notification` event to
   `/bridge/inbound`.
4. The worker Interaction Agent writes a push `outputmessages` row whose
   metadata contains `notification_id` and the same product-notification facts.
5. The bridge output dispatcher posts that output to Gateway `/api/outbound`.
6. Gateway sends through the provider and reconciles the matching
   `product_notifications.status` to `delivered`.

A passing smoke must verify the end-to-end chain above. A created domain row or
a `product_notifications` row by itself is not enough.

For user-initiated chat flows, the happy path has two independent output
obligations:

- The requester must receive a non-placeholder Interaction Agent reply for the
  original user turn. The bridge `reply` and the requester `outputmessages`
  row must not be the system fallback
  `系统刚才没能生成回复，请稍后再试一次。`.
- The counterparty product notification must complete the product-notification
  chain above and reconcile to `product_notifications.status='delivered'`.

Do not collapse those obligations into one pass/fail signal. A domain row plus
a requester reply proves creation, but not counterparty delivery. A delivered
counterparty notification proves push delivery, but not that the original user
turn got a good synchronous reply.

## Safety Rules

- State before running that this can send real push messages to real accounts.
- Never print API keys or bearer tokens.
- Do not hard-code old route fields from chat. Query current production state.
- Use a unique marker such as `server-smoke-YYYYMMDDTHHMMSSZ`.
- Schedule test reminders far in the future and include the marker in the title.
- After active shared-reminder verification, cancel the marked shared reminder
  through Scheduling. Do not manually delete unmarked user data.
- Do not delete unmarked user data.
- If an interrupted run may have partially executed, first query by marker and
  clean up any active marked shared reminder before starting a fresh marker.
- Do not treat provider errors as a pass. In particular,
  `wechat_send_failed ret=-2`, a `product_notifications` row that remains
  `pending_delivery`, or only failed Mongo output rows for the notification
  means the receiver delivery obligation failed even if the domain row was
  created. If the same notification has both successful and failed output rows,
  do not call it a clean pass; record it as partial evidence and investigate
  the duplicate or retry behavior.
- Do not rely on a single marker, single phrasing, or single direction for a
  broad happy-path claim. Use at least two marked natural-language create
  phrasings when validating a recently changed shared-reminder path: one
  machine-like smoke title and one normal chat title. When account routes allow
  it, run both account directions or explicitly record why one direction is not
  valid evidence.
- A normal chat title should avoid punctuation-heavy marker shapes such as
  `server-smoke-...` in the main title. Put the unique marker in a compact
  suffix, for example `验收喝茶<marker>`, so the test also samples ordinary LLM
  reply behavior.

## Required Context

From production Postgres, query both accounts:

```bash
ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T postgres psql -U clawscale -d clawscale'
```

```sql
select
  dr.tenant_id,
  dr.coke_account_id,
  c.display_name,
  cu.id as clawscale_user_id,
  dr.business_conversation_key,
  dr.channel_id,
  dr.end_user_id,
  dr.external_end_user_id,
  dr.is_active,
  dr.updated_at
from delivery_routes dr
join clawscale_users cu on cu.coke_account_id = dr.coke_account_id
join customers c on c.id = dr.coke_account_id
where dr.coke_account_id in ('<creator_account_id>', '<receiver_account_id>')
order by c.display_name;
```

Confirm all rows are active. For shared reminders, also confirm the two accounts
are active friends or create the friendship through the direct friend-link flow
first.

## Flow

1. Inspect service health and recent logs:

```bash
ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml ps'
ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml logs --since=10m coke-agent coke-bridge gateway | tail -200'
```

2. Verify or create the direct friendship.

Use the public user-link session or the canonical Scheduling tool with the
link owner's current code. A repeated run between already-active friends should
return success without a duplicate friendship notification.

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T gateway node - <<'JS'
const key = process.env.CLAWSCALE_IDENTITY_API_KEY;
const marker = process.env.MARKER || '<marker>';
const body = {
  customer_id: '<creator_account_id>',
  user_link_code: '<receiver_user_link_code>',
  idempotency_key: `friendship-smoke-${marker}`,
};
const res = await fetch('http://127.0.0.1:4041/api/internal/scheduling/tools/create_friendship_by_user_link_code', {
  method: 'POST',
  headers: { authorization: 'Bearer ' + key, 'content-type': 'application/json' },
  body: JSON.stringify(body),
});
console.log(await res.text());
JS"
```

Verify the active friendship:

```sql
select id, account_a_id, account_b_id, status, updated_at
from friendships
where status = 'active'
  and ((account_a_id = '<creator_account_id>' and account_b_id = '<receiver_account_id>')
    or (account_a_id = '<receiver_account_id>' and account_b_id = '<creator_account_id>'))
order by updated_at desc;
```

If the friendship call returned `created=false`, do not use old friendship
notifications as delivery evidence. That only proves the friendship idempotency
path. If it returned `created=true`, verify the fresh friendship notification
with the same product-notification checks used for shared reminders below.

For a freshly created friendship only:

```sql
select id, recipient_account_id, kind, status, attempts, last_error,
       friendship_id, payload, business_conversation_key, delivered_at
from product_notifications
where friendship_id = '<friendship_id>'
order by created_at desc;
```

3. Simulate the creator message through production bridge:

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T -e MARKER='<marker>' coke-bridge python - <<'PY'
import json, os, time, urllib.request
marker = os.environ['MARKER']
key = os.environ['COKE_BRIDGE_API_KEY']
text = f'帮我约<receiver_name>，上海时间2029年1月1日10:00，标题是验收测试-{marker}，持续5分钟。'
payload = {
    'customer_id': '<creator_account_id>',
    'coke_account_id': '<creator_account_id>',
    'coke_account_display_name': '<creator_display_name>',
    'tenant_id': '<tenant_id>',
    'clawscale_user_id': '<clawscale_user_id>',
    'channel_id': '<channel_id>',
    'platform': 'wechat_personal',
    'external_id': '<external_end_user_id>',
    'end_user_id': '<end_user_id>',
    'business_conversation_key': '<business_conversation_key>',
    'channel_scope': 'personal',
    'message_type': 'text',
    'input': text,
    'text': text,
    'timestamp': int(time.time()),
    'inbound_event_id': f'smoke_create_{marker}',
    'sync_reply_token': f'smoke_create_token_{marker}',
}
req = urllib.request.Request(
    'http://127.0.0.1:8090/bridge/inbound',
    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req, timeout=180) as resp:
    print(resp.read().decode('utf-8'))
PY"
```

Required requester checks after the bridge call:

- The bridge response has `ok=true`.
- The bridge `reply` is non-empty and is not the system fallback
  `系统刚才没能生成回复，请稍后再试一次。`.
- The requester `outputmessages` row for the inbound event exists, has
  `status` not `failed`, has no `fallback_kind=system_failure`, and its visible
  `message` is grounded in the requested action.
- If the requester reply fails but the domain row is created, report the row as
  `partial-production`: creation passed, requester chat reply failed.

4. Verify active create by marker:

```sql
select id, title, status, fire_at, duration_minutes, creator_reminder_id,
       receiver_reminder_id, created_at, updated_at
from shared_reminders
where title like '%<marker>%'
order by created_at desc;

select id, recipient_account_id, kind, status, attempts, last_error,
       shared_reminder_id, payload, business_conversation_key, delivered_at
from product_notifications
where shared_reminder_id = '<shared_reminder_id>'
order by created_at;
```

For each fresh product notification, verify the current outbound chain:

```sql
select id, kind, status, attempts, last_error, business_conversation_key,
       delivered_at, payload
from product_notifications
where id = '<product_notification_id>';
```

Required checks:

- `payload` contains `facts` and `facts_hash`.
- `payload` does not contain final prose such as `text`.
- `facts.title` includes the smoke marker for shared reminder notifications.
- After dispatcher delivery, `status='delivered'`,
  `business_conversation_key` is set, and `delivered_at is not null`.

Then verify the worker-produced push output in production MongoDB:

```bash
ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T mongo mongosh --quiet --eval '\''
const notificationId = "<product_notification_id>";
const rows = db.getSiblingDB("mymongo").outputmessages.find({
  $or: [
    {"metadata.notification_id": notificationId},
    {"metadata.product_notification.notification_id": notificationId},
  ],
}).sort({timestamp: -1}).limit(5).toArray();
printjson(rows.map((row) => ({
  id: String(row._id),
  status: row.status,
  message: row.message,
  metadata: row.metadata,
})));
'\'''
```

Required checks:

- At least one row exists.
- `metadata.notification_id` or
  `metadata.product_notification.notification_id` equals the notification id.
- `metadata.business_protocol.delivery_mode='push'`.
- `metadata.business_protocol.idempotency_key` is
  `product_notification:<product_notification_id>`.
- `metadata.product_notification.facts_hash` matches the Postgres
  notification row.
- `status` is not `failed`.
- Gateway logs for the marker do not show provider send failure such as
  `wechat_send_failed ret=-2`.
- The visible `message` is derived from the product-notification facts. For a
  shared reminder create, it should mention the reminder title or scheduled
  local date/time and must not be a generic onboarding or unrelated chat reply.
- If multiple output rows exist for the same notification, record all statuses.
  A successful row plus a failed row is not clean happy-path evidence, even
  when the final `product_notifications` row reconciles to `delivered`.

If the output row is missing, failed, or has unrelated visible text, stop and
report the layer where the chain failed. Continue only with cleanup.

For each marker, classify evidence before moving on:

- `passed-production`: requester reply passed, domain row/projections passed,
  product notification facts passed, worker output passed, provider
  reconciliation reached `delivered`, and cleanup passed.
- `partial-production`: at least one core layer passed, but a separate
  obligation failed or stayed pending. State exactly which layer failed.
- `failed-production`: no durable domain write happened, or the requested
  operation completed the wrong user-visible behavior.

5. If natural-language routing fails, isolate the layer by calling the
   canonical gateway tool with the same accounts. A successful canonical call
   means the gateway/domain service is healthy and the bug is in agent routing,
   schema, or canonical argument construction.

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T gateway node - <<'JS'
const key = process.env.CLAWSCALE_IDENTITY_API_KEY;
const marker = process.env.MARKER || '<marker>';
const body = {
  customer_id: '<creator_account_id>',
  receiver_account_id: '<receiver_account_id>',
  receiver_name: '<receiver_name>',
  title: `验收测试-${marker}`,
  fire_at: '2029-01-01T02:00:00.000Z',
  timezone: 'Asia/Shanghai',
  duration_minutes: 5,
  idempotency_key: `shared-reminder-smoke-${marker}`,
};
const res = await fetch('http://127.0.0.1:4041/api/internal/scheduling/tools/create_shared_reminder', {
  method: 'POST',
  headers: { authorization: 'Bearer ' + key, 'content-type': 'application/json' },
  body: JSON.stringify(body),
});
console.log(await res.text());
JS"
```

6. Cancel the marked active shared reminder through Scheduling:

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T gateway node - <<'JS'
const key = process.env.CLAWSCALE_IDENTITY_API_KEY;
const marker = process.env.MARKER || '<marker>';
const body = {
  customer_id: '<creator_account_id>',
  shared_reminder_id: '<shared_reminder_id>',
  idempotency_key: `shared-reminder:<shared_reminder_id>:cancel:<creator_account_id>`,
};
const res = await fetch('http://127.0.0.1:4041/api/internal/scheduling/tools/cancel_shared_reminder', {
  method: 'POST',
  headers: { authorization: 'Bearer ' + key, 'content-type': 'application/json' },
  body: JSON.stringify(body),
});
console.log(await res.text());
JS"
```

7. Verify cancelled state and receiver notification:

```sql
select id, title, status, creator_reminder_id, receiver_reminder_id,
       cancelled_at, updated_at
from shared_reminders
where id = '<shared_reminder_id>';

select recipient_account_id, kind, status, attempts, last_error, payload, delivered_at
from product_notifications
where shared_reminder_id = '<shared_reminder_id>'
order by created_at;
```

Apply the same product-notification outbound-chain checks to the cancellation
notification row. If the creator cancels, the receiver should receive the
cancel notification; if the receiver cancels, the creator should receive it.

## Evidence To Report

- bridge response and late output if the bridge returned the placeholder
- direct friendship id/status and owner notification status
- created shared reminder id and active status
- receiver creation notification id/status plus facts/facts_hash
- worker `outputmessages` id/status/message for the creation notification
- `/api/outbound` reconciliation evidence: notification status `delivered`,
  `business_conversation_key`, and `delivered_at`
- cancel result and final cancelled status
- receiver cancellation-notification status when creator cancels, or creator
  cancellation-notification status when receiver cancels
- worker `outputmessages` id/status/message for the cancellation notification
- cleanup evidence showing the marked runtime reminders were cancelled through
  Scheduling
- any layer isolation result: natural-language route vs canonical tool
