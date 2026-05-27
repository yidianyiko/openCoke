---
name: production-real-user-flow-smoke
description: Use when verifying Coke production behavior by simulating real account messages or actions on the server, especially shared-reminder create/accept flows, notification delivery, and cleanup of test reminders.
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
- After accepted-flow verification, cancel both runtime reminders and delete
  the marked shared request only after verifying the marker matches exactly.
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
where dr.coke_account_id in ('<requester_account_id>', '<invitee_account_id>')
order by c.display_name;
```

Confirm all rows are active. For shared reminders, also confirm the two accounts
are active friends or use the canonical scheduling tool to surface the exact
resolver error.

## Flow

1. Inspect service health and recent logs:

```bash
ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml ps'
ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml logs --since=10m coke-agent coke-bridge gateway | tail -200'
```

2. Simulate the requester message through production bridge:

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T -e MARKER='<marker>' coke-bridge python - <<'PY'
import json, os, time, urllib.request
marker = os.environ['MARKER']
key = os.environ['COKE_BRIDGE_API_KEY']
text = f'帮我约<invitee_name>，上海时间2029年1月1日10:00，标题是验收测试-{marker}，持续5分钟。'
payload = {
    'customer_id': '<requester_account_id>',
    'coke_account_id': '<requester_account_id>',
    'coke_account_display_name': '<requester_display_name>',
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

3. Verify create by marker:

```sql
select id, title, status, fire_at, duration_minutes, requester_reminder_id,
       invitee_reminder_id, created_at, updated_at
from shared_reminder_requests
where title like '%<marker>%'
order by created_at desc;

select id, recipient_account_id, kind, status, attempts, last_error,
       shared_reminder_request_id, payload, delivered_at
from product_notifications
where shared_reminder_request_id = '<request_id>'
order by created_at;
```

4. If natural-language routing fails, isolate the layer by calling the
   canonical gateway tool with the same accounts. A successful canonical call
   means the gateway/domain service is healthy and the bug is in agent routing,
   schema, or canonical argument construction.

5. Simulate invitee acceptance either through the same bridge with delivered
   `product_notification` context or directly through the canonical tool for
   isolation:

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T gateway node - <<'JS'
const key = process.env.CLAWSCALE_IDENTITY_API_KEY;
const body = {
  customer_id: '<invitee_account_id>',
  request_id: '<request_id>',
  idempotency_key: 'accept-<marker>',
};
const res = await fetch('http://127.0.0.1:4041/api/internal/scheduling/tools/accept_shared_reminder', {
  method: 'POST',
  headers: { authorization: 'Bearer ' + key, 'content-type': 'application/json' },
  body: JSON.stringify(body),
});
console.log(await res.text());
JS"
```

6. Verify accepted state and requester notification:

```sql
select id, title, status, requester_reminder_id, invitee_reminder_id,
       resolved_at, updated_at
from shared_reminder_requests
where id = '<request_id>';

select recipient_account_id, kind, status, attempts, last_error, delivered_at
from product_notifications
where shared_reminder_request_id = '<request_id>'
order by created_at;
```

7. Clean up future reminders through the bridge internal reminder API, then
   delete only the exact marked shared request:

```bash
ssh gcp-coke "cd /home/whoami/coke && docker compose -f docker-compose.prod.yml exec -T coke-bridge python - <<'PY'
import json, os, urllib.request
key = os.environ['COKE_BRIDGE_API_KEY']
for reminder_id, customer_id in [
    ('<requester_reminder_id>', '<requester_account_id>'),
    ('<invitee_reminder_id>', '<invitee_account_id>'),
]:
    req = urllib.request.Request(
        'http://127.0.0.1:8090/bridge/internal/reminders/' + reminder_id + '/cancel',
        data=json.dumps({'customer_id': customer_id}).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        print(resp.read().decode('utf-8'))
PY"
```

```sql
delete from shared_reminder_requests
where id = '<request_id>' and title = '验收测试-<marker>'
returning id, title;
```

## Evidence To Report

- bridge response and late output if the bridge returned the placeholder
- created request id and status
- invite notification status
- accept result and final request status
- requester accepted-notification status
- cleanup evidence for runtime reminders and marked Postgres rows
- any layer isolation result: natural-language route vs canonical tool
