---
name: v6-wechat-smoke
description: Use when running the openCoke agent test-set v6 behavioral smoke over the wechat_personal channel against the deployed clean stack, verifying NL turns route to the correct domain.operation and produce (or refuse) the right Postgres rows.
---

# WeChat v6 Behavioral Smoke

## Overview

`scripts/smoke/v6_wechat_smoke.py` drives the human-authored
`openCoke-agent-test-set-v6` (encoded in `scripts/smoke/v6_cases.py`) through
the deployed clean stack over the **`wechat_personal`** channel and verifies
each turn against the clean Postgres rows.

This is the behavioral complement to `coke-agent-smoke` (`clean_smoke.py`):

- `coke-agent-smoke` verifies infrastructure plumbing (first-contact
  provisioning, friendship/shared APIs, reminder fire) over **WhatsApp**.
- This harness verifies **turn-level NL behavior** — that a natural-language
  message routes to the correct `domain.operation` and creates or refuses the
  right domain rows — over **WeChat personal**.

Core principle (shared): the assistant reply is a hypothesis; the clean
Postgres rows are the verdict. A turn's structural intent is its materialized
`staged_command` rows (`domain.operation`). We never assert reply wording.

## Product Decisions Baked In

- **日程 == reminder.** There is no separate calendar-event entity. A personal
  schedule is a personal reminder (with `duration_minutes`). The v6 D-group
  maps onto `reminder.*`, not a distinct domain.
- **Capability gaps** (cases marked `gap=...`) target behavior the product does
  NOT implement. The smoke records current behavior and marks them
  `expected_gap`; it never greens the v6-desired behavior:
  - `scheduling_conflict_001` (E4): receiver conflict is detected and the create
    is blocked, but no alternative-time suggestion is produced.
  - `scheduling_reschedule_001/002` (E5/E6): there is no reschedule operation.
  - `calendar_self_create_002` (D3): no self-reminder conflict warning.
  - `reminder_005` (A5): vague-time best-guess vs clarify both acceptable.

Negative assertions ("不允许发生") are enforced for **every** case, including
gap cases.

## Channel Payload

```text
POST /webhooks/wechat/personal
{"wxid": "...", "message_id": "...", "text": "...", "sender_name": "..."}
```

Field names come from `coke/providers/wechat_personal.py`. These were
field-name assumptions until validated against a real connector — confirm
against the live connector before trusting a real-account run.

## Required Env

```bash
export COKE_SMOKE_API_BASE="https://coke.keep4oforever.com"
export COKE_SMOKE_DB_URL="postgresql+psycopg://..."
# Requester = the real account being simulated (e.g. olivers).
export COKE_SMOKE_SENDER_A='{"wxid":"<olivers_wxid>","push_name":"olivers"}'
# Optional:
export COKE_SMOKE_WEBHOOK_SECRET="..."     # if the webhook requires a secret
export COKE_SMOKE_TIMEZONE="Asia/Shanghai"
export COKE_SMOKE_POLL_TIMEOUT="90"
```

Friend personas required by a case ("张三", two "Oliver"s, ...) are provisioned
as **run-scoped synthetic** `wechat_personal` accounts so the smoke never
mutates the real friend account.

## Run Modes

```bash
# Offline: validate corpus, print the execution plan, show a sample payload.
.venv/bin/python -m scripts.smoke.v6_wechat_smoke --dry-run

# Live (default webhook injection). Subsets:
.venv/bin/python -m scripts.smoke.v6_wechat_smoke --first-round
.venv/bin/python -m scripts.smoke.v6_wechat_smoke --group A_personal_reminder
.venv/bin/python -m scripts.smoke.v6_wechat_smoke --case reminder_002 --case scheduling_001
.venv/bin/python -m scripts.smoke.v6_wechat_smoke          # full 26-case corpus
```

Evidence is written to `artifacts/evidence/v6-wechat-smoke/<run-id>.json`.

## What The Harness Verifies Per Case

1. Inject the case message from the requester via the webhook.
2. Wait for the completed `turn` that consumed that inbound event
   (`message.causal_inbound_event_id` -> `turn` by seq window).
3. Collect the verdict: materialized `staged_command` ops, `output_disposition`,
   outbound `message`, `pending_clarification`, and the diff of active
   `reminder` / `shared_reminder` rows before vs after.
4. Assert:
   - forbidden ops did NOT materialize (always),
   - a reply was produced when `reply_expected`,
   - for non-gap cases: the expected ops materialized and the outcome-shaped
     rows exist (create -> new row; clarify/chat -> no new product row),
   - for gap cases: record current behavior, mark `expected_gap`.

## Limitations

- A live webhook smoke runs at real wall-clock time; it cannot pin the per-case
  `当前时间`. The harness asserts **intent routing + row existence/absence**,
  not exact temporal resolution. Precise time correctness belongs to the
  reminder eval corpus, not this smoke.
- Strongly time-anchored cases (e.g. "今天 8-9" run after 09:00) may legitimately
  clarify/refuse; treat those as routing-verified, not create-verified.

## Explicit Non-Goals

- No reply-wording assertions (that is an eval concern).
- No new product features to make a v6 case pass. Gaps stay gaps.
- No mutation of the real friend account; friend personas are synthetic.
