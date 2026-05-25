---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: smoke-design
---

# Personal reminder long-tail smoke — hunt design

## Why

Personal reminders are Coke's highest-traffic supervision surface, but live
smoke coverage is still close to basic create/list/update/cancel. The current
agent reminder path supports `create`, `update`, `cancel/delete`, `complete`,
`list`, and `batch` through `visible_reminder_tool`; durable state lives in the
Mongo `reminders` collection. The bridge/customer reminder APIs support list,
create, update, complete, and cancel, but customer route validation only admits
`FREQ=DAILY` and `FREQ=WEEKLY` while the runtime RRULE subset is broader.

This smoke is a discovery hunt. It should find where production-shaped reminder
requests diverge from the product contract, file evidence, and stop. It does
not fix product code.

## Setup

- Two batches, each with one freshly provisioned account:
  - Batch A: `personal-reminder-crud-recurring-<timestamp>`
  - Batch B: `personal-reminder-time-content-list-<timestamp>`
- Batch B must run case 25 first, while the account is still empty, then run
  cases 14-24.
- Account timezone: use the provisioned account's normal runtime timezone; do
  not add cross-timezone cases.
- LLM model stays `GLM-5.1 thinking-off`; do not swap model/provider.
- Every case creates its own setup reminders through agent turns unless the
  case explicitly starts from an empty account.
- Before running a batch, verify bridge/gateway health per
  `.claude/skills/coke-agent-smoke/SKILL.md`. If the stack is down, stop as
  `BLOCKED-SETUP`.
- Before each case, snapshot Mongo and Postgres; after each case, snapshot
  again and compare deltas. Assistant reply text is evidence only after Mongo
  and Postgres agree.
- Batches may leave state behind between cases, but every case must filter by
  the batch account id and must not depend on unrelated prior smoke data.

## Cases

| # | Batch | Case | Turns | Expected behavior | product_contract_unclear |
| - | ----- | ---- | ----- | ----------------- | ------------------------ |
| 1 | A | Snooze existing one-shot | Seed `提醒我 30 分钟后喝水`; then `再过 10 分钟提醒我` | Treat as a snooze/update of the existing one-shot: same `_id`, `lifecycle_state=active`, `next_fire_at` shifts to about now+10m; no duplicate active `喝水` reminder. If the agent needs the target restated, it must ask and make no write. | false |
| 2 | A | Update time | Seed `提醒我明天早上 8 点喝水`; then `把那个喝水提醒改成下午 4 点` | Same `_id`; title preserved; schedule changes to the next valid 16:00 for that reminder context; no duplicate. | false |
| 3 | A | Update title | Seed `提醒我明天 8 点喝水`; then `把那个 8 点的提醒改成「吃药」` | Same `_id`; title becomes `吃药`; schedule preserved. | false |
| 4 | A | Update recurrence | Seed `每天 8 点提醒我喝水`; then `把每天 8 点的提醒改成只有工作日` | Same `_id`; RRULE becomes weekly weekdays, expected `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`; next fire remains a future weekday 08:00. | false |
| 5 | A | Delete by fuzzy name | Seed `提醒我明天 9 点喝水`; then `删掉喝水提醒` | `delete` is an alias for cancel: matching active reminder becomes `lifecycle_state=cancelled`, `next_fire_at=null`; no physical deletion required. | false |
| 6 | A | Complete vs delete | Seed two `吃药` reminders with distinguishable times; run `完成今天的吃药提醒`, then `删掉吃药提醒` against the remaining one | Complete sets `lifecycle_state=completed` and `completed_at`; delete/cancel sets `lifecycle_state=cancelled` and `cancelled_at`. These are semantically distinct. If target is ambiguous, agent must ask and make no write. | false |
| 7 | A | Daily recurring | `每天早 8 点提醒我喝水` | One active reminder with `schedule.rrule=FREQ=DAILY`, future `next_fire_at`, one local time. | false |
| 8 | A | Weekdays only | `工作日早 8 点提醒我喝水` | One active reminder with `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`; no unsupported daily `BYDAY`. | false |
| 9 | A | Weekly specific day | `每周三 14:00 提醒我开会` | One active reminder with `FREQ=WEEKLY;BYDAY=WE`, local time 14:00. | false |
| 10 | A | Bi-weekly | `每隔一周周一 10 点提醒我复盘` | One active reminder with `FREQ=WEEKLY;INTERVAL=2;BYDAY=MO`, local time 10:00. | false |
| 11 | A | Monthly | `每月 1 号 09:00 提醒我交房租` | Agent path should create one active reminder using `FREQ=MONTHLY` anchored on day 1 at 09:00. Runtime supports this shape; customer route support is narrower, so cross-surface parity is unclear. | true |
| 12 | A | Recurring skip | Seed weekly reminder; then `这周的不用了` | No current EXDATE/occurrence-skip operation exists. Expected safe behavior: ask/decline with no write, or explicitly explain unsupported. A silent full-series cancel/update is a finding. Proposed product: skip only the next occurrence. | true |
| 13 | A | End recurring | Seed daily reminder; then `把每天的提醒停掉` | Cancel the recurrence source: `lifecycle_state=cancelled`, `next_fire_at=null`; no future fires. | false |
| 14 | B | Past time | `提醒我昨天 10 点开会` | Refuse/report invalid schedule; no reminder created. | false |
| 15 | B | Just past | At runtime, ask for a time about five minutes before `current_time` | No past reminder should be created. Clarify or refuse is acceptable; proposed product is refuse with a future-time prompt unless user wording clearly implies tomorrow. | true |
| 16 | B | Far future | `明年 1 月 1 日 0:00 提醒我写年度计划` | Create a one-shot reminder at that future local datetime; no arbitrary horizon rejection. | false |
| 17 | B | Bare clock | Use `8 点提醒我喝水` when the live clock makes 08:00 past; also run one generated bare-clock phrase whose hour is still future today | Create at today local time when the bare clock is future, otherwise tomorrow at that clock time. Assistant reply must include the chosen date/time. | false |
| 18 | B | Relative time | Three subcases: `5 分钟后提醒我喝水`; `明早提醒我喝水`; `下下周三提醒我喝水` | `5 分钟后` creates a future one-shot. `明早` and `下下周三` lack an exact clock and should ask for the missing time, with no write. | false |
| 19 | B | Sub-minute precision | `8 点 30 分 45 秒提醒我喝水` for a future time | If runtime preserves seconds, `next_fire_at` and `schedule.local_time` should include `:45`. If product chooses minute precision, the assistant must say it rounded. Silent truncation is a finding. | true |
| 20 | B | Long title | Create a reminder whose title is 200 chars, then list | 200 chars is accepted by the customer route contract and should not be truncated in Mongo or reply. A 201-char variant, if added later, should be rejected cleanly. | false |
| 21 | B | Emoji + Chinese | `明天 9 点提醒我 🍅 番茄钟 ⏰` | Emoji and Chinese title content are preserved exactly in Mongo and visible reply. | false |
| 22 | B | Multiple at once | `提醒我每天 8 点和 12 点喝水` | Data model has one local time per reminder, so expected behavior is two active recurring reminders, both title `喝水`, one at 08:00 and one at 12:00, both `FREQ=DAILY`; not one invalid multi-time row. | false |
| 23 | B | List today's reminders | Seed today and tomorrow reminders; ask `我今天有什么提醒` | Reply should include only reminders/occurrences due today. Agent tool currently lists all active reminders, while gateway supports date-range list, so this is a contract gap to expose. | true |
| 24 | B | List by fuzzy title | Seed `喝水` and non-matching reminders; ask `我设过哪些喝水提醒` | No write. Reply should mention only matching active reminders or clearly say none. It must not hallucinate reminders absent from Mongo. | false |
| 25 | B | Empty list | Fresh account before any seed in Batch B, ask `我有什么提醒` | Reply should say no reminders / empty list; Mongo delta stays empty; no hallucinated reminder. | false |

## Per-case execution model

For each case:

1. Snapshot Mongo collections: `reminders`, `outputmessages`, `inputmessages`,
   and `agent_sessions`, filtered by the smoke account where possible.
2. Snapshot Postgres tables relevant to account identity and gateway routing:
   `customers`, route/binding tables used by the provisioned account, and any
   reminder projection tables if present.
3. Run the case's 1-3 agent turns through the bridge using the provisioned
   account's `coke_account_id`.
4. Snapshot Mongo and Postgres again.
5. Compute deltas and compare with the table expectation.
6. Classify:
   - `PASSED`: DB state and visible reply match the expected behavior.
   - `FINDING`: DB state, reply, or tool trace diverges from expectation.
   - `BLOCKED`: setup, stack health, auth/provisioning, or unrelated gateway
     failure prevents the case from exercising its target behavior.
7. Save transcript turns, DB deltas, relevant tool trace excerpts, verdict, and
   exact `bug_pattern` in the evidence JSON.

A `FINDING` does not stop later cases unless it corrupts the batch account so
badly that later preconditions cannot be built. In that case, mark only the
dependent cases `BLOCKED` and keep the original finding intact.

## Findings JSON shape

```json
{
  "batch_id": "personal-reminder-crud-recurring-20260526t120000Z",
  "account": {
    "label": "alice",
    "coke_account_id": "ck_smoke_personalreminder..._alice",
    "timezone": "Asia/Tokyo"
  },
  "case_id": "PR-04-update-recurrence",
  "verdict": "FINDING",
  "bug_pattern": "R1",
  "severity": "visible-error",
  "product_contract_unclear": false,
  "expected": "same reminder updated to FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
  "observed": "assistant claimed updated, but Mongo still had FREQ=DAILY",
  "turns": [
    {
      "speaker": "alice",
      "input_text": "把每天 8 点的提醒改成只有工作日",
      "reply_text": "...",
      "elapsed_ms": 12345,
      "output_id": "..."
    }
  ],
  "mongo_delta": {
    "reminders": {
      "added": 0,
      "modified": 1,
      "removed": 0,
      "before": [],
      "after": []
    }
  },
  "postgres_delta": {},
  "agent_trace_excerpt": {
    "tool": "reminder_domain",
    "action": "update",
    "args": {"keyword": "喝水", "rrule": "FREQ=DAILY"}
  }
}
```

Write one JSON file per batch under
`artifacts/evidence/shared-reminder-agent-smoke/`:

- `personal-reminder-crud-recurring-<batch>.json`
- `personal-reminder-time-content-list-<batch>.json`

Bug-pattern candidates:

- `A` / `B` / `C` / `D1` / `D2` / `F`: reuse existing smoke tags where they fit.
- `R1`: unsupported or wrong RRULE encoding.
- `R2`: occurrence-level recurring action applied to the whole series.
- `T1`: time inference, past-time, or precision normalization bug.
- `L1`: list scope/filtering bug.
- `M1`: multi-reminder batch cardinality/deduplication bug.
- `S1`: snooze semantics bug.
- `NEW`: use only when none of the above fits; include a one-line definition.

## What the hunt codex must NOT do

- Do not modify product code in `agent/`, `connector/`, `dao/`, or `gateway/`.
- Do not try to fix bugs found by the hunt.
- Do not swap the LLM model or thinking mode.
- Do not run more than 25 cases in a batch; this design uses two batches.
- Do not weaken expected behavior after seeing failures.
- Do not treat assistant text as proof without Mongo/Postgres verification.
- Do not add cross-timezone or calendar-import cases.
- Do not push to origin without explicit human sign-off.

## Reviewable summary

- The hunt covers all 25 requested personal reminder long-tail cases.
- It splits execution into two fresh single-account batches to control state and
  stay under the batch-size rule.
- Expected behavior is grounded in the current `visible_reminder_tool`,
  `ReminderRuntimeContract`, Mongo `reminders` fields, and gateway reminder
  routes.
- Unclear product contracts are explicitly flagged for monthly cross-surface
  parity, recurring skip, just-past time, sub-minute precision, and today-only
  list behavior.
- The smoke verdict is DB-first: assistant replies are hypotheses until Mongo
  and Postgres deltas confirm them.
- New bug-pattern tags are proposed only for gaps not covered by the existing
  shared-reminder smoke taxonomy.
