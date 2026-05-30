# Coke Clean Rebuild E2E Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Destructively retire the old `coke` production stack on `gcp-coke`, promote `coke-clean` as the primary public stack, reset the clean database for go-live, and run a personal-WeChat web-first end-to-end check with honest connector evidence.

**Architecture:** Treat this as an operational cutover, not a migration: preserve the Evolution provider stack, preserve `coke-clean`, delete only the old `coke` project and its data, and move nginx product traffic to clean API/web ports. Personal WeChat remains a provider adapter behind the clean ingress/egress tier; if the old bridge is the only live connector, the webhook test must be simulation-only and outbound delivery must be reported as blocked by missing connector configuration.

**Tech Stack:** Docker Compose on `gcp-coke`, nginx, Postgres 17, Redis 7.2, Flask/Gunicorn clean API, Next.js web client, pytest.

**Plan Status:** blocked

**Verification Evidence:**
- Remote old-stack teardown: `docker compose -p coke down -v --remove-orphans`; final `docker ps` showed only `coke-clean-*` and `evolution-*`.
- Remote nginx cutover: backed up `/etc/nginx/sites-available/coke` to `/etc/nginx/sites-available/coke.before-clean-cutover-20260530T095312Z`; `nginx -t` passed and nginx reloaded.
- Remote clean DB reset: dropped/recreated `coke`, ran `coke-migrate`; post-reset database had 29 public tables and zero product rows before E2E.
- Remote health: clean API `/healthz` returned `{"ok":true}`; public `https://coke.keep4oforever.com/` and `/healthz` returned HTTP 200.
- Remote personal-WeChat simulation: `/api/auth/register`, email verification, pairing-code webhook, and reminder webhook all accepted under one web-first account; reminder row created; outbound delivery failed with `provider_not_configured`.
- Local web build: `cd web && pnpm build` passed.
- Local unit suite: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` — `380 passed`.
- Local diff check: `git diff --check` passed with no output.

**Live Empty-Output Addendum (2026-05-31):** A real personal-WeChat
friend-link join turn committed the friendship but failed the turn with
`failed / invalid_output_protocol` because GLM-5.1 returned blank assistant
content after tool work. This addendum keeps the output contract strict:
blank output remains invalid, the runtime may retry the same turn once when the
first model result is blank, and no template/fallback prose is synthesized.

**Live Personal-WeChat Happy-Path Sweep Addendum (2026-05-31):** Run the clean
product matrix A-I against the two connected personal-WeChat accounts on
`gcp-coke`: `olivers` account `ae02ff016fcd4d39a189e51c8c8a31e6` with wxid
`o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat`, and `李梓豪` account
`635d3bdc1b024a08acf49940b91a9de5` with wxid
`o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat`. Each case must use real Chinese
phrasing from the repository issue records where available, drive inbound
through the clean personal-WeChat webhook, verify clean Postgres rows, and
verify each required visible reply has a real `delivery_attempt.status='sent'`.
If a case exposes a blocking product bug, diagnose the root cause, add a red
test, watch it fail, implement the smallest fix, verify locally, redeploy
non-disruptively, rerun the failed case, and then continue the sweep.

---

### Task 1: Provider Connector Investigation

**Files:**
- Read: `coke/providers/wechat_personal.py`
- Read: `coke/config.py`
- Read: `coke/composition.py`
- Read: remote `/home/whoami/coke/.env*`
- Read: remote `/home/whoami/coke-clean/.env*`

- [x] **Step 1: Read the canonical personal-WeChat contract**

Confirm from the requirements and target architecture specs that `wechat_personal` is web-first, connection-first, and not a messaging-first auto-provisioning channel.

- [x] **Step 2: Read the clean adapter and environment mapping**

Confirm `WeChatPersonalAdapter` normalizes inbound from `wxid`, `text`, `message_id`, optional `pairing_code`, and sends outbound to `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL` with optional `COKE_PROVIDER_WECHAT_PERSONAL_API_KEY`.

- [x] **Step 3: Inspect live old and clean environment**

On `gcp-coke`, compare old `.env*` ClawScale/eCloud/character variables with clean `.env*` `COKE_PROVIDER_WECHAT_PERSONAL_*` variables.

- [x] **Step 4: Record the connector finding**

If no clean `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL` exists and the old bridge is the only ClawScale-shaped connector, record that deleting the old bridge removes live personal-WeChat connectivity and that Part 3 must use webhook-simulation mode.

### Task 2: Destructive Old Stack Teardown

**Files:**
- Remote delete: `/home/whoami/coke`
- Remote delete: old `/home/whoami/.env*.bak` matching the old stack, if present

- [x] **Step 1: Capture pre-teardown container evidence**

Run:

```bash
ssh gcp-coke 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

Expected: both `coke-clean-*` and old `coke-*` containers are visible, plus `evolution-*`.

- [x] **Step 2: Stop and remove old compose project with volumes**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke && docker compose -p coke down -v --remove-orphans'
```

Expected: old `coke` containers and old compose volumes are removed.

- [x] **Step 3: Force-remove lingering old containers**

Run:

```bash
ssh gcp-coke 'docker rm -f coke-coke-agent-1 coke-coke-bridge-1 coke-gateway-1 coke-mongo-1 coke-postgres-1 coke-redis-1 2>/dev/null || true'
```

Expected: no old containers remain.

- [x] **Step 4: Delete old code/data/logs and backup env files**

Run:

```bash
ssh gcp-coke 'rm -rf /home/whoami/coke /home/whoami/coke/.env*.bak /home/whoami/.env*.bak'
```

Expected: `/home/whoami/coke` no longer exists.

- [x] **Step 5: Confirm only clean and Evolution containers remain**

Run:

```bash
ssh gcp-coke 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

Expected: only `coke-clean-*` and `evolution-*` remain.

### Task 3: Promote Clean Stack And Reset Database

**Files:**
- Remote modify: `/etc/nginx/sites-available/coke`
- Remote build/run: `/home/whoami/coke-clean/web`
- Remote database: `coke-clean-postgres-1` database `coke`

- [x] **Step 1: Start clean web profile**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml --profile web up -d --build coke-web'
```

Expected: `coke-clean-coke-web-1` is running on `127.0.0.1:4042`, or build failure is captured and API-only status is reported.

- [x] **Step 2: Back up nginx site**

Run:

```bash
ssh gcp-coke 'sudo cp /etc/nginx/sites-available/coke /etc/nginx/sites-available/coke.before-clean-cutover-$(date -u +%Y%m%dT%H%M%SZ)'
```

Expected: backup file exists.

- [x] **Step 3: Route product traffic to clean API and clean web**

Update nginx so `/` proxies to `127.0.0.1:4042`, `/api/` proxies to `127.0.0.1:8000`, provider webhooks proxy to `127.0.0.1:8000`, dead old `/bridge/`, `/user/`, `/bind/`, `/gateway/`, `/auth`, `/health`, old `/api/ -> 4041`, and old `/ -> 4040` routes are removed, and `/evolution-api/ -> 8081` stays.

- [x] **Step 4: Validate and reload nginx**

Run:

```bash
ssh gcp-coke 'sudo nginx -t && sudo systemctl reload nginx'
```

Expected: syntax ok and reload succeeds.

- [x] **Step 5: Reset clean database and rerun migrations**

Run:

```bash
ssh gcp-coke 'docker exec coke-clean-postgres-1 psql -U coke -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''coke'\'' AND pid <> pg_backend_pid();" -c "DROP DATABASE IF EXISTS coke;" -c "CREATE DATABASE coke OWNER coke;" && cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate'
```

Expected: migrated clean database, 28 or more tables, zero product rows.

- [x] **Step 6: Restart clean runtime after DB reset**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml --profile web up -d coke-api coke-worker coke-scheduler coke-outbox-relay coke-web'
```

Expected: API, worker, scheduler, outbox relay, and web are running.

- [x] **Step 7: Health-check clean production**

Run:

```bash
ssh gcp-coke 'curl -fsS http://127.0.0.1:8000/healthz && curl -k -I https://coke.keep4oforever.com/'
```

Expected: API health is 200 and public site responds from clean web, or web deferral is recorded.

### Task 4: Personal-WeChat Web-First E2E

**Files:**
- Read: `coke/api/channel_routes.py`
- Read: `coke/api/provider_webhooks.py`
- Remote database: `coke-clean-postgres-1` database `coke`

- [x] **Step 1: Create or authenticate a web-first account**

Use clean `/api/auth/*` if the routes are available. If auth APIs are not exposed for this production slice, create the minimum web-first account rows through the clean schema and report that this is a direct DB setup path, not a public auth-route pass.

- [x] **Step 2: Connect a `wechat_personal` channel**

Use `/api/channels` with an existing web-first `channel_identity_id`, then `/api/channels/<id>/connect`. If the API cannot bind the identity without a real connector or auth path, report the exact failed call and reason; do not fake a live connector.

- [x] **Step 3: Simulate inbound webhook**

POST to `/webhooks/wechat/personal` with:

```json
{
  "wxid": "<bound-wechat-identity>",
  "message_id": "<unique-message-id>",
  "text": "提醒我明天早上9点跑步"
}
```

Expected: accepted as the existing web-first account, not auto-provisioned.

- [x] **Step 4: Verify database rows**

Query `account`, `channel_identity`, `channel`, `delivery_route`, `conversation`, `message`, `turn`, `reminder`, `delivery_attempt`, and `outbox` as applicable. Paste rows that prove account association, inbound message recording, reminder creation if the worker path completes, and outbound delivery status.

- [x] **Step 5: Classify outbound delivery**

If `COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL` remains unset, record outbound delivery as blocked by missing connector configuration rather than delivered.

### Task 5: Local Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md`

- [x] **Step 1: Run local unit verification**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all tests pass.

- [x] **Step 2: Mark this plan complete**

Set `Plan Status` to `complete` only after remote cutover checks and local pytest pass, then check off completed steps.

- [x] **Step 3: Commit the plan and any code fixes**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md
git commit -m "ops: record clean production cutover closeout"
```

### Task 6: Empty Model Output Root Cause And Red Tests

**Files:**
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Read: production `ai.agno_sessions` / turn/output/delivery rows on `gcp-coke`

- [x] **Step 1: Inspect failing Agno session shape**

Query the failed join turn by recent `invalid_output_protocol` and inspect
the corresponding Agno session messages. Capture whether the model returned
tool calls followed by empty final content, reasoning-only content, or a token
cutoff. Do not change code before this evidence is known.

Evidence captured from production `ai.agno_sessions` session
`bdefeb3826704fd598bb0ffbb931aadf`: message 2 was an assistant tool-call
carrier with empty content and one `social_scheduling_tool` call; message 3 was
the tool result `ok=True` with `friendship_id=cd671792c1264d9ead43ac4221ef2bf6`;
message 4 was final assistant content `好友添加成功啦！...`, but it was plain
text instead of the required JSON protocol object. The turn failed because the
final model output was non-protocol text, not because the tool failed or because
of token cutoff.

- [x] **Step 2: Add a failing prompt-contract test**

Add a unit test that asserts the Interaction Agent instructions require a final
structured reply after tool work:

```python
def test_instructions_require_final_protocol_reply_after_tool_work():
    factory = FakeAgentFactory(FakeAgentInstance(content={"type": "reply", "segments": ["ok"]}))
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True))

    instructions = "\n".join(factory.instances[0].instructions)
    assert "After any tool call" in instructions
    assert '{"type":"reply","segments":["..."]}' in instructions
    assert "never end with empty assistant content" in instructions
```

- [x] **Step 3: Add failing bounded-retry tests**

Add Turn runner tests that prove a blank first model answer is retried once and
still fails closed if the retry is blank:

```python
def test_blank_agent_output_retries_same_turn_once_then_uses_valid_retry(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(""),
        AgentResult.completed({"type": "reply", "segments": ["好友已经添加好了。"]}),
    ]

    result = harness["runner"].run_inbound_turn(_inbound_trigger())

    assert result.disposition == "replied"
    assert harness["agent"].invocations == 2
    assert harness["delivery"].delivered_texts[-1].text == "好友已经添加好了。"


def test_blank_agent_output_retry_still_blank_fails_closed(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(""),
        AgentResult.completed("   "),
    ]

    result = harness["runner"].run_inbound_turn(_inbound_trigger())

    assert result.disposition == "failed"
    assert result.reason_code == "invalid_output_protocol"
    assert harness["agent"].invocations == 2
    assert harness["delivery"].delivered_texts == []
```

- [x] **Step 4: Run red tests**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py -v
```

Expected: the new instruction assertion and retry assertions fail before the
implementation.

Red evidence: focused pytest collected 27 tests, with three expected failures:
missing "After any tool call" instruction and `AgentResult` lacking the new
`blank_output` field needed for a blank-only retry distinction.

### Task 7: Prompt Contract And One-Retry Runtime Fix

**Files:**
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `coke/turn/output_protocol.py` if a narrow blank-output classifier is needed
- Modify: `coke/turn/runner.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`

- [x] **Step 1: Strengthen the Interaction Agent instructions**

Add an explicit instruction that after any tool call the agent must finish with
one structured protocol object grounded in the real tool result:

```text
After any tool call, you MUST emit a final user-facing protocol object.
If the tool succeeded, return {"type":"reply","segments":["..."]} confirming
the real result in the user's language. If no user-visible message is truly
warranted, return {"type":"no_reply","reason":"intentional_no_reply"}.
Never end with empty assistant content, reasoning-only content, or only tool
calls.
```

- [x] **Step 2: Implement a single blank-output retry**

In `TurnRunner`, when the first `AgentResult.completed(...)` validates as
`invalid_output_protocol` because the raw model output is blank/whitespace,
invoke the same `InteractionAgent` request exactly one more time. Validate the
second answer normally. Do not retry malformed nonblank JSON, do not rewrite
bad output, do not synthesize fallback prose, and do not loop.

- [x] **Step 3: Run focused green tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py -v
```

Expected: the new prompt and retry tests pass.

Green evidence: focused pytest passed `27 passed in 1.99s`.

- [x] **Step 4: Run full local unit and integration verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: both suites pass.

Verification evidence: unit suite passed `419 passed in 10.31s`;
integration suite passed `9 passed, 33 skipped in 3.97s` with repository
contract skips due to `COKE_TEST_DATABASE_URL` not being set.

- [x] **Step 5: Commit code and plan changes**

Run:

```bash
git add coke/llm/agno_interaction_agent.py coke/turn/runner.py coke/turn/output_protocol.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md
git commit -m "fix: retry blank interaction agent output once"
```

- [x] **Step 6: Expand protocol retry after live regression evidence**

The first deployed fix did not handle the real regression. The formal lizihao
join rerun `formal-e2e-20260530T190351Z-p3-lizihao-join` failed with
`invalid_output_protocol`: Agno run 4 called `social_scheduling_tool`, received
`ok=true` / `status=already_active`, then returned non-protocol plain text
(`你们已经是好友了...`). This was not blank output, so the blank-only retry did
not fire.

Add a bounded same-turn protocol retry for any invalid first answer. The retry
does not synthesize or rewrite visible text; it re-invokes the Interaction Agent
once with protocol retry context, and the normal output protocol validator still
fails closed if the second answer is invalid.

Red evidence:

```text
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py -v
4 failed, 24 passed in 2.66s
```

Green evidence:

```text
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py -v
28 passed in 2.02s
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
420 passed in 10.16s
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
9 passed, 33 skipped in 3.84s
```

### Task 8: Redeploy Clean Runtime

**Files:**
- Remote deploy target: `gcp-coke:/home/whoami/coke-clean`
- Read: `docs/deploy.md`
- Read: `docs/clawscale_bridge.md`

- [x] **Step 1: Deploy non-disruptively**

Deploy the current branch to `coke-clean` without stopping Evolution, the web
service, or the personal-WeChat connector. Preserve `/home/whoami/coke-clean/.env`
and provider configuration.

Deploy evidence: `scripts/deploy-compose-to-gcp.sh` stopped during rsync before
service restart because root-owned remote `web/.next` artifacts rejected
attribute/file updates. I reran the same allowlisted rsync with `--exclude=.next`
and then ran the script's compose/migration/health sequence manually. Clean API
health returned `{"ok":true}`; `coke-web`, Postgres, Redis, Evolution, and the
personal-WeChat connector remained running.

- [x] **Step 2: Confirm health and connector state**

Run remote health checks and confirm `connected_session_count=2` from the
personal-WeChat connector. Record the exact command outputs used as evidence.

Health evidence:

```text
curl http://127.0.0.1:8000/healthz -> {"ok":true}
curl http://127.0.0.1:8095/healthz -> {"connected":true,"connected_session_count":2,"ok":true,"status":"connected"}
```

### Task 9: Formal Real Personal-WeChat E2E

**Files:**
- Remote database: `coke-clean-postgres-1` database `coke`
- Remote API: `/webhooks/wechat/personal`

- [x] **Step 1: State real-message safety**

Before running, state that this smoke can send real WeChat messages to the two
connected real accounts.

- [x] **Step 2: Phase 1 personal reminder**

Post connector-shaped inbound for olivers wxid
`o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat` with text
`提醒我明天早上9点跑步`. Verify one timed reminder row and the reply
`delivery_attempt.status = 'sent'`.

Evidence: `formal-e2e-20260530T190351Z-p1-olivers-reminder` was accepted,
turn `d98a122f-21b4-4961-8842-9736f2e08d22` replied, and delivery attempt
`30e19af7-2517-4ddc-acbb-4706d9647745` was `sent` with provider message id
`coke-1780167981549-799493d48fef`. The active timed reminder row was the
existing duplicate-prevention row `9da54785-6738-4cb8-8c89-da421a08429a`
(`content='跑步'`, `next_fire_at='2026-05-31 01:00:00+00'`,
`captured_timezone='Asia/Shanghai'`), and the model correctly replied that it
would not create a duplicate.

- [x] **Step 3: Phase 2 friend link**

Post olivers friend-link request. Verify one `friend_link` row, extract the
code from the model reply, and verify the reply `delivery_attempt.status =
'sent'`.

Evidence: `formal-e2e-20260530T190351Z-p2-olivers-friend-link` replied with
`https://coke.example/friends/friend_link_tJm4MJt4NQ3Vdaq5ntJtmHG_-K9Qhsif`.
The active `friend_link` row is `c20d5272-c9f4-4bc5-ab35-2790317a07f4`, and
delivery attempt `26aa65d0-e7a8-4575-bd85-1e34f200c593` was `sent` with
provider message id `coke-1780168181334-087e5a5da377`.

- [x] **Step 4: Phase 3 friend-link join**

Post lizihao wxid `o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat` with the code.
Verify `friendship.lifecycle = 'active'` and the lizihao confirmation reply
`delivery_attempt.status = 'sent'`. This is the regression phase.

Evidence: the first deployed rerun
`formal-e2e-20260530T190351Z-p3-lizihao-join` still failed because GLM-5.1
called `social_scheduling_tool`, received `ok=true` / `status=already_active`,
then returned non-protocol plain text. After broadening the bounded protocol
retry and redeploying, `formal-e2e-20260530T190351Z-p3b-lizihao-join` replied
successfully. Turn `3a4f0115-514a-49ab-9dec-22e08e876918` was
`replied/reply_ready`, active friendship
`cd671792-c126-4d9e-ad43-ac4221ef2bf6` linked lizihao
`635d3bdc-1b02-4a08-acf4-9940b91a9de5` and olivers
`ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`, and delivery attempt
`fa9fed46-d33d-4b2b-9119-cafbab5ec2c7` was `sent` with provider message id
`coke-1780168695568-09da018a2198`.

- [x] **Step 5: Phase 4 shared reminder**

Post olivers shared-reminder creation involving lizihao. Verify
`shared_reminder.status = 'active'`, per-participant `reminder_projection`
rows, `notification_fact` rows, and sent delivery attempts for both users'
visible messages.

Evidence: `formal-e2e-20260530T190351Z-p4-olivers-shared-reminder` replied
successfully. Shared reminder `13195519-06b3-446c-b46c-2b4edba9d00f` is
`active` with title `一起喝水`, local trigger `2026-05-31 15:00:00`, timezone
`Asia/Shanghai`, and duration `15`. Projection
`b2c009e5-9323-4855-ac07-492d16aa94d8` maps olivers to reminder
`2dc06f97-ded4-474f-a69f-1c9a12085461`; projection
`2eedabb2-d558-4902-a0b5-c9e350af5ae5` maps lizihao to reminder
`586bcf36-034c-4e96-a7dc-75ecf47f6714`. Notification fact
`f908041f-fde8-4d19-9324-bfb8ae5fa4dd` was created with idempotency key
`shared_reminder:1319551906b3446cb46c2b4edba9d00f:created`. Creator delivery
attempt `b423fee2-0d16-4bf2-9ac4-bc5b1076d5ae` was `sent` with provider
message id `coke-1780168779167-ad8088085732`; recipient notification delivery
attempt `ec9a99b0-0e16-41ac-b188-5c991650d81c` was `sent` with provider
message id `coke-1780168788878-604cc7bcd9d6`.

- [x] **Step 6: Phase 5 reminder fire**

Set a test reminder due, let the scheduler fire, and verify `reminder_fire`,
render-turn message, and delivery attempt status. If iLink rejects unsolicited
sends, record the exact provider constraint instead of counting it as sent.

Evidence: I set olivers shared-projection reminder
`2dc06f97-ded4-474f-a69f-1c9a12085461` due by updating `next_fire_at` to
`2026-05-30 19:21:37.032838+00`. The running scheduler claimed reminder fire
`3e0c8d05-2bd3-461a-b726-17ec1ae13568` at due time
`2026-05-30 19:21:37.032838+00`. Reminder-fire turn
`59144e3f-ed7a-46de-aa7c-72a760849185` completed
`replied/reply_ready` for trigger
`reminder_fire:ae02ff016fcd4d39a189e51c8c8a31e6:2026-05-30T19:21:37.032838+00:00`.
Outbound message `c32cdccc-09e0-4609-9e74-8df9390d4b26` was rendered, and
delivery attempt `d9c2ae13-542f-4ef8-aa34-688771c86540` was `sent` with
provider message id `coke-1780169039211-86cd34627138`.

- [x] **Step 7: Mark plan complete**

Only after the focused tests, full verification, deploy health, connector
count, and all feasible E2E phases have evidence, set:

```markdown
**Plan Status:** complete
```

### Task 10: Comprehensive Live Personal-WeChat Happy-Path Sweep

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md`
- Modify if bugs are blocking: focused `coke/` modules owned by the failing clean-domain path
- Test if bugs are blocking: focused `tests/unit/coke/**` regression tests
- Remote evidence: `gcp-coke` clean Postgres `coke`, clean API logs, clean personal-WeChat connector health

- [x] **Step 1: Verify live target health and route bindings**

Run:

```bash
ssh gcp-coke 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
ssh gcp-coke 'curl -fsS http://127.0.0.1:8000/healthz; echo; curl -fsS http://127.0.0.1:8095/healthz; echo'
ssh gcp-coke "docker exec -i coke-clean-postgres-1 psql -U coke -d coke -v ON_ERROR_STOP=1 -c \"select a.id as account_id, a.default_timezone, ci.provider_subject, c.connection_state, dr.lifecycle, dr.provider_address from account a join channel_identity ci on ci.account_id=a.id join channel c on c.account_id=a.id and c.channel_identity_id=ci.id join delivery_route dr on dr.account_id=a.id where a.id in ('ae02ff016fcd4d39a189e51c8c8a31e6','635d3bdc1b024a08acf49940b91a9de5') order by a.id;\""
```

Expected: clean API healthy, connector `connected_session_count=2`, both real
accounts have connected personal-WeChat routes.

- [x] **Step 2: Build the case ledger from repository phrasings**

Use the issue records named in the user request and preserve real Chinese
phrasing where present:

```text
Daily: 你好 / 不用回复
Timed reminder: 提醒我明天早上9点跑步
Fire regression: 2分钟后提醒我喝水-<marker>。
List: 列一下我的提醒。
Recurring: create/update/cancel wording from the recurring regression note
Shared create/status/cancel: wording from the shared real-user matrix
Coach boundary: 帮我约彭教练...
Ambiguous update: 改一下提醒时间
```

Record one unique marker per case and never reuse a marker after a partial run.

- [ ] **Step 3: Run cases A-I one at a time through `/webhooks/wechat/personal`**

For each case, post connector-shaped inbound from the correct wxid with a unique
`message_id`, wait up to 180 seconds for worker/scheduler output, then query
the clean schema. A case can pass only when the domain rows match the expected
product state and each required visible reply has a real
`delivery_attempt.status='sent'`; intentional no-reply passes only with
`output_disposition.disposition='no_reply'` and no outbound delivery.

- [x] **Step 4: Diagnose every failure before fixing**

For a failed case, gather the failing `message`, `turn`, `output_disposition`,
domain rows, `outbox`, `delivery_attempt`, and clean API/worker logs first.
Classify the failure as product/runtime bug, test/harness bug, environment
instability, or plan gap before editing.

- [x] **Step 5: Use TDD for any blocking bug fix**

Before changing production code, write the smallest focused failing unit test
under `tests/unit/coke/**`, run it with:

```bash
/data/projects/coke/.venv/bin/python -m pytest <focused-test> -v
```

Expected: the new test fails for the observed root cause. Then implement the
smallest code fix, rerun the focused test, and run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

- [x] **Step 6: Redeploy only after local verification passes**

Run the repository deploy path preserving `coke-clean/.env` and the connector,
then verify:

```bash
ssh gcp-coke 'curl -fsS http://127.0.0.1:8000/healthz; echo; curl -fsS http://127.0.0.1:8095/healthz; echo'
```

Expected: clean API healthy and connector still reports
`connected_session_count=2`.

2026-05-31 result: local focused tests failed first for the observed
output-protocol and reminder-operation failures, then passed after the fixes.
The full local unit suite passed with
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`
reporting `426 passed in 10.13s`. A backend-only clean redeploy preserved the
connector and clean environment after the full deploy script hit a remote
web `.next` permission problem. Post-deploy health returned clean API
`{"ok":true}` and connector
`{"connected":true,"connected_session_count":2,"ok":true,"status":"connected"}`.

- [ ] **Step 7: Rerun the failed blocking case, then continue coverage**

Do not count a fix as verified until the same live case that exposed it passes
against DB and delivery-attempt evidence. Non-blocking bugs stay recorded in
the final matrix while the sweep continues.

2026-05-31 result: the original B1 timed-reminder failure passed after the
output-protocol fix. The B4/B5 durable-state failures were corrected by the
reminder-operation fix, but olivers delivery attempts then failed with
`ilink_send_failed_ret_-2`, including when using the persisted connector
context token. 李梓豪 delivery remained usable for several additional cases
and produced `sent` evidence for greeting, cancel/delete, duplicate
prevention, and ambiguous-reference clarification before another live
delivery attempt failed with `ilink_send_failed_ret_-2` on the coach-boundary
case. The remaining A-I matrix is blocked by strict delivery-verdict
requirements until the live personal-WeChat connector/session issue is
refreshed or diagnosed outside the clean product code path.

- [x] **Step 8: Final verification, plan status, and commit**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

If all required live cases are covered and verification passes, set
`Plan Status` to `complete`, commit the plan plus any code/tests, and report
`git log --oneline main..HEAD`.

2026-05-31 result: verification passed, but the plan status remains `blocked`
instead of `complete` because the strict A-I live matrix was not fully covered.
Commands run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

`review-trigger` reported `human_review_required: no`; its remaining
`evidence_gap` risk is expected because this sweep recorded live evidence in
the plan/final report rather than under `artifacts/evidence/**`.

### Task 11: iLink `ret=-2` Hardening And Product-Logic Sweep Completion

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-e2e-closeout.md`
- Modify: `provider_edges/wechat_personal_connector/app.py`
- Modify if root cause is confirmed in clean delivery: `coke/composition.py`
- Modify if request context must be threaded: `coke/turn/runner.py`
- Test: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py`
- Test if clean delivery changes: `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py`
- Test if turn request context changes: `tests/unit/coke/turn/test_turn_runner.py`

- [ ] **Step 1: Capture the real iLink `ret=-2` response body**

Inspect connector logs and, if needed, add connector-side logging of the full
iLink `sendmessage` failure response. Evidence must include the actual response
body, not only `ilink_send_failed_ret_-2`.

- [ ] **Step 2: Confirm protocol root cause before fixing**

Use the raw iLink protocol documents and live evidence to classify the failure:
stale/wrong `context_token`, single-use/short-lived token behavior, unsupported
unsolicited sends, session expiry, or rate limiting. Do not implement product
logic changes until this classification is recorded.

- [ ] **Step 3: Write failing tests for the confirmed delivery hardening**

At minimum cover connector logging/response preservation for iLink business
failures. If the clean app is using the wrong context token, add a failing test
showing delivery uses the triggering inbound token, not the conversation's latest
token.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py -v
```

Expected before implementation: the new tests fail for the observed root cause.

- [ ] **Step 4: Implement the smallest delivery fix**

Preserve clean architecture boundaries: connector logs and maps iLink failures,
ChannelReachability records real sent/failed attempts, and ConversationRuntime
supplies only the relevant inbound context. Add bounded retry/backoff only for
transient `ret=-2`; do not mark a failed send as success.

- [ ] **Step 5: Verify locally and deploy non-disruptively**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
git diff --check
```

Then redeploy connector and clean backend without disturbing Postgres state or
the two live WeChat sessions. Verify `/healthz` for API and connector and that
`connected_session_count=2`.

- [ ] **Step 6: Resume the remaining A-I live sweep product-logic first**

Run the remaining B-I cases one at a time using the real olivers/李梓豪 accounts
and repository phrasings. For each case, record domain rows and turn behavior as
primary evidence, with delivery attempts as secondary evidence. Transient
`ret=-2` after retry is noted but does not block product-bug discovery.

- [ ] **Step 7: Fix product blockers with TDD and continue**

For each hard product failure, gather DB/log evidence, write the focused failing
test, run it red, implement the smallest fix, run the focused test green, run
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`, redeploy,
rerun the live case, and continue.

- [ ] **Step 8: Close out with verification and commit**

After all feasible cases have evidence, run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Set `Plan Status` to `complete` only if the full requested verification and live
sweep pass. Otherwise leave the precise blocker and uncovered cases in this
plan and final report.
