---
kind: plan
status: implemented
topic: v6 wechat behavioral smoke
date: 2026-06-11
---

# v6 WeChat Behavioral Smoke

## Goal

Cover the human-authored `openCoke-agent-test-set-v6` as a runnable smoke over
the `wechat_personal` channel, and remove the dead pre-rebuild smoke skills.

## Context

- `coke-agent-smoke` (`scripts/smoke/clean_smoke.py`) is the only live smoke. It
  is **WhatsApp/Evolution only** and verifies infrastructure plumbing (5 phases:
  first-contact provisioning, NL personal reminder, friendship API, shared
  reminder API, reminder fire). It asserts DB rows, not turn-level NL behavior.
- Two skills referenced the deleted pre-rebuild stack and were unrunnable:
  `production-real-user-flow-smoke` (Mongo / Gateway / product_notifications /
  ClawScale request-response) and `reminder-crud-case-testing`
  (`scripts/simulate_user_path.py`, `agent/runner/agent_runner.py`, `start.sh`,
  `pm2-manager.sh` — all absent on `main`).
- The `wechat_personal` channel exists end to end: provider
  (`coke/providers/wechat_personal.py`), webhook (`POST /webhooks/wechat/personal`
  in `coke/api/provider_webhooks.py`), but had **no smoke coverage**.

## Capability Survey (v6 vs current backend)

The v2 turn pipeline action vocab (`coke/turn/v2/param_schema.py`):

- `reminder`: create / update / delete / complete / list / batch_create (`kind`
  supports `recurring`).
- `social_scheduling`: availability_query / create_shared_reminder /
  cancel_shared_reminder / list_shared.
- `friendship`, `settings`, `calendar_import`.

Mapping v6's 26 cases:

| v6 group | backend | smoke |
| --- | --- | --- |
| A1–A5 personal reminders | reminder.create | covered |
| B1–B3 recurring | reminder.create kind=recurring | covered |
| C1–C3 availability | social_scheduling.availability_query + clarify | covered |
| D1–D5 self schedule | **reminder.\*** (日程 == reminder) | covered |
| E1–E3, E7–E8 scheduling | create/cancel shared + clarify | covered |
| E4 conflict suggestion | conflict blocks; **no alternative suggestion** | gap |
| E5/E6 reschedule | **no reschedule op** | gap |

Decisions (confirmed with the user 2026-06-11):

- **日程 == reminder.** No separate calendar-event entity. D-group maps to
  `reminder.*`.
- E4 alternative-time suggestion, E5/E6 reschedule, D3 self-conflict warning,
  and A5 vague-time are **capability gaps**. The smoke records current behavior
  and marks them `expected_gap`; it does not build product features to green
  them. Negative assertions are still enforced for gap cases.

## Verdict Model

The structural intent of a turn is its materialized `staged_command` rows
(`domain.operation`). Per case:

1. Inject the message via `POST /webhooks/wechat/personal`.
2. Resolve the turn: `message.causal_inbound_event_id` -> the `turn` whose
   `[input_from_seq, input_to_seq]` window covers that inbound `seq`.
3. Collect: materialized `staged_command` ops, `output_disposition`, outbound
   `message`, `pending_clarification`, and before/after diff of active
   `reminder` / `shared_reminder` rows.
4. Assert forbidden ops absent (always), reply present when expected, expected
   ops materialized + outcome rows present (non-gap), or record behavior (gap).

We never assert reply wording (eval concern).

## Deliverables

- `scripts/smoke/v6_cases.py` — 26 cases as typed specs (message, fixtures,
  expected ops, forbidden ops, outcome, gap flags). Unit-validated against the
  live action schema so it cannot drift.
- `scripts/smoke/v6_wechat_smoke.py` — runner: wechat payload injection, run-
  scoped synthetic friend provisioning, fixture seeding via clean APIs
  (`/api/friends/link+join`, `/api/reminders/batch`, `/api/shared-reminders`),
  turn-verdict collection + assertion. Modes: `--dry-run`, `--first-round`,
  `--group`, `--case`, full corpus.
- `.claude/skills/v6-wechat-smoke/SKILL.md`.
- `tests/unit/coke/smoke/test_v6_wechat_smoke.py` — corpus integrity, payload
  field names, fixture time-phrase parsing, and verdict-assertion logic.
- Deleted `production-real-user-flow-smoke` and `reminder-crud-case-testing`.

## Verification

- `pytest tests/unit/coke/smoke/test_v6_wechat_smoke.py` — 12 passing.
- `python -m scripts.smoke.v6_wechat_smoke --dry-run` — corpus + plan validate.

## Live Execution Status (2026-06-11)

PROVEN end-to-end on the real **olivers** WeChat account (manual, one case):
olivers sent "过10分钟提醒我喝水" → `reminder.execute_batch` materialized →
reminder `喝水` (timed, next_fire_at +10m, tz Asia/Shanghai) → reply
"已建好「喝水」提醒，10分钟后提醒你💧" → `delivery_attempt.status='sent'`
(wechat_personal). The channel + turn pipeline + verdict model all work live.

The remaining 25 cases still need to be run and verified. Hand this to a Codex
session. **Read `.claude/skills/v6-wechat-smoke/SKILL.md` first** — it is the
playbook (hard-won facts, account map, recipe, SQL, fixtures). Key facts repeated
here so the handoff is self-contained.

### CRITICAL execution rule: send ONE message at a time, isolated

The turn pipeline **batches rapid sends from the same account into one turn**
(observed: 11 quick posts collapsed into turns with input windows like
`168→178`). That destroys both per-case attribution and per-case behavior (every
case got the last message's reply). Therefore:

- Send one message, **wait for its turn to complete** before sending the next.
  Poll the DB until the inbound message's turn has `completed_at IS NOT NULL`
  and its window is `[seq, seq]` (single message), or just sleep ~18s between
  sends. Then each case maps cleanly to one turn.
- Do NOT batch. Do NOT fire-and-forget a loop with <15s spacing.

### Other hard facts (also in the skill)

- Webhook: `POST https://coke.keep4oforever.com/webhooks/wechat/personal`,
  no secret needed. Body: `{wxid, account_id(DASHLESS hex), message_id, text,
  sender_name, session_id, context_token}`. `account_id` MUST be dashless
  (`ae02ff016fcd...`), else `channel_identity_already_bound`.
- **Use `curl`, not Python urllib** — Cloudflare returns 403 / `error code 1010`
  for the urllib User-Agent. (If scripting in Python, set a curl/browser UA.)
- requester = olivers: account `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`, wxid
  `o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat`. DB queries use the DASHED account_id.
- DB is not public; query via
  `ssh gcp-coke 'sudo docker exec -i coke-clean-postgres-1 psql -U coke -d coke'`.

### Per-case verdict (row-effect is the truth; staged_command is a soft signal)

For each EVID, resolve the turn (`message.causal_inbound_event_id` → the turn
whose `[input_from_seq,input_to_seq]` covers that inbound seq) and assert per
`scripts/smoke/v6_cases.py` `expect.outcome`:

- create_reminder → a new active `reminder` row (check `kind`: A=timed,
  B=recurring; D1 too).
- create_shared → new active `shared_reminder` row.
- cancel_reminder / cancel_shared → an active row removed.
- update_reminder → existing reminder changed, no new row.
- list / availability / clarify / chat / conflict_block → reply, no new rows.
- `forbid` tags enforced for every case incl. gaps.

### Execution order

1. **No-fixture, requester-only (11):** A1–A5, B1–B3, D1, F1, F2. Send each as
   olivers, isolated; verify row effect + kind. (chat_001/chat_002 must create
   NO reminder.)
2. **Requester reminders fixtures (D2–D5):** first seed olivers reminders via
   `POST /api/reminders/batch {owner_account_id:<dashed>, items:[...]}` (运动
   08:00 60m, etc.), then send the case message isolated and verify
   list/update/cancel effect.
3. **Friend cases (C, E):** friend persona = a second paired account
   (**lizihao** = `635d3bdc-1b02-4a08-acf4-9940b91a9de5`,
   `o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat`). Befriend olivers↔lizihao via
   `GET /api/friends/link?owner_account_id=<olivers dashed>` then
   `POST /api/friends/join {joiner_account_id:<lizihao dashed>, link_code}`.
   Remap case aliases ("张三", "Oliver", the two Olivers) onto lizihao — the
   requester is olivers so a friend cannot also be named olivers; for the
   C3 two-Oliver ambiguity you need two friend accounts (use lizihao + a
   synthetic paired account). Seed friend_busy via reminders on the friend, and
   pre-existing shared via `POST /api/shared-reminders`. Then send isolated.
   - C2 (王五 non-friend) and E3 (王五) need NO fixture — just send, expect
     clarify, no shared row.

### Capability gaps — record current behavior, do NOT build features

`reminder_005` (A5 vague time), `calendar_self_create_002` (D3 self-conflict),
`scheduling_conflict_001` (E4 alt-time suggestion), `scheduling_reschedule_001`
/`scheduling_reschedule_002` (E5/E6 reschedule). For these, only enforce the
`forbid` tags and record what actually happened; do not assert the v6-desired
behavior.

### Cleanup owed (test pollution to undo)

Today's manual/batch attempts created junk on **olivers** (ae02ff01) and the
synthetic account **6bfe382d** (锅里的汤): the `喝水` reminder and a failed
rapid-batch run (`RID v6run_20260610T163009Z`) that created batched reminders.
After verification, cancel future test reminders created on these accounts so
they do not keep firing real WeChat pushes. Do not delete unmarked user data.

### Caveat

A live webhook smoke runs at real wall-clock time; it cannot pin each case's
`当前时间`. Assert intent routing + row effect, not exact temporal resolution.
Strongly time-anchored cases (e.g. D1 "今天8-9" after 09:00) may legitimately
clarify; treat those as routing-verified.
