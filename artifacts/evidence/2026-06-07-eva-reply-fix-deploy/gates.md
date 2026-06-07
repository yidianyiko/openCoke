# Eva Reply Fix Deploy Evidence

Date: `2026-06-07`
Target commit: `b4859e057486e00498ed4c802ebc3a32482e3703`
Previous deployed commit: `fb3efb5c699c17fc23cf913dad1171bc8fe4baab`
Production host: `gcp-coke`
Remote root: `/home/whoami/coke-clean`

## Gate A - Local Green And Pre-Deploy Reachability

Command:

```text
.venv/bin/python -m pytest tests/unit/coke -q
```

Output:

```text
collected 823 items
...
============================= 823 passed in 20.79s =============================
```

Command:

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 gcp-coke hostname
```

Output:

```text
coke-server
```

Before deploy, relay to connector from inside `coke-outbox-relay`:

```text
http_code=000 exit=7
```

Before deploy, worker to connector from inside `coke-worker`:

```text
http_code=200 exit=0
```

Remote deployed SHA before deploy:

```text
fb3efb5c699c17fc23cf913dad1171bc8fe4baab
```

## Gate B - Canonical Redeploy

Command:

```text
bash scripts/deploy-compose-to-gcp.sh
```

Selected output:

```text
[deploy-clean] local sha b4859e057486e00498ed4c802ebc3a32482e3703
[deploy-clean] last deployed sha fb3efb5c699c17fc23cf913dad1171bc8fe4baab
[deploy-clean] deploy tier backend
[deploy-clean] changed paths since deployed sha:
  coke/llm/agno_interaction_agent.py
  coke/turn/output_protocol.py
  coke/turn/runner.py
  docker-compose.clean.yml
  docs/issues/2026-06-07-shared-reminder-false-success.md
  docs/superpowers/plans/2026-06-07-shared-reminder-false-success.md
  tests/unit/coke/llm/test_interaction_agent.py
  tests/unit/coke/turn/test_output_protocol.py
  tests/unit/coke/turn/test_turn_runner.py
...
 Container coke-clean-coke-api-1 Recreated
 Container coke-clean-coke-outbox-relay-1 Recreated
 Container coke-clean-coke-worker-1 Recreated
 Container coke-clean-coke-scheduler-1 Recreated
...
[deploy-clean] clean deploy health checks passed
```

Deployed SHA after deploy:

```text
b4859e057486e00498ed4c802ebc3a32482e3703
```

Public healthz:

```text
{"ok":true}
```

Relay `extra_hosts` from `docker inspect coke-clean-coke-outbox-relay-1`:

```text
["host.docker.internal:host-gateway"]
```

Relay container status after recreate:

```text
d511bd75b15d coke-clean-coke-outbox-relay Up 20 seconds
```

## Gate C - Relay Can Reach Connector

After deploy, relay to connector from inside `coke-outbox-relay`:

```text
http_code=200 exit=0
```

Before/after comparison:

```text
before: http_code=000 exit=7
after:  http_code=200 exit=0
```

## Gate D - Eva Real Turn Path

Eva account:

```text
94566791-4d39-4b28-9d9f-367c1ed0be2c
```

Connector state was checked with token values masked. Eva's connected session:

```text
{"session_id": "4fd4f7799442421a98933620ff01ee73", "account_id": "945667914d394b289d9f367c1ed0be2c", "status": "connected", "token_key_count": 1, "context_token_keys": ["o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat"], "token_lengths": {"o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat": 136}, "cursor_present": true}
```

Webhook post output:

```text
prepared marker=server-verify-20260607T070825Z message_id=codex-server-verify-20260607T070825Z-eva wxid=o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat session_id=4fd4f7799442421a98933620ff01ee73 context_token_len=136
{"http_status": 202, "marker": "server-verify-20260607T070825Z", "message_id": "codex-server-verify-20260607T070825Z-eva", "response": {"accepted": true, "account_id": "945667914d394b289d9f367c1ed0be2c", "channel_id": "beeeed53803847bc9164c43199ea6e59", "channel_identity_id": "a202a065ddf542a7b9b749faa654dad7", "created_account": false, "provider_subject": "o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat", "provider_type": "wechat_personal", "raw_event_id": "codex-server-verify-20260607T070825Z-eva"}, "text": "提醒我 server-verify-20260607T070825Z 明天上午9点"}
```

Postgres turn verdict:

```text
turn_id                              | trigger_id                                       | started_at                    | completed_at                  | disposition | reason_code | outbound_message_count | reply_attempt_count | waiting_attempt_count
272feff9-6715-49cf-9a9d-b5637a42d584 | inbound:codex-server-verify-20260607T070825Z-eva | 2026-06-07 07:08:26.707084+00 | 2026-06-07 07:08:58.355372+00 | replied     | reply_ready | 1                      | 1                   | 0
```

Outbound reply:

```text
outbound_message_id                  | segment_index | created_at                    | reply_text
c98b2440-c375-47d5-8f8c-f5cb2cc6ff8d | 1             | 2026-06-07 07:08:58.355372+00 | 好的，明天上午9点提醒你 server-verify-20260607T070825Z
```

Reply delivery attempt:

```text
attempt_id                           | status | provider_message_id_present | error_code | delivery_source | delivery_intent                         | context_token_source | attempted_at
b5cdb1d3-a73c-4cb0-b7fe-b8a8eb0e741f | sent   | t                           |            | reply           | 272feff9671549cf9a9db5637a42d584:reply:1 | trigger_payload      | 2026-06-07 07:09:02.585214+00
```

Waiting delivery:

```text
waiting_attempt_count = 0
```

Cleanup through `ReminderService.delete_reminder`:

```text
{'state': 'succeeded', 'reminder_id': '1b84e90853a946efb2534073d226aa00', 'fact': {}}
```

Final reminder lifecycle:

```text
id                                   | owner_account_id                     | content                         | next_fire_at             | lifecycle | updated_at
1b84e908-53a9-46ef-b253-4073d226aa00 | 94566791-4d39-4b28-9d9f-367c1ed0be2c | server-verify-20260607T070825Z | 2026-06-08 01:00:00+00 | deleted   | 2026-06-07 07:11:18.647503+00
```

## Notes

- The actual context token was not printed.
- WeChat personal records `sent`; no read receipt was claimed.
- No fallback account was used.
