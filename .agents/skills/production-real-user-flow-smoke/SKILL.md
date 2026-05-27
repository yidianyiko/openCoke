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

## Safety Rules

- State before running that this can send real push messages to real accounts.
- Never print API keys or bearer tokens.
- Do not hard-code old route fields from chat. Query current production state.
- Use a unique marker such as `server-smoke-YYYYMMDDTHHMMSSZ`.
- Schedule test reminders far in the future and include the marker in the title.
- After active shared-reminder verification, cancel the marked shared reminder
  through Scheduling. Do not manually delete unmarked user data.
- Do not delete unmarked user data.

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

Verify the active friendship and owner notification:

```sql
select id, account_a_id, account_b_id, status, updated_at
from friendships
where status = 'active'
  and ((account_a_id = '<creator_account_id>' and account_b_id = '<receiver_account_id>')
    or (account_a_id = '<receiver_account_id>' and account_b_id = '<creator_account_id>'))
order by updated_at desc;

select id, recipient_account_id, kind, status, attempts, last_error,
       friendship_id, delivered_at
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

4. Verify active create by marker:

```sql
select id, title, status, fire_at, duration_minutes, creator_reminder_id,
       receiver_reminder_id, created_at, updated_at
from shared_reminders
where title like '%<marker>%'
order by created_at desc;

select id, recipient_account_id, kind, status, attempts, last_error,
       shared_reminder_id, payload, delivered_at
from product_notifications
where shared_reminder_id = '<shared_reminder_id>'
order by created_at;
```

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

## Evidence To Report

- bridge response and late output if the bridge returned the placeholder
- direct friendship id/status and owner notification status
- created shared reminder id and active status
- receiver creation notification status
- cancel result and final cancelled status
- receiver cancellation-notification status when creator cancels, or creator
  cancellation-notification status when receiver cancels
- cleanup evidence showing the marked runtime reminders were cancelled through
  Scheduling
- any layer isolation result: natural-language route vs canonical tool
