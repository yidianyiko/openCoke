---
title: Personal reminder creation drops duration ("一小时"/"半小时") — calendar facts under-reports busy time
kind: incident
date: 2026-05-25
status: open
affected_surfaces:
  - agent/agno_agent/capabilities/reminder_intent.py
  - agent/agno_agent/adapters/reminder_command_executor.py
  - agent/agno_agent/tools/reminder_protocol/tool.py
  - agent/reminder/runtime_contract.py (validate_duration_minutes already exists)
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-badminton-20260525t045815Z.json (T04+T05)
---

# Personal reminder ignores duration words — Bug I

## What happened

Real-user badminton scenario, batch `badminton-20260525t045815Z`.

Bob said:

- T04: `提醒我周四晚上 19:00 开会一小时。`
- T05: `提醒我周五晚上 19:00 跟妈妈视频半小时。`

Coke replied positively for both:

- T04: `好啦，已帮你设置好：周四（5月28日）晚上19:00开会一小时...`
- T05: `好嘞，已经帮你设好了。周五（5月29日）晚上19:00...跟妈妈视频半小时...`

Mongo `reminders` documents show:

```
title='开会一小时'       duration_minutes=None  next_fire_at=2026-05-28 11:00 UTC
title='跟妈妈视频半小时'  duration_minutes=None  next_fire_at=2026-05-29 11:00 UTC
```

The duration ("一小时" / "半小时") was swallowed into the title string instead
of being parsed into `duration_minutes`. The reminder fires as a point event
with no time-block semantics.

## Why it matters

`gateway/packages/api/src/routes/internal-scheduling-routes.ts` exposes
`list_friend_calendar_facts` which returns "busy intervals" — but the busy
interval calculation depends on each reminder having a positive
`duration_minutes`. Bob's two reminders, even though they occupy real time on
his calendar from his perspective, are invisible to the calendar facts.

Concrete consequence demonstrated in the same batch: Alice could (after
Bug G is fixed) ask for Bob's busy times in the same week and only see the
badminton invitation she herself created (90 min, because shared reminders
DO store duration). She would NOT see Bob is busy 19:00–20:00 on Thursday
or 19:00–19:30 on Friday. She could then propose a shared reminder that
collides with Bob's actual schedule.

This breaks the "约朋友 X 时间一起 Y" promise at the data layer.

## Why this looks like a present bug, not a missing feature

- `agent/reminder/runtime_contract.py::validate_duration_minutes` already
  exists, so the backend can take a duration.
- `agent/agno_agent/tools/reminder_protocol/tool.py::visible_reminder_tool`
  accepts `duration_minutes` per the existing signature (already used by
  shared-reminder flows).
- The assistant's own reply STATES the duration ("一小时", "半小时"), proving
  the LLM extracted the concept — it just didn't pass it down through
  `reminder_intent.py` / `reminder_command_executor.py` into the tool call.

## Suggested fix layer

In `agent/agno_agent/capabilities/reminder_intent.py` (the LLM-driven intent
extractor), add `duration_minutes` to the structured output schema and the
extraction rules. Acceptable Chinese surface forms:

- `N 小时` / `N 个小时`
- `半小时` (30), `一刻钟` (15), `三刻钟` (45)
- `N 分钟` / `N 分`
- English: `for N hours`, `for N min`, `for half an hour`

In `agent/agno_agent/adapters/reminder_command_executor.py`, thread
`duration_minutes` through to the visible_reminder_tool call.

Also tighten the title extraction so the duration words are STRIPPED from
the title (`title="开会"` not `title="开会一小时"`).

Regression test in `tests/unit/agent/test_reminder_intent_capability.py`:
"提醒我周四 19:00 开会一小时" → `intent.title=="开会"`,
`intent.duration_minutes==60`.

## Verification

After fix, re-run the badminton scenario and confirm:

- Mongo `reminders` for Bob's two filler reminders show `duration_minutes=60`
  and `30` respectively.
- After Bug G is also fixed, `list_friend_calendar_facts` for Bob
  Thu–Fri shows two busy intervals (19:00–20:00 Thu, 19:00–19:30 Fri) PLUS
  the badminton 16:00–17:30 Sat.

## Cross-link

This pairs with `2026-05-25-calendar-facts-friend-name-missing.md` (Bug G).
Fixing only one leaves the feature half-broken from user perspective.
