---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: smoke-design
---

# Coach booking smoke — hunt design

## Why

The user described a scenario where Coke is used as a coach-booking
system: one user is a fitness coach with working hours 09:00–22:00, and
multiple students book lessons with him. Coke has **no first-class
coach-booking feature**. Booking is therefore expressed through the
existing primitives `shared_reminder` + `friend_calendar_facts`, with
the coach manually approving requests (A1 — no availability product
contract).

The goal of this smoke is to **discover** how the existing primitives
behave under coach-booking pressure, file findings, and feed those into
a separate fix pass. **This smoke does not change product code.**

## Setup

- 4 accounts:
  - `Coach Alex`
  - `Student Mei`
  - `Student Jin`
  - `Student Kai`
- Display names are unique (the duplicate-display-name guard added
  earlier this session enforces this).
- The coach sends a friend invite via `生成我的好友邀请码`; each student
  accepts via the public link session flow.
- Postgres assertion before any case runs: `friendships` has 3 active
  rows involving Alex.

If setup fails (any provision error, friend graph not at 3), the smoke
stops and reports `BLOCKED-SETUP` — no cases run.

## Cases

Cases run in this order so the harness builds up state gradually and
the parallel/destructive cases come last:

| # | Case | Expected (under A1: coach manually approves) |
| - | ---- | -------------------------------------------- |
| C1 | Happy path | Student Mei: `约教练 Alex 明天 10:00 上一节课`. Result: `shared_reminder_requests` +1 (pending); coach `接受 Mei 明天 10 点的预约`; request → accepted; both sides have a `reminders` row for 10:00. |
| C5 | Fuzzy name | Mei: `约 Alex 教练` / `约 alex` / `约 Coach`. Each should resolve to Coach Alex with no clarification needed. Then `约张教练` (no such person) — agent must refuse / clarify, not hallucinate a booking with anyone. |
| C4 | Vague time | Jin: `约教练 Alex 周三上午`. Agent must ask which hour, not pick one silently. |
| C3 | Outside window | Kai: `约教练 Alex 凌晨 3 点`. Agent should create the request normally — Coke has no availability constraint, so any agent-side refusal or invented "outside working hours" is a finding. |
| C11 | Past time | Mei: `约教练 Alex 昨天 10 点`. Agent should refuse — past times are universally invalid. |
| C7 | Modify | Mei takes the C1 accepted request and asks `把和教练 Alex 明天 10 点改成 11 点`. Time updates on the request; reminders updated for both sides. |
| C6 | Cancel | Jin creates a fresh request (`约教练 Alex 后天 14:00`), accepts, then says `取消跟教练的训练课`. Request → cancelled; both reminders gone. |
| C8 | Coach-initiated | Coach: `提醒明天 14:00 给 Student Mei 上一节课`. Pending request appears on Mei's side; Mei accepts. |
| C9 | Coach declines | Kai: `约教练 Alex 后天 16:00`. Then coach: `拒绝 Kai 的预约`. Status → declined; Kai's chat should reflect rejection (or at least not see a phantom accepted reminder). |
| C10 | Calendar facts | Mei: `教练 Alex 明天什么时候有空？` after several bookings exist. Returned slots must match the real `reminders`/`shared_reminder_requests` state for Alex — no invented availability. |
| C13 | Coach overview | Coach: `我今天有几节课？` (or `列一下我今天的课程`). Output should match accepted shared reminders for Alex today. |
| C2 | Slot collision | Jin: `约教练 Alex 大后天 10:00`. Immediately Kai: `约教练 Alex 大后天 10:00`. Two pending requests at the same slot. Both should appear in `shared_reminder_requests`. Coke is not expected to auto-detect collision; finding only if it silently merges, drops one, or accepts both without surfacing the conflict to the coach. |
| C12 | Concurrent burst | 3 students simultaneously POST: each `约教练 Alex 下周一 11:00 / 12:00 / 13:00`. All 3 requests must land; no causal-id hijack (Bug F), no Bug B empty fallbacks. |

Each case is self-contained and is allowed to leave durable state behind
for the next case (later cases assume prior accepted requests exist).
The harness does NOT reset between cases — that's intentional, since
real coach-booking traffic is incremental.

## Per-case execution model

For each case:

1. Snapshot mongo (`reminders`, `outputmessages`,
   `inputmessages`, `agent_sessions`) and postgres (`friendships`,
   `shared_reminder_requests`, `account_blocks`, `customers`).
2. Run the case's 1–3 agent turns (sending as the right
   coke_account_id; coach turns use `coach.coke_account_id`).
3. Snapshot again.
4. Compute deltas, compare against `Expected`.
5. Classify outcome:
   - `PASSED` — matches expected
   - `FINDING` — observed differs from expected, with classification:
     - `bug_pattern`: A / B / C / D1 / D2 / F / G / H / I / NEW
     - `severity`: silent-bad-side-effect | visible-error | UX-rough
   - `BLOCKED` — case could not run (e.g., setup precondition missing,
     gateway 5xx that's not the case's subject)
6. Append to evidence JSON.

A `FINDING` in one case does not stop later cases.

## Findings JSON shape

```json
{
  "case_id": "C3-outside-window",
  "verdict": "FINDING",
  "bug_pattern": "C",
  "severity": "visible-error",
  "expected": "agent creates 03:00 request, no constraint invented",
  "observed": "agent replied '凌晨太早了，约 9 点以后吧' but no shared_reminder_requests row appeared",
  "agent_reply": "...",
  "mongo_delta": {
    "reminders": {"added": 0, "modified": 0},
    "outputmessages": {"added": 1}
  },
  "postgres_delta": {
    "shared_reminder_requests": {"added": 0}
  }
}
```

The runner writes one JSON file per batch, with all cases inside, to
`artifacts/evidence/shared-reminder-agent-smoke/coach-booking-<batch>.json`.

## What the codex doing the hunt must NOT do

- Do not modify product code in `agent/` or `gateway/`.
- Do not reintroduce `blockAccount` / `unblockAccount` / `account_blocks`.
- Do not push to origin without explicit human sign-off.
- Do not weaken assertions to make a case pass.
- Do not assume coach has an availability window. A1 was chosen — coach
  approves manually; no product contract on hours.
- Do not run the fire-delivery assertion as a hard gate (smoke accounts
  hit `missing_delivery_route` 404 by design — covered by the
  `wont_fix` issue).

## Outputs the hunt must produce

1. Runner: `tools/agent_smoke/_runner_phase_coach_booking_hunt.py`
2. Evidence JSON: `artifacts/evidence/shared-reminder-agent-smoke/coach-booking-<batch>.json`
3. Summary printed to stdout:

   ```
   | case | verdict | bug_pattern | one-line observed |
   |------|---------|-------------|-------------------|
   | C1   | PASSED  |             |                   |
   | C3   | FINDING | C           | agent invented availability constraint |
   ...
   ```

4. One single commit, no push:
   `smoke(coach-booking): hunt run <batch> — N findings`
   Touching only the new runner + the evidence file.

## Fix phase (NOT part of this codex run)

After the hunt commit, the human reviews findings and classifies each
one:

- `D2` (doc only — file an issue, do not change product)
- `D3` (product contract change — needs a separate design + fix codex)

Each D3 fix is dispatched as its own codex run with its own brief.
