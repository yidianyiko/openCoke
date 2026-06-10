---
name: v6-wechat-smoke
description: Use when running the openCoke agent test-set v6 behavioral smoke over the wechat_personal channel against the deployed clean stack on gcp-coke, simulating a real paired account (olivers) sending WeChat messages and verifying the agent's turn/reminder/shared rows in Postgres.
---

# WeChat v6 Behavioral Smoke (playbook)

Verify turn-level NL behavior over the **`wechat_personal`** channel by
simulating a real paired account sending WeChat messages, then reading the
verdict from the clean Postgres rows. Cases live in `scripts/smoke/v6_cases.py`
(26 cases from `openCoke-agent-test-set-v6`).

This is the behavioral complement to `coke-agent-smoke` (`clean_smoke.py`, which
covers WhatsApp infra plumbing). The runner is `scripts/smoke/v6_wechat_smoke.py`.

## HARD-WON FACTS (validated live 2026-06-11 — do not re-learn the hard way)

1. **wechat_personal does NOT auto-provision on first contact** (unlike
   WhatsApp). An inbound webhook MUST carry the `account_id` of an
   already-paired account or it is rejected `identity_pairing_required`.
2. **`account_id` must be the DASHLESS hex form**, exactly as the real
   connector sends it. `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6` →
   `ae02ff016fcd4d39a189e51c8c8a31e6`. The dashed UUID gives
   `channel_identity_already_bound`.
3. The real connector inbound payload shape is:
   `{"wxid","account_id"(dashless),"message_id","text","sender_name","session_id","context_token"}`.
   Include `session_id` + `context_token`; outbound send needs a context token.
4. The webhook currently needs **no secret** (`COKE_WEBHOOK_INBOUND_SECRET`
   unset → 202; a missing-secret rejection would be 401, pairing errors are 400).
5. **`staged_command.operation` is an EXECUTION-layer name, not the planner
   vocab.** A personal create materializes as `reminder.execute_batch` /
   `reminder.detect_and_create` / `reminder.create`; a shared create as
   `social_scheduling.detect_and_create_shared_reminder` /
   `create_shared_reminder`; cancel/update as `reminder.delete_reminder` /
   `reminder.update_reminder` / `social_scheduling.cancel_shared_reminder`.
   **Read intents (list, availability) produce NO `staged_command` at all.**
   So assert at the semantic-bucket + row-effect level, never an exact op.
6. **The verdict is the row-effect diff**: snapshot active `reminder` /
   `shared_reminder` rows for the requester before, send, then diff
   (new / removed). Plus `output_disposition` and the outbound
   `delivery_attempt.status`.

## Real Paired Accounts (gcp-coke, as of 2026-06-11)

| persona | account_id (dashed)                   | wechat wxid (provider_subject)          | state |
| ------- | ------------------------------------- | --------------------------------------- | ----- |
| olivers | `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6` | `o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat` | connected |
| lizihao | `635d3bdc-1b02-4a08-acf4-9940b91a9de5` | `o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat` | connected |
| eva     | `94566791-4d39-4b28-9d9f-367c1ed0be2c` | `o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat` | connected |
| (synthetic) | `6bfe382d-f981-491e-9af4-c1c821b76020` | `wxid_cutover_20260530T101003Z` | connected |
| (synthetic) | `b4ff2825-f26e-4d3f-a887-9bf90ff96ffe` | `wxid_tzfix_tokyo_20260530T103547Z` | connected |

`o9cq…@im.wechat` are REAL WeChat openids — driving them pushes a real WeChat
message to that person. olivers/lizihao/eva are the owner's own test accounts.

## Server Access

The clean stack runs on `gcp-coke` (host `coke-server`,
`/home/whoami/coke-clean`, docker compose `coke-clean-*`). Postgres is NOT
publicly exposed; query it over SSH:

```bash
ssh gcp-coke 'sudo docker exec -i coke-clean-postgres-1 psql -U coke -d coke' <<'SQL'
  <your SQL>
SQL
```

DB url inside the compose network: `postgresql+psycopg://coke:coke@postgres:5432/coke`.
To run the python runner with DB access, run it on the server or via an SSH
tunnel to the published Postgres port.

## Manual One-Case Recipe (no script needed)

```bash
ACC="ae02ff016fcd4d39a189e51c8c8a31e6"        # olivers, DASHLESS
WXID="o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat"
EVID="manual_$(date -u +%Y%m%dT%H%M%SZ)"

curl -sS -X POST https://coke.keep4oforever.com/webhooks/wechat/personal \
  -H 'Content-Type: application/json' \
  -d "{\"wxid\":\"$WXID\",\"account_id\":\"$ACC\",\"message_id\":\"$EVID\",\"text\":\"过10分钟提醒我喝水\",\"sender_name\":\"olivers\",\"session_id\":\"${EVID}-s\",\"context_token\":\"${EVID}-ctx\"}"
# expect: {"accepted":true,...}  HTTP 202
```

Verdict SQL (resolve the turn from the inbound event, then read effects):

```sql
-- turn for the event
select t.id, t.completed_at is not null as done
from message m join turn t
  on m.conversation_id=t.conversation_id and m.seq between t.input_from_seq and t.input_to_seq
where m.causal_inbound_event_id='<EVID>' and m.direction='inbound';

-- staged ops (soft signal)
select sc.domain, sc.operation, sc.status from staged_command sc
  join turn t on t.id=sc.turn_id
  join message m on m.conversation_id=t.conversation_id and m.seq between t.input_from_seq and t.input_to_seq
where m.causal_inbound_event_id='<EVID>' and m.direction='inbound';

-- newest reminders for the account (row effect)
select content, kind, next_fire_at, captured_timezone from reminder
where owner_account_id='<DASHED account_id>' and lifecycle='active'
order by created_at desc limit 3;

-- outbound reply text + delivery
select left(m.text,120) as reply,
       (select status from delivery_attempt da where da.turn_id=t.id limit 1) as delivery
from message m join turn t on t.id=m.turn_id
  join message im on im.conversation_id=t.conversation_id and im.seq between t.input_from_seq and t.input_to_seq
where im.causal_inbound_event_id='<EVID>' and m.direction='outbound';
```

Proven round-trip (2026-06-11): olivers sent "过10分钟提醒我喝水" →
`reminder.execute_batch` materialized → reminder `喝水` timed, next_fire_at +10m,
tz Asia/Shanghai → reply "已建好「喝水」提醒，10分钟后提醒你💧" →
`delivery_attempt.status='sent'` (wechat_personal).

## Fixtures (for C / E cases)

Friend personas must be **pre-paired accounts** (use lizihao, or another paired
account). Seed via the clean APIs with the dashed account_id:

- friendship: `GET /api/friends/link?owner_account_id=<dashed>` → `link_code`,
  then `POST /api/friends/join {joiner_account_id,link_code}`.
- reminders: `POST /api/reminders/batch {owner_account_id, items:[{operation:create,content,raw_text,trigger_time,captured_timezone,kind,duration_minutes,entry_point}]}`.
- shared: `POST /api/shared-reminders {creator_account_id, receiver_account_ids,title,local_trigger_at,captured_timezone,duration_minutes,context}`.

Remap case friend aliases (张三, two Olivers) onto available real accounts; the
requester is olivers, so a friend cannot also be "olivers".

## Verdict Model Per Case

- create_reminder → a new active `reminder` row (and, for A vs F, no new shared).
- create_shared → a new active `shared_reminder` row.
- cancel_reminder / cancel_shared → an active row removed.
- update_reminder → no NEW reminder row; existing one changes.
- list / availability / clarify / chat / conflict_block → reply, no new rows.
- forbid tags (`reminder_create` / `shared_create` / `shared_cancel`) enforced
  for EVERY case incl. gaps.

## Capability Gaps (record current behavior, do NOT build features to green)

- E4 (`scheduling_conflict_001`): receiver conflict blocks; no alternative-time
  suggestion.
- E5/E6 (`scheduling_reschedule_*`): no reschedule op (cancel + create only).
- D3 (`calendar_self_create_002`): no self-reminder conflict warning.
- A5 (`reminder_005`): vague-time best-guess vs clarify both acceptable.

## Cleanup

Mark fixtures/test reminders with the run id and cancel future ones after
verification. Do not delete unmarked user data. Reminders fire and push real
WeChat messages — cancel created ones unless the run is meant to observe firing.
