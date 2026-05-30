---
name: coke-agent-smoke
description: Use when running the clean-architecture Coke real-account smoke harness for WhatsApp first-contact, reminders, friendship, shared reminders, and reminder-fire verification against the clean Postgres schema.
---

# Coke Clean Agent Smoke

## Overview

Use the RR8 clean smoke harness in `scripts/smoke/clean_smoke.py` to drive two
senders through the rebuilt Coke stack and verify every claim against the clean
Postgres tables in `coke/schema.py`.

Core principle: **the assistant reply is a hypothesis; the clean Postgres DB is
the verdict.** A missing row in `account`, `channel_identity`, `conversation`,
`message`, `turn`, `output_disposition`, `reminder`, `friendship`,
`shared_reminder`, `reminder_projection`, `notification_fact`, or
`reminder_fire` is the bug. Do not weaken assertions to make the smoke green.

## Stack Rule: Hard Stop If Down

The clean stack must already be running. Do not start it with guessed secrets or
placeholder env. If `/healthz` is down or Postgres is unreachable, **HARD STOP**
and report the exact failed check.

Required env:

```bash
export COKE_SMOKE_API_BASE="https://coke.keep4oforever.com"
export COKE_SMOKE_DB_URL="postgresql+psycopg://..."
export COKE_SMOKE_SENDER_A='{"remote_jid":"<olivers>@s.whatsapp.net","push_name":"olivers"}'
export COKE_SMOKE_SENDER_B='{"remote_jid":"<li_zihao>@s.whatsapp.net","push_name":"李梓豪"}'
```

Optional env:

```bash
export COKE_SMOKE_EVOLUTION_INSTANCE="coke"
export COKE_SMOKE_TIMEZONE="Asia/Tokyo"
export COKE_SMOKE_POLL_TIMEOUT="180"
export COKE_SMOKE_POLL_INTERVAL="2"
export COKE_SMOKE_FIRE_DELAY_SECONDS="45"
```

Health checks:

```bash
curl -fsS "$COKE_SMOKE_API_BASE/healthz"
/data/projects/coke/.venv/bin/python -m scripts.smoke.clean_smoke --dry-run
```

## Run Modes

Synthetic webhook mode posts Evolution `messages.upsert` payloads directly to
the clean provider webhook:

```bash
/data/projects/coke/.venv/bin/python -m scripts.smoke.clean_smoke --mode webhook
```

Real WhatsApp mode does not fake inbound. It writes the exact messages to send
in the JSON transcript and polls the clean DB for inbound rows delivered by the
real Evolution webhook:

```bash
/data/projects/coke/.venv/bin/python -m scripts.smoke.clean_smoke --mode real
```

Evidence is written to:

```text
artifacts/evidence/clean-smoke/<run-id>.json
```

## What The Harness Verifies

1. First contact from each WhatsApp sender auto-provisions a `messaging_first`
   `account`, an anchor `channel_identity`, a `conversation`, inbound `message`,
   `turn`, `output_disposition`, and outbound `message` when the disposition is
   reply-like.
2. A natural-language personal reminder creates exactly one active owner-scoped
   `reminder` with `next_fire_at` and `captured_timezone`.
3. A clean `/api/friends/link` link code plus `/api/friends/join` creates exactly
   one active unordered `friendship`.
4. Clean `/api/shared-reminders` creates an active `shared_reminder`, one active
   `reminder_projection` per participant, and a `notification_fact` with
   `facts_hash` and no `payload.text`.
5. Clean `/api/reminders/batch` creates a due reminder; the scheduler must create
   `reminder_fire.delivery_result='delivered'` and an outbound `message`
   containing the reminder title.

## Explicit Non-Goals

- No Mongo queries.
- No bridge or Gateway endpoints.
- No old `tools/agent_smoke` runners.
- No `pymongo`, DAO, connector, or `memo_runtime` imports.
- No template/fallback prose classification. The DB rows are the only verdict.
