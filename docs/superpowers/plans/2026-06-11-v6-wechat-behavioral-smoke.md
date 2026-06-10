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

## Not Yet Done

- **Live run against production is not yet executed** (no smoke creds in the
  build environment). The live path is correct-by-construction and dry-run
  clean, but a real `wechat_personal` run must confirm the connector payload
  field names and the end-to-end verdict before any green claim.
- A live webhook smoke cannot pin each case's `当前时间`; strongly time-anchored
  cases are routing-verified, not exact-time-verified.
