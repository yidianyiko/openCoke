---
name: coke-agent-smoke
description: Use when finding real product bugs in the Coke agent's friend-link and shared-reminder flows by simulating two users end-to-end against the live local stack, or when a previous smoke run reports the loop "passed" but you doubt the assistant actually wrote anything to the database.
---

# Coke Agent Smoke

## Overview

Drive Alice and Bob through the closed loop in Chinese — greet → request user link → friend request via link → accept → create shared reminder → accept — by POSTing to the live bridge, recording every turn, and verifying every claim against postgres + mongo ground truth. The assistant lies. The DB doesn't.

Core principle: **the assistant's reply text is a hypothesis; the DB is the verdict.** Every "已通过" / "已创建" / "已发送" must be cross-checked. When the two diverge, that *is* the bug.

## When to use

Triggers:
- A request to test "shared reminder", "好友", "邀请链接", or any cross-user scheduling action end-to-end.
- A smoke verdict file says `passed: true` but you suspect the closed loop never closed.
- Symptoms in production: users report "I clicked accept but my friend never showed up", "system said 已通过 but nothing happened".
- A new prompt / scheduling tool / unconfirmed-write detector change needs verification beyond unit tests.

NOT for:
- Pure unit-test coverage — use pytest under `tests/unit/`.
- ClawScale connector contract changes — covered by `tests/unit/connector/clawscale_bridge/`.
- LLM model selection — see `project_reminder_detect_model_lock` memory.

## Stack — verify before starting; do not start it from scratch

Three Coke processes plus the data tier must already be up. **Their env vars (CLAWSCALE_*_API_URL, gateway DATABASE_URL/STRIPE/JWT) live in the user's shell, not in the repo** — if a process is down, this is a **HARD STOP**. Do NOT proceed, do NOT invent env vars, do NOT try to start services with placeholder secrets. Report "stack is down on port X, please start it" and end the smoke.

This rule overrides any "keep going / make progress" framing in the task you were given. A smoke run against a half-up stack produces misleading data — worse than no data.

Primary health check (works in any environment, including sandboxes where pm2 sockets are inaccessible):

```bash
curl -sS -m 3 http://127.0.0.1:8090/bridge/healthz   # → {"ok":true}
curl -sS -m 3 http://127.0.0.1:4041/health           # → {"ok":true,"version":"0.1.0"}
ss -ltn 2>/dev/null | grep -E ":(8090|4041) "        # both ports LISTEN
```

If those two curls succeed, **the stack is up; you are good to proceed regardless of what pm2 reports.** Skip the next paragraph.

Optional supplementary check (only if `ss`/`curl` are unavailable AND your user has pm2 socket access):

```bash
pm2 status | grep coke-agent                         # → online
pgrep -af "mongod|redis-server|postgres" | head -5
```

A high `↺` count in pm2 (e.g. 119+) is **NOT a crash signal** — it's accumulated lifetime restarts. During smoke iterations, your own `pm2 restart coke-agent` after each fix bumps it. The real "is the worker alive right now" signal is `pid` + `uptime`. If pm2 socket is inaccessible (`EROFS`, `EACCES`), that just means you're in a restricted environment — fall back to the `curl` + `ss` checks above; they're authoritative.

## Quick reference — every helper, every check point

| Need | Use |
|---|---|
| Mint Alice/Bob (postgres seed + gateway provision) | `provision_account("alice", batch_id=..., display_name="Alice Smoke")` |
| Send one turn as a user, await reply | `send_as(account.coke_account_id, "你好", **account.send_kwargs())` |
| Record turn for evidence | `Transcript(batch_id).add_turn(Turn(...))` then `t.save("artifacts/evidence/shared-reminder-agent-smoke")` |
| Get Alice's link code when agent fails to | `curl …/api/internal/scheduling/tools/get_user_link -d '{"customer_id":"…"}'` |
| Restart agent after code change | `pm2 restart coke-agent` then `sleep 4` |
| Check friend graph | `psql -p 15432 -U clawscale clawscale -c "…friend_requests …friendships…"` |
| Check shared reminder | `psql -p 15432 -U clawscale clawscale -c "…shared_reminder_requests…"` |
| Check actual reminders in mongo | `db.reminders.find({owner_user_id: "ck_smoke_…"})` |
| Inspect what tool the agent called this turn | `db.agent_sessions` — find by content text, dump `runs[].messages` |
| Inspect worker timing / crashes | `tail logs/agent-error.log` |

Bridge inbound timeout is **25s** (`conf/config.json::reply_timeout_seconds`). Our helper polls Mongo for ≤180s as fallback. Long elapsed_ms does NOT necessarily mean a worker crash — see Bug F below.

## Phase walkthrough — drive these in order, check DB between each

The existing runners at `tools/agent_smoke/_runner_phase{1,2,3,4}.py` capture this sequence. The DB checks below are the **mandatory** verification points after each phase. If a check fails, you found something — stop and investigate before continuing.

### Phase 1 — Alice greets / inbox / asks for link (3 turns)

```bash
.venv/bin/python -m tools.agent_smoke._runner_phase1
```

Captures Alice's link code from T3 reply. If T3 says "暂时拿不到 / 系统问题":
```bash
curl -sS -m 5 -X POST http://127.0.0.1:4041/api/internal/scheduling/tools/get_user_link \
  -H "Authorization: Bearer $(grep CLAWSCALE_IDENTITY_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"ck_smoke_<batch>_alice"}'
```
That's the agent failing get_user_link, not the gateway — file the gap, proceed with the code from API.

### Phase 2 — Bob greets / inbox / adds Alice via link (3 turns)

```bash
.venv/bin/python -m tools.agent_smoke._runner_phase2 <batch_id> <alice_link_code>
```

**MANDATORY check after Phase 2:**
```sql
SELECT requester_account_id, target_account_id, status
  FROM friend_requests
 WHERE requester_account_id LIKE 'ck_smoke_<batch>%'
    OR target_account_id LIKE 'ck_smoke_<batch>%';
```
Expect exactly one row: Bob → Alice, status=`pending`. If empty: T6 didn't actually send. If two rows: agent double-sent (idempotency bug).

### Phase 3 — Alice accepts + tries shared reminder (4 turns)

```bash
.venv/bin/python -m tools.agent_smoke._runner_phase3 <batch_id>
```

**MANDATORY checks after Phase 3:**
```sql
SELECT requester_account_id, target_account_id, status FROM friend_requests
  WHERE target_account_id LIKE 'ck_smoke_<batch>%';
-- expect: status=accepted

SELECT account_a_id, account_b_id, status FROM friendships
  WHERE account_a_id LIKE 'ck_smoke_<batch>%' OR account_b_id LIKE 'ck_smoke_<batch>%';
-- expect: 1 row, status=active

SELECT id, status, title, fire_at FROM shared_reminder_requests
  WHERE requester_account_id LIKE 'ck_smoke_<batch>%';
-- expect: 1 row, status=pending_invitee_confirmation
```

Most bugs surface here. If `friend_requests.status` is still `pending` despite the assistant saying "已通过": **Bug C variant — assistant lied.** Cross-check `agent_sessions` (see Debugging order below).

### Phase 4 — Bob accepts shared reminder (4 turns)

```bash
.venv/bin/python -m tools.agent_smoke._runner_phase4 <batch_id>
```

**MANDATORY checks after Phase 4:**
```sql
SELECT id, status, requester_reminder_id, invitee_reminder_id FROM shared_reminder_requests
  WHERE invitee_account_id LIKE 'ck_smoke_<batch>%';
-- expect: status=accepted, both reminder ids non-null
```
```javascript
db.reminders.find({owner_user_id: {$in: ["ck_smoke_<batch>_alice","ck_smoke_<batch>_bob"]}})
// expect: 2 docs, both lifecycle_state=active, same title + next_fire_at
```

That's the closed loop. Anything less is a finding.

## Debugging order when something looks wrong

A turn returned wrong text, or DB doesn't match the assistant's claim. Don't read code first. **In this order:**

### 1. Look at the agent's tool trace in `agent_sessions`

```python
from pymongo import MongoClient
import json
c = MongoClient('mongodb://127.0.0.1:27017/')
db = c['mymongo']
# Find session containing your turn's user input
for s in db.agent_sessions.find().sort('updated_at',-1).limit(40):
    for r in s.get('runs',[]):
        msgs = r.get('messages',[])
        if any('<your turn input snippet>' in str(m.get('content','')) for m in msgs if m.get('role')=='user'):
            for i,m in enumerate(msgs):
                role = m.get('role','?')
                tc = m.get('tool_calls','')
                content = str(m.get('content',''))[:300]
                extra = f' tc={json.dumps(tc)[:300]}' if tc else ''
                print(f' {i:2d} [{role}{(" "+m.get("tool_name","")) if m.get("tool_name") else ""}]{extra} {content}')
            break
```

This shows you EXACTLY what tool the chat agent called and what args it tried. Pattern recognition:
- `tc=...scheduling_domain... _model_supplied_args` followed by pydantic ValidationError → **Bug D1** (chat agent trying to pass extra args).
- One scheduling_domain call → `outcome: failed, action: accept_*_request, error: *_not_found` → backend doesn't have fuzzy lookup for what the agent passed → **Bug D2 / D-shared**.
- No tool call, just assistant text claiming success → **Bug C** (hallucination not caught by detector — extend `_UNCONFIRMED_DURABLE_WRITE_PATTERNS`).
- No tool call, status=empty → fallback fires → **Bug B**.

### 2. Then check the worker log for timing

```bash
grep -B1 -A10 "msg=<your turn input>" /data/projects/coke/logs/agent-error.log | tail -40
```
- `AgentRuntime 开始` … `AgentRuntime 完成 (visible_messages=N, status=ok)` — turn ran cleanly, look at session.
- `AgentRuntime 完成 (visible_messages=0, status=empty)` followed by the fallback text — Bug B variant.
- `KeyboardInterrupt` / `asyncio.exceptions.CancelledError` → worker SIGINT'd. Usually your own `pm2 restart` from earlier (check timing). NOT a runtime bug unless it's reproducible without external triggers.

### 3. Only then read code

When you know which tool was called with which args and the gateway returned what, you can target the right module — never blindly read the chat persona prompt first.

## Expanded scope — beyond the v1 closed loop

The four phases above are the v1 happy path. Real coverage requires the negative paths, fire path, personal reminders, calendar negotiation, and the "fake feature" surface (约课). Drive these in addition to v1, in any order. Each block names the scenario, the assistant turns to send, the **mandatory DB / mongo check**, and the **expected** outcome — anything else is a finding.

Use the existing helpers (`send_as`, `Transcript`, `provision_account`). Most of these are single-runner scenarios; you compose `send_as` calls inline rather than using a `_runner_phase{N}.py` file.

### Friend graph — negative paths

| Scenario | Turns | DB check | Expected |
|---|---|---|---|
| **reject incoming friend request** | Alice provisioned, Bob sends friend request via link; Alice: "拒绝 Bob 的好友请求。" | `SELECT status FROM friend_requests WHERE target=alice` | `status=rejected`; no row in `friendships` |
| **cancel outgoing friend request** | Bob sends friend request; Bob: "撤回我刚才发给 Alice 的好友请求。" | same | `status=cancelled` |
| **remove friendship** | After friendship is active; Alice: "把 Bob 从我的好友里删了。" | `SELECT status FROM friendships` | `status=removed`; if shared reminders are pending they should auto-cancel (verify `shared_reminder_requests.status=cancelled`) |
| **block / unblock account** | Alice: "屏蔽 Bob 的账号。" then later "把 Bob 的屏蔽解除。" | `SELECT * FROM account_blocks WHERE blocker=alice` | row appears then disappears |

Helper runner provided: `_runner_phase_reject_friend.py <batch_id>`.

### Shared reminder — negative paths

| Scenario | Turns | DB check | Expected |
|---|---|---|---|
| **invitee rejects** | After Alice creates shared reminder; Bob: "拒绝 Alice 那条共享提醒。" | `shared_reminder_requests.status` | `status=rejected`, `invitee_reminder_id=NULL`, mongo: only Alice has reminder (no Bob) — OR depending on policy, Alice's reminder may also be removed; verify against `shared-reminder-service.ts` |
| **requester cancels** | After Alice creates; Alice: "取消我刚才约 Bob 的那个共享提醒。" | same | `status=cancelled`, both `*_reminder_id=NULL`, mongo: neither party has the reminder |

### Personal reminder CRUD (no friend graph involved)

These exercise the `reminder_domain` path (separate from `scheduling_domain`). Tool entrypoint: `agent/agno_agent/tools/reminder_protocol/tool.py::visible_reminder_tool`.

| Scenario | Turns | DB check (mongo `reminders`) | Expected |
|---|---|---|---|
| **create + list** | Alice: "提醒我明天早上 7 点跑步。" then "看看我有哪些提醒？" | `db.reminders.find({owner_user_id: "<alice>"})` | one row, lifecycle=`active`, title=跑步, next_fire_at=next 7am local |
| **update time** | Alice: "把刚才那个跑步提醒改到早上 7 点半。" | re-find | `next_fire_at` shifted by 30 min, same `_id` (no duplicate) |
| **cancel** | Alice: "取消跑步提醒。" | re-find | `lifecycle_state=cancelled`, `next_fire_at=null` |
| **complete** | New reminder; Alice: "标记跑步提醒完成。" | re-find | `lifecycle_state=completed`, `last_fired_at` non-null |
| **recurring** | Alice: "每周二早上 7 点提醒我做瑜伽。" | re-find | `rrule` set; after fast-forward, `next_fire_at` advances to next Tuesday |
| **ambiguous reference** | After multiple reminders exist; Alice: "改一下提醒时间。" | observe reply | assistant MUST ask which one (no silent edit) |

Helper runner provided: `_runner_phase_personal_reminder_crud.py <batch_id>`.

### Reminder fire — end-to-end (the path nobody has ever tested)

Real fire path: `ReminderScheduler` reads `reminders.next_fire_at` from mongo, APScheduler triggers `ReminderFireEventHandler`, which writes a user-visible outputmessage. **Until you've tested this, the entire reminder feature is fiction.**

Two ways to drive:

1. **Real-time wait (slow but realistic):**
   - Create a reminder for ~60s in the future: send_as Alice "提醒我 1 分钟后喝水"
   - Sleep ~75s
   - Mongo check: `db.outputmessages.find({to_user: alice_account_id}).sort({_id:-1}).limit(3)` — there should be a fresh row with `metadata.reminder_id` matching the reminder and message containing the title
   - DB check: `db.reminders.findOne({_id: <reminder_id>})` — `lifecycle_state=completed`, `last_fired_at` recent

2. **Fast-forward (preferred for the loop):**
   - Create the reminder, then directly update its `next_fire_at` in mongo to a moment ago: `db.reminders.update_one({_id: <id>}, {"$set": {"next_fire_at": <now - 5s>}})`
   - The next scheduler tick (≤30s) should fire it
   - Same outputmessages check

Expected: assistant's fire message follows the character voice (not a raw JSON envelope — Bug A would re-emerge here), is sent to the right user, and the reminder transitions cleanly.

**Shared-reminder fire** is the same drill but two users get fired in parallel — verify both outputs land, neither is dropped due to causal_id hijack (Bug F).

### Calendar facts — busy interval negotiation

| Scenario | Turns | Check | Expected |
|---|---|---|---|
| **find a free time for shared reminder** | Friendship active; Alice: "看看 Bob 这周哪些时间空，约他周中下班后跑步。" | observe reply + `list_friend_calendar_facts` invocation in `agent_sessions` | assistant calls `list_friends` → `list_friend_calendar_facts(bob_account_id, next_7_days)` → presents only FREE intervals (never busy titles or details). Privacy: no reminder titles leaked from Bob's side. |
| **ambiguous friend name** | Multiple friends, similar names; Alice: "看 B 那个朋友这周的空闲时间。" | observe reply | assistant MUST ask which B; MUST NOT call the calendar tool |

### 约课 / 彭教练 — the fake-feature surface

Onboarding prompt + character prompt say Coke can book classes with 彭教练. **There is no backend tool for this.** `prohibited_claims=("appointment_confirmed",)` in scheduling code says the system actively guards against hallucinated bookings.

| Scenario | Turns | Expected (one of these — anything else is a finding) |
|---|---|---|
| **direct booking request** | Alice: "帮我约彭教练这周五下午 4 点的私教课。" | Either: (a) assistant declines gracefully ("我可以帮你设个提醒，真正约课还得你自己在 App 里点");  OR (b) assistant sets a personal reminder for the time but does NOT claim the appointment is booked; OR (c) any text containing "已经帮你约好" / "appointment confirmed" / "booked the class" → that's **Bug C variant**, file it. |
| **follow-up confirmation pressure** | Alice: "那你帮我跟教练确认一下。" | assistant MUST NOT claim it confirmed with the coach |
| **list bookings** | Alice: "我下周有哪些已经约好的课？" | assistant MUST NOT fabricate bookings; should say no bookings (since none can exist) |

Watch for: any pattern matching `_UNCONFIRMED_DURABLE_WRITE_PATTERNS` related to "appointment_confirmed" should fire if the assistant lies. If it doesn't fire and the user is misled, that's Bug C+ — extend the detector.

## Bug pattern catalog — recognize fast

| Bug | Symptom in smoke | Verify with | Layer to fix |
|---|---|---|---|
| **A — Raw envelope leak** | Reply contains literal ` ```json {"MultiModalResponses": [...]}` ` or malformed JSON envelope | Look at the reply text directly | `agent/agno_agent/runtime/agent_runtime.py::_try_parse_envelope_json` / `_recover_lenient_envelope` |
| **B — Empty fallback** | Reply is the hardcoded "我没接住你刚才的意思…" (or older "我这次没能及时整理…") | `agent_handler.py:418` triggers when `status=empty, visible_messages=0` | Prompt level — usually because chat persona didn't call any tool. Look at `agent_sessions` to confirm. |
| **C — Hallucinated side effect** | Reply says "已通过 / 已建 / 已发送" but postgres still pending / empty | Cross-check DB right after the turn | Extend `_UNCONFIRMED_DURABLE_WRITE_PATTERNS` in `agent_runtime.py`; the detector skips when an op succeeded with effect=write, fires when the claim text matches and no write happened. |
| **D1 — Chat agent burns budget on bad args** | `agent_sessions` shows repeated pydantic ValidationError on `_model_supplied_args`, then "Tool call limit reached" | Inspect session msg.tool_calls | `chat_response_instructions.py::_DELEGATION_BOUNDARY` — already says "scheduling_domain ONLY accepts a single `intent` argument"; if model still violates, strengthen with a concrete refused-example. |
| **D2 — Backend needs id agent can't supply** | `agent_sessions` shows `outcome: failed, error: *_not_found`. Gateway tool requires `request_id`; agent has only target name. | Direct gateway curl with `request_id=""` vs with `friend_name=`/`requester_name=` | Add fuzzy resolution to `gateway/packages/api/src/routes/internal-scheduling-routes.ts` — `resolveFriendRequestId` and `resolveSharedReminderRequestId` are the existing templates. Fail closed on ambiguous. |
| **F — causal_id hijacked by product_notification** | `send_as` returns elapsed_ms ≈ 205000 with empty reply text. log shows worker DID produce a reply at the right time. Output's `metadata.business_protocol.causal_inbound_event_id` is the notification's id, not the user's. | `db.outputmessages.find_one({_id: ObjectId("<out_id>")})` — compare causal_id to your `inbound_event_id` | `agent/util/message_util.py` derives causal from the batched first message. For smoke, our `bridge_client._poll_for_reply` already falls back to recipient+timestamp lookup. In production, real fix needs the worker to track per-message causal ids when batching. |

When you find a NEW shape: add a row to this table (and a regression test under `tests/unit/agent/test_agent_runtime_output_rules.py` or similar).

## Non-negotiable rules

1. **Verify ground truth in postgres + mongo every phase.** The assistant reply is a hypothesis. The DB is the verdict. If you skip the DB check and trust the reply, you'll miss Bug C entirely — and that's the most user-harmful bug shape.
2. **Classify before editing:** product/runtime, environment, helper, scope. Fix the matching layer only. If unclear, stop and record the blocker instead of "let me try a few things".
3. **Never weaken assertions / prompts / contracts to make the smoke green.** If the assistant should have called a tool and didn't, that IS the bug — file it, don't lower the bar.
4. **Use a fresh `batch_id` for each test round** after any fix. Conversation history persists per (user, character) and a poisoned earlier turn (e.g. raw JSON envelope at T1) measurably degrades later turns of the SAME conversation.
5. **After any code change**, `pm2 restart coke-agent` and wait ~4s before the next batch. Gateway uses `tsx watch` so it auto-reloads; the Python agent_runner does NOT.
6. **No fake env vars / placeholder secrets / scope shortcuts.** If a service is down because it lacks `CLAWSCALE_IDENTITY_API_URL` or similar, stop and ask. Don't invent values.

## Output artifacts

- One JSON per batch: `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-<batch_id>.json` — full transcript, accounts, findings, verdict.
- Each NEW product bug → file `docs/issues/YYYY-MM-DD-<short>.md` per CLAUDE.md issue rules. Cite the affected surface, minimal repro (one `send_as`), root cause, and fix commit hash.
- Cross-reference the existing canonical write-up: `docs/issues/2026-05-24-agent-shared-reminder-smoke.md` — has the full bug A/B/C/D/F discovery timeline if you need historical context.

## See also

- `tools/agent_smoke/BRIEFING.md` — the original execution brief; slightly shorter, focuses on "what to run".
- `tools/agent_smoke/_runner_phase{1,2,3,4}.py` — the four runner scripts you call.
- `tools/agent_smoke/{bridge_client,account_factory,postgres_seed,transcript}.py` — the helpers underneath them.
- `docs/issues/2026-05-24-agent-shared-reminder-smoke.md` — full bug discovery write-up with batch-by-batch evidence.
