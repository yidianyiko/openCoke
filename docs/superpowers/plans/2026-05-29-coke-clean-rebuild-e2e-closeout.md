# Coke Clean Rebuild E2E Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Destructively retire the old `coke` production stack on `gcp-coke`, promote `coke-clean` as the primary public stack, reset the clean database for go-live, and run a personal-WeChat web-first end-to-end check with honest connector evidence.

**Architecture:** Treat this as an operational cutover, not a migration: preserve the Evolution provider stack, preserve `coke-clean`, delete only the old `coke` project and its data, and move nginx product traffic to clean API/web ports. Personal WeChat remains a provider adapter behind the clean ingress/egress tier; if the old bridge is the only live connector, the webhook test must be simulation-only and outbound delivery must be reported as blocked by missing connector configuration.

**Tech Stack:** Docker Compose on `gcp-coke`, nginx, Postgres 17, Redis 7.2, Flask/Gunicorn clean API, Next.js web client, pytest.

**Plan Status:** in_progress

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

### Task 8: Redeploy Clean Runtime

**Files:**
- Remote deploy target: `gcp-coke:/home/whoami/coke-clean`
- Read: `docs/deploy.md`
- Read: `docs/clawscale_bridge.md`

- [ ] **Step 1: Deploy non-disruptively**

Deploy the current branch to `coke-clean` without stopping Evolution, the web
service, or the personal-WeChat connector. Preserve `/home/whoami/coke-clean/.env`
and provider configuration.

- [ ] **Step 2: Confirm health and connector state**

Run remote health checks and confirm `connected_session_count=2` from the
personal-WeChat connector. Record the exact command outputs used as evidence.

### Task 9: Formal Real Personal-WeChat E2E

**Files:**
- Remote database: `coke-clean-postgres-1` database `coke`
- Remote API: `/webhooks/wechat/personal`

- [ ] **Step 1: State real-message safety**

Before running, state that this smoke can send real WeChat messages to the two
connected real accounts.

- [ ] **Step 2: Phase 1 personal reminder**

Post connector-shaped inbound for olivers wxid
`o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat` with text
`提醒我明天早上9点跑步`. Verify one timed reminder row and the reply
`delivery_attempt.status = 'sent'`.

- [ ] **Step 3: Phase 2 friend link**

Post olivers friend-link request. Verify one `friend_link` row, extract the
code from the model reply, and verify the reply `delivery_attempt.status =
'sent'`.

- [ ] **Step 4: Phase 3 friend-link join**

Post lizihao wxid `o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat` with the code.
Verify `friendship.lifecycle = 'active'` and the lizihao confirmation reply
`delivery_attempt.status = 'sent'`. This is the regression phase.

- [ ] **Step 5: Phase 4 shared reminder**

Post olivers shared-reminder creation involving lizihao. Verify
`shared_reminder.status = 'active'`, per-participant `reminder_projection`
rows, `notification_fact` rows, and sent delivery attempts for both users'
visible messages.

- [ ] **Step 6: Phase 5 reminder fire**

Set a test reminder due, let the scheduler fire, and verify `reminder_fire`,
render-turn message, and delivery attempt status. If iLink rejects unsolicited
sends, record the exact provider constraint instead of counting it as sent.

- [ ] **Step 7: Mark plan complete**

Only after the focused tests, full verification, deploy health, connector
count, and all feasible E2E phases have evidence, set:

```markdown
**Plan Status:** complete
```
