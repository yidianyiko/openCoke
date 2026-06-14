---
kind: investigation
status: open
title: Eva 2026-06-14 chat root-cause analysis (interactive-turn recurrence)
created_at: 2026-06-14
updated_at: 2026-06-15
surface:
  - clean-rebuild
  - conversation-runtime
  - reminder
  - social-scheduling
  - wechat-personal
related:
  - docs/issues/2026-06-06-eva-chat-rca.md
---

# Eva 2026-06-14 Chat RCA

## Fix Status (updated 2026-06-15)

Deployed to gcp-coke (`main`) and smoke-verified on the real WeChat path:

- **RC0** ✅ deployed + verified — relative-time rendering; live replies show
  "今天上午0点55分", "明天晚上6点".
- **RC1** ✅ deployed + verified — "明天晚上6点" stored as 18:00 (not 06:00).
- **RC2** ✅ deployed — conflict/refusal wording bound to typed outcome. NOTE: the
  first RC2 deploy regressed prose list replies into grounded-failure recovery
  (force-JSON on outcome turns); caught by live smoke, hotfixed (prose tolerance
  restored, domain_claim guard kept), redeployed.
- **RC5** ✅ deployed + verified — deterministic schedule-by-date; live "今天日程"
  lists exactly today's items, no fired/past pollution.
- **RC6** ✅ deployed + verified — fire completion; live one-time reminder fired →
  completed → retired; recurring advancement unit+integration proven.

Committed, reviewed, NOT merged to main:

- **RC3+RC7** 🔶 friend-agenda questions route to availability_query (busy/free),
  never list_shared/titles; vague queries default to a documented today..+7d
  window. On branch `fix/friend-schedule-busy-free` (`11c65e8d`). Reviewed: in
  scope, 357 unit tests pass, RC2 prose hotfix not regressed. NOT merged; will
  likely need an express.py conflict resolution against the deepseek swap.

Not started:

- **RC4** ⬜ contextual correction misclassified as a new scheduling intent (the
  "失忆"). Last remaining; serializes on plan.py.

### Acceptance note (2026-06-15, post-1h auto check)

main is green (973 unit tests) but the only NEW thing that landed on main during
the hour is an UNRELATED, eval-backed **DeepSeek V4 swap for the `detector` and
`express` roles** (`cad1b465`; decision recorded in
`docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md`). It is NOT yet
deployed — production still runs GLM-5.1 + RC0–6.

CRITICAL: the deepseek swap changes the models BEHIND RC0 (express rendering),
RC1 (detector AM/PM), and RC2 (express conflict-claim + prose handling). All my
RC0/RC1/RC2 live smokes were under GLM-5.1, so deploying main re-opens those as
UNVERIFIED for the deployed model and requires a full real-account re-smoke. The
RC4 task is still missing and RC3+RC7 is unmerged. Therefore the auto-acceptance
did NOT blanket-deploy; this is the "investigate" path.

Main commits: RC0 `340bca15`, RC6 `61a18629`, RC2 `fbba63bb`, RC5 `b76cc24a`,
RC2 hotfix `cec8c5b4`, RC1 `b8b8a21e` (+ merge commits). Each fix was reviewed by
running its tests directly (not trusting Codex's report).

## Summary

On `2026-06-14 Asia/Shanghai` (evening), Eva hit a cluster of scheduling and
memory failures that are **recurrences of the documented 2026-06-06 Eva RCA**
(RC3 soft-success, RC5 privacy leak, date/time confusion, history
contamination). Production HEAD already contains every 06-06 fix commit, so this
is **not a deploy gap**. The 06-06 fixes hardened specific domain tools and
*render-mode/system* turns; today's failures all occurred on **interactive
inbound turns**, where the Plan and Express LLM layers still fabricate
schedules, conflicts, and success claims from conversation history instead of
being bound to deterministic domain outcomes.

RCA only. No production behavior changed by this report.

## Runtime Identity (note: eva account rebound)

- host `gcp-coke`, compose root `/home/whoami/coke-clean`, DB timezone `UTC`.
- Eva's WeChat openid `o9cq8084UWQ0BnDlHIoNtko_KaAA@im.wechat` **rebound to a new
  account `2ca837a3-4f32-4272-a935-a71b5af1209a`** (created `2026-06-14 13:12
  Asia/Shanghai`). The 06-06 eva account `94566791-...` is now orphaned (0
  recent traffic). This matches the single-bot-session caveat: re-scanning bumps
  the prior binding.
- conversation `c93f7cd8-6dfe-4ff7-b401-d36cc6f6f1e9`.
- friend `olivers` = `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`.
- deployed SHA `cdc32155` == local HEAD (contains all eva fix commits:
  `696c8c32`, `8ff8de1c`, `fa71e487`, `a3898934`, `39885e01`, `10343ce3`,
  `09498bf3`).

## Durable Facts (Postgres)

Eva's tomorrow (`2026-06-15`) reminders are only two **shared** projections,
both co-owned with olivers:

| title | local_trigger | dur | kind | creator | created | last change |
| --- | --- | --- | --- | --- | --- | --- |
| 晚饭 | 2026-06-15 19:30 | 60 | shared_projection | olivers | 15:44 | 15:44 |
| 开会 | 2026-06-15 **06:00** | 30 | shared_projection | eva | 18:02 | 18:02:47 |

Eva's personal reminders: 出门 (06-14 13:41, fired), 看 openCoke 结果 (06-22 09:00),
续订服务 (07-03 14:00), 去跑步 (06-14 20:00, fired), 复盘今天 (daily 22:00). The
fired one-time reminders (出门, 去跑步) remain `lifecycle='active'`.

## Evidence Timeline (Asia/Shanghai)

```
18:01 eva 约olivers明天晚上八点开会          -> coke 约不了，明晚八点已有安排，时间冲突  (CORRECT: 20:00 ∈ 晚饭19:30-20:30)
18:02 eva 约六点吧                            -> coke 已建好「开会」，明天早上6点开始       (BUG: 六点 -> 06:00 AM)
18:02 eva 改成半小时吧                        -> coke 已改成30分钟                          (duration edit landed 18:02:47)
18:03 eva 不对 是晚上六点                     -> coke 是晚上6点…我马上帮你改过来           (BUG: durable 开会 unchanged, still 06:00)
21:16 eva 请让oliver晚上21:20找我             -> coke 约不了，那个时间有冲突了             (HALLUCINATED conflict)
21:17 eva 今天oliver有什么安排？              -> coke Oliver今天: 开会6:00, 晚饭19:30       (PRIVACY LEAK + today/tomorrow confusion)
21:23 eva 为什么21:20的时间会冲突呢           -> coke 晚饭19:30-60min…不过21:20已过…判断有误 (admits fabrication)
21:24 eva 你刚刚为什么会判断有误呢            -> coke 只看Oliver有"晚饭"就报冲突，没算时间
21:24 eva 为什么oliver今天会有开会的日程呢    -> coke 之前帮他约的，改到晚上6点…           (claims 18:00 but durable is 06:00)
21:25 eva 不是明天吗？                        -> coke 你是说明天约Oliver吗?具体什么时间?    (CONTEXT LOSS: correction read as new booking)
21:26 eva 我不是约了oliver明天开会吗          -> coke 对哦，是明天开会！明天具体什么时间?
21:26 eva 我明天的日程呢                      -> coke 开会6:00, 晚饭19:30 (2项)
21:29 eva 我明天有哪些日程                    -> coke 出门13:41, 去跑步20:00, 复盘22:00, 开会次日6:00, 晚饭次日19:30 (5项)  (INCONSISTENT + past items)
```

Per-turn pipeline phases (`turn_latency_event` from `coke-worker`): every inbound
turn ran `llm_json.turn_plan`; reminder/scheduling turns also ran
`llm_json.detected_reminder_fields`. Note seq22 ("不是明天吗") ran
`detected_reminder_fields` — i.e. the correction was processed as a fresh
reminder/scheduling intent. seq24 ran `detected_reminder_fields`; seq25 did not —
the two "明天日程" answers took different pipeline paths, producing different lists.

## Root Causes

### RC0 (deepest): The user-facing Express layer has no clock — temporal grounding is computed and threaded to Plan but withheld from the only layer that talks to the user

This is the underlying cause behind the "tomorrow shown as today" leak and a
whole class of time errors (including 06-06 RC1's wrong "还有1小时").

Evidence (code, deployed HEAD `cdc32155`):

- The runtime DOES compute an authoritative clock per turn:
  `_current_time_facts` (`coke/turn/runner.py`) puts
  `current_time` (ISO, in the user's timezone) into `trusted_facts`.
- That clock reaches the **Plan** layer: `_plan_request`
  (`coke/turn/inbound/pipeline.py:225`) sets `trusted_facts=trusted_facts`, and
  the planner forwards `trusted_facts` to the LLM (`plan.py:125`).
- The **Execute** detector has its own separate clock: each handler computes
  `self._now()` (`handlers/reminder.py:30`, `handlers/social.py:27`) at
  execution time.
- The **Express** layer — the *sole producer of user-visible prose* — gets
  **none of it**. `_express_request` (`pipeline.py:236`) builds `ExpressRequest`
  from `settled_outcome`, `current_input_messages`, `conversation_history`,
  `persona`, and only pulls `onboarding_guidance` out of `trusted_facts`. It
  never passes `current_time` (or `trusted_facts`). `ExpressAgent._agent_input`
  (`express.py:149`) confirms the payload has no `now`/today field, and dates
  are serialized as bare ISO strings (`_plain_value` -> `value.isoformat()`).

Consequence: Express must render every relative-time expression — "今天/明天",
"还有1小时", "早上6点/晚上6点", "今天/明天的日程" — with **no reference clock**.
The one piece of context it does receive is `conversation_history`, so it anchors
relative-time words on whatever was recently said. For seq18 it saw
`开会 2026-06-15T06:00` / `晚饭 2026-06-15T19:30` with no "today" to diff against,
inside a conversation that had just been about "今天 oliver", and labeled
tomorrow's items as 今天.

Structural smell: a single turn has **three different time sources** — Plan's
`current_time` snapshot, each Execute handler's fresh `datetime.now(UTC)`, and
Express's *nothing*. There is no single trusted "turn clock" threaded
consistently, and the user-facing layer is the one starved of it.

This also re-opens the 06-06 design review's own D1/D2 principle: history was
isolated and typed facts injected for *render-mode/system* turns, but for
*interactive* Express the runtime did the opposite — it passes raw
`conversation_history` and withholds both the clock and the structured trusted
facts. So interactive Express is exactly where "reconstruct truth from prose"
still fully lives. RC2 (fabricated conflict), RC3 (today/tomorrow leak), and the
soft-success narration are all downstream of this.

### How legacy (`coke-legacy-server`) avoided RC0

The pre-rebuild single-agent server did exactly two things the rebuild's Express
does not:

1. It always injected the clock into the agent prompt:
   `CONTEXTPROMPT_时间 = "### 系统当前时间（24小时制）{time_str}"`
   (`coke-legacy-server/agent/prompt/chat_contextprompt.py:63`).
2. It **pre-formatted every reminder time into a relative-day string in Python**,
   not in the LLM. `format_time_friendly(timestamp)`
   (`coke-legacy-server/util/time_util.py:308`) computes
   `days_diff = (dt.date() - now.date()).days` and returns 今天/明天/后天/星期X/
   M月D日 + 上午/下午/晚上 deterministically; `format_with_date` adds weekday.
   The reminder context block fed to the agent used these strings
   (`context_retrieve_tool.py:433` calls `format_time_friendly(ts)`), so the
   model read "明天上午9点" and never saw a raw timestamp or computed a relative
   day itself.

The rebuild regressed on both points: Express has no clock (RC0) and is handed
raw ISO datetimes (`_plain_value` -> `isoformat()`) to relativize on its own.
The fix direction ("B") is what legacy already did: deterministic relative-day
formatting in the fact layer, plus the trusted clock threaded to the producer.

### RC1: Explicit period word (晚上/PM) is dropped between Plan and Execute → wrong-AM/PM meeting that cannot be corrected

`coke/turn/inbound/plan.py:33` instructs the planner to keep ambiguous clock
phrases "verbatim … do NOT resolve AM/PM or dates in Plan — the detector picks
the plausible near-future reading in Execute." The Execute detector
(`coke/llm/reminder_detector.py`) near-future heuristic is written for *today*
disambiguation ("if the morning reading is already past, prefer evening"). For a
**tomorrow** reminder both 06:00 and 18:00 are future, so the heuristic
under-specifies and picked 06:00 for "六点". When eva explicitly said "晚上六点"
(PM), that period marker was not honored — the bare clock phrase re-resolved to
06:00, equal to the stored value, which then hit the **"reject no-op shared
reminder update"** guard (`2418ef7c`) and silently did nothing
(`_update_shared_reminder` -> service no-op; projection `updated_at` stuck at
18:02:47). The Express layer still emitted a soft promise ("我马上帮你改过来")
not bound to the empty outcome. Net: user corrected to PM twice; meeting is still
06:00.

Correct layer: Plan→Execute time hand-off must preserve explicit period markers
(晚上/下午/上午/morning/evening) as a typed field, not a free phrase; and a
no-op update that contradicts an explicit user correction must surface, not be
swallowed.

### RC2: Conflict claims on interactive turns are LLM-fabricated, not bound to the domain conflict outcome

The deterministic conflict check is correct. Both `personal_busy_intervals`
(`coke/composition.py:482`) and `shared_busy_intervals`
(`coke/domains/social_scheduling/repository.py:835`) use proper half-open
overlap (`interval_start < end and interval_end > start`) on local wall-clock
datetimes including date. olivers's only items are tomorrow 06:00-06:30 and
19:30-20:30; neither overlaps 21:20, and olivers has nothing today. So seq17's
"21:20 时间冲突" was **not** a domain block — the Express/Plan LLM fabricated it
(most likely carrying the genuine seq13 20:00 conflict forward through included
interactive chat history), then fabricated the 晚饭 justification, then admitted
"判断有误". The genuine seq13 20:00 conflict was correct; only the 21:20 claim is
the bug.

Correct layer: interactive-turn conflict wording must be bound to a typed
`blocked/receiver_conflict` outcome with the actual conflicting interval, never
narrated from history.

### RC3: Friend-agenda questions bypass the busy/free privacy contract

The 06-06 privacy fix (`696c8c32`) hardened the **availability tool**:
`_availability_facts` exposes only public windows (`to_public_dict`), no titles.
But seq18 "今天oliver有什么安排" did not route through `availability_query`; the
planner answered an agenda question directly from Eva's own `shared_projection`
reminders (which legitimately carry titles because Eva co-owns them) and
presented them as olivers's personal schedule, with titles and times — and as
"今天" when they are tomorrow. There is no contract/guard that a "what is my
friend doing / friend's schedule" question must be answered as busy/free only.

Correct layer: route/guard friend-schedule questions into the busy/free
availability contract; do not let the planner narrate a friend's agenda from
shared-reminder titles.

### RC4: Contextual corrections are misclassified as new scheduling intents (the "失忆")

seq22 "不是明天吗？" was a clarification that the 开会 subject is tomorrow, not
today. The planner ran `detected_reminder_fields` and answered "你是说明天约
Oliver 吗？具体明天什么时间方便呢？" — treating it as a fresh booking. The prior
subject (the 开会 shared reminder) was not carried forward as a typed
conversational subject, so a short follow-up correction reopened scheduling from
scratch.

Correct layer: follow-up/correction classification and a typed
last-subject carry-forward for interactive turns.

### RC5: No deterministic "schedule for day X" path → inconsistent lists incl. past one-time reminders

`_list` (`coke/turn/inbound/handlers/reminder.py:69`) supports
`trigger_after`/`trigger_before`, but the planner does not resolve "明天" to a
concrete range (reminder.py:415 explicitly defers date-range list resolution as
a "separate quality follow-up"). So `_list` returns all active reminders and the
Express LLM decides which to show as "明天" — non-deterministically (seq24 = 2
items, seq25 = 5 items) and including today's already-fired one-time reminders
(出门 13:41, 去跑步 20:00 still `lifecycle='active'`). Fired one-time reminders are
not retired, compounding the pollution.

Correct layer: a deterministic schedule-by-date query (resolve relative day to a
[start,end) range, exclude past/fired one-time reminders) feeding a fact block;
and a lifecycle transition for fired one-time reminders.

### RC6 (NEW, systemic P0): reminder fires never complete → recurring reminders die after one fire and one-time reminders never retire

Found while analysing this incident; not visible in the transcript text alone but
confirmed in production data.

Evidence (production, deployed HEAD `cdc32155`):

- Across the ENTIRE `reminder_fire` table: 57 fires, ALL `fire_state='claimed'`,
  `handled_at` and `completed_at` NULL for every row, even the 22 with
  `delivery_result='delivered'`. Zero fires ever reach `completed`.
- Eva's daily `复盘今天` (recurring) still has `next_fire_at = 2026-06-14 22:00`
  after it already fired at 22:00; at 2026-06-15 00:24 it has NOT advanced to
  2026-06-15 22:00.
- 12 one-time reminders are stuck `lifecycle='active'` with `next_fire_at` in the
  past (incl. eva's 出门 13:41 and 去跑步 20:00).

Root cause (code):

- `ReminderService.complete_fire` (`coke/domains/reminder/service.py:664`) is the
  only path that sets `fire_state='completed'` and then calls
  `_advance_or_complete_after_occurrence` (service.py:972), which advances the
  recurrence (`next_occurrence_after`) for recurring reminders and retires
  one-time reminders. **`complete_fire` has zero production callers** (only a unit
  test calls it).
- The production delivery callback
  `OutputLifecycleDeliveryCallbacks.record_delivery` (`coke/composition.py:286`)
  for `ReminderFireTurn`/`UndeliveredResendTurn` calls only
  `record_fire_delivery` (service.py:578), which sets `delivery_result` and
  `updated_at` and nothing else — no completion, no advancement.

Consequences:

- Recurring reminders fire exactly once and then freeze: `next_fire_at` stays in
  the past, the same occurrence is re-claimed idempotently by `occurrence_key`,
  and the series never advances. "每天晚上10点提醒我复盘" silently stops after day
  one. This is a core product-promise failure the eva transcript would not have
  revealed until tomorrow.
- One-time reminders never retire, so they pollute every schedule listing
  (this is the durable half of RC5's "today's fired items shown under 明天") and
  count as busy intervals for any availability/conflict query whose window covers
  the past.

Correct layer: the fire lifecycle must settle on delivery. After a
`ReminderFireTurn` delivers, the delivered fires must be completed (idempotently),
which advances recurring reminders and retires one-time reminders. Decide the
policy for undelivered fires (retry/settle) explicitly; do not leave fires
permanently `claimed`.

NOTE: this is a separate, larger fix than RC0 and is NOT in the RC0 Codex task.
It should be its own change.

### RC7 (NEW): "what is my friend doing [today]" has no correct capability → eva saw the wrong schedule

Direct answer to the follow-up "why did eva ask olivers's schedule and see the
wrong arrangements" (seq18: "今天oliver有什么安排？" -> "Oliver 今天有这些安排：
开会 6:00、晚饭 19:30").

The friend-facing READ surface (param_schema.py) is only:

- `social_scheduling.availability_query` — requires `participant` +
  `local_start` + `local_end`; returns busy/free windows ONLY (no titles).
- `social_scheduling.list_shared` — optional `participant`, NO date params;
  returns ALL active shared reminders between the two, WITH titles.
- `reminder.list` — the requester's OWN reminders only (includes the requester's
  `shared_projection` copies of shared reminders).

There is no "query a friend's actual schedule" action, and there should not be
one for a friend's PRIVATE reminders (privacy). So "今天oliver有什么安排" has no
correct answer surface. Evidence that seq18 was answered from shared data, not
olivers's real schedule:

- An `availability_query` for "今天" would have reported olivers FREE today (his
  only items are tomorrow 06-15), i.e. "今天他有空" — not a list of activities.
- The exact output "开会 6:00 / 晚饭 19:30" matches eva's two `shared_projection`
  rows (06-15) byte-for-byte. That output can only come from a shared-reminder
  read (`list_shared`, or `reminder.list` surfacing eva's own shared projections),
  presented AS olivers's personal agenda.

So eva never saw olivers's schedule. She saw the shared reminders between them,
and that read was wrong on four axes at once:

1. it leaked activity titles instead of busy/free (RC3);
2. `list_shared` has NO date filter, so the "今天" qualifier was ignored and
   tomorrow's items were returned (RC5-class);
3. they were rendered as "今天" though they are 06-15 (RC0, no Express clock);
4. 开会 carried the wrong stored time 06:00 instead of 18:00 (RC1).

Underlying problem: the runtime has no bounded concept of "a friend's schedule".
A friend-schedule question falls back to whatever read the planner can map it to
(`list_shared` / own `reminder.list`), which returns shared items, undated and
titled, framed as the friend's agenda. The fix is product-level: define what a
friend-schedule question may return (busy/free over a resolved date range, never
private titles) and route such questions there, instead of letting them resolve
to `list_shared`. This depends on RC0 (clock) and RC5 (date-range resolution).

## "Identical to olivers" explained (user's key question A)

Eva's only tomorrow items are the two shared reminders co-owned with olivers, so
they project onto both calendars by design → identical. Eva has no distinct
one-time reminder for tomorrow. The thing she believed she booked differently
(开会 8pm→6pm) is mis-stored at 6 AM (RC1), so her "我约了不一样的" expectation is
broken by the time bug, not by a data mix-up between the two accounts.

## Cross-cutting conclusion

Every failure is the same anti-pattern the 06-06 design review named (D1/D2/D3):
user-visible claims reconstructed from conversation prose/history instead of
bound to typed domain outcomes, with history not isolated. Those fixes were
applied to render-mode/system turns and specific domain tools, but **interactive
inbound turns (Plan + Execute + Express) were not brought under the same
fact-binding discipline**, and that is exactly where 2026-06-14 failed.

## Recommended Fix Order (proposed, not yet implemented)

1. P0 RC1: typed period-of-day in the Plan→Execute time hand-off + surface
   no-op updates that contradict an explicit user correction.
2. P0 RC2: bind interactive conflict wording to the typed conflict outcome.
3. P1 RC3: route friend-schedule/agenda questions through busy/free availability.
4. P1 RC4: typed last-subject carry-forward + correction classification.
5. P1 RC5: deterministic schedule-by-date query + retire fired one-time
   reminders.
6. P2: extend the Eva regression corpus (`09498bf3`) with these interactive-turn
   cases so the recurrence is caught.
