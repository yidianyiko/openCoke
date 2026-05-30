# Personal WeChat Outbound Delivery And Session Durability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** blocked-live-formal

**Goal:** Make personal-WeChat replies use the correct iLink `context_token`, keep connector sessions durable across restarts, and prove delivery on the two connected real accounts.

**Architecture:** Coke remains the product and delivery-attempt authority; the `wechat_personal` provider adapter maps Coke delivery requests to the connector contract, and the connector owns only iLink session state, polling, token/context handling, and raw protocol calls. The connector persists per-account bot token, cursor, and per-contact context tokens in its JSON state file; Coke stores inbound `context_token` in `message.payload` and records every send result in `delivery_attempt`.

**Tech Stack:** Python Flask/httpx connector, SQLAlchemy metadata-defined clean schema, existing in-memory service tests, pytest, Docker Compose on `gcp-coke`, and live Postgres/connector evidence for final smoke verification.

---

## Protocol Facts Used

- `sendmessage` must use `AuthorizationType: ilink_bot_token`, `Authorization: Bearer <bot_token>`, random base64 decimal `X-WECHAT-UIN`, `base_info.channel_version`, `message_type: 2`, `message_state: 2`, unique `client_id`, target `to_user_id`, and the inbound message's exact `context_token`.
- `getupdates` returns `msgs`, an opaque `get_updates_buf` cursor, and inbound message `context_token`; cursor and context tokens must be persisted per account/session.
- `ret != 0`, `errcode != 0`, HTTP non-2xx, and `errcode/ret = -14` are real iLink failures even when transport succeeds.
- Public implementations do not expose an independent proactive-send API. Proactive or reminder-fire sends can only use a latest valid context token for the target conversation; if iLink rejects it, Coke must record failed delivery instead of faking success.

## Files

- Modify: `provider_edges/wechat_personal_connector/app.py` for iLink response parsing, session resume, per-account polling durability, retry/backoff, and diagnostics.
- Modify: `provider_edges/wechat_personal_connector/docker-compose.yml` so the connector can join the clean Coke Docker network and post webhooks to the `coke-api` service.
- Modify: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py` for failing connector tests covering session resume, context-token send, iLink business failure mapping, and robust polling.
- Modify if Coke-side context selection is proven stale: `coke/composition.py`, `coke/domains/conversation_runtime/repository.py`, `coke/domains/conversation_runtime/service.py`, and targeted tests under `tests/unit/coke/conversation_runtime/` or `tests/unit/coke/channel_reachability/`.
- Modify if provider error mapping loses body details: `coke/providers/base.py`, `coke/providers/wechat_personal.py`, and `tests/unit/coke/channel_reachability/test_provider_adapters.py`.
- Update: this plan file as steps complete.

## Task 1: Root Cause And Live Evidence

- [x] **Step 1: Inspect current git state**

Run:

```bash
git status --short --branch
```

Expected: the current worktree is on `main`; any pre-existing unrelated changes are left untouched.

Observed: branch `main` with only this task's edited files.

- [x] **Step 2: Inspect live clean services and connector state**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose ps'
ssh gcp-coke 'cd /home/whoami/wechat-personal-connector && docker compose ps && python3 - <<'"'"'PY'"'"'
import json
from pathlib import Path
path = Path("/data/wechat_personal_state.json")
data = json.loads(path.read_text()) if path.exists() else {}
print(json.dumps({
    "status": data.get("status"),
    "session_count": len(data.get("sessions", {})) if isinstance(data.get("sessions"), dict) else 0,
    "sessions": {
        k: {
            "account_id": v.get("account_id"),
            "status": v.get("status"),
            "ilink_user_id": v.get("ilink_user_id"),
            "has_token": bool(v.get("token")),
            "cursor_len": len(str(v.get("cursor") or "")),
            "context_token_keys": sorted((v.get("context_tokens") or {}).keys()),
            "last_poll_error": v.get("last_poll_error"),
        }
        for k, v in (data.get("sessions") or {}).items()
        if isinstance(v, dict)
    },
    "last_poll_error": data.get("last_poll_error"),
}, ensure_ascii=False, indent=2))
PY'
```

Expected: determine whether both real accounts have connected sessions with tokens and whether prior errors are per-session or global.

Observed: clean Coke services and the standalone connector were running. Connector state had connected sessions for the real olivers and lizihao account IDs with iLink wxids and bot tokens, but no cached context tokens. The connector container could not reach the clean API through `host.docker.internal:8000`, matching the persisted `ConnectError([Errno 111] Connection refused)` poll failure.

- [x] **Step 3: Reproduce or inspect the 409 with response body**

Run a connector `/send` probe for a connected account using the latest persisted context token, then inspect logs without printing secrets:

```bash
ssh gcp-coke 'cd /home/whoami/wechat-personal-connector && docker compose logs --since=30m wechat-personal-connector | tail -200'
```

Expected: record whether the failure is connector `wechat_not_connected`, iLink HTTP 409, iLink business body such as `ret:-2`, or expired session `ret:-14`.

Observed: the recent `provider_http_409` row in clean Postgres was for an old fake removed route, not the two current connected real routes. The actionable live failure was the connector webhook path: inbound getupdates could not post into clean Coke, so Coke had no durable real context tokens to echo on replies.

## Task 2: Connector Tests First

- [x] **Step 4: Add failing tests for session resume and poll robustness**

Add tests to `tests/unit/coke/provider_edges/test_wechat_personal_connector.py`:

```python
def test_create_app_autostarts_poll_for_persisted_connected_sessions(monkeypatch, tmp_path):
    monkeypatch.setenv("WECHAT_CONNECTOR_AUTOSTART_POLL", "1")
    state = ConnectorState(tmp_path / "state.json")
    state.update({"sessions": {"session-1": {"account_id": "acct_1", "status": "connected", "base_url": "https://bot.example", "token": "bot-token", "cursor": "", "context_tokens": {}}}})
    ilink = FakeIlinkClient(updates={"get_updates_buf": "", "msgs": []})
    create_app(ConnectorConfig(webhook_url="http://coke-api/webhooks/wechat/personal", poll_interval_seconds=0.01), state=state, ilink_client=ilink, webhook_client=FakeWebhookClient())
    deadline = time.monotonic() + 1.0
    while not ilink.update_calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ilink.update_calls
```

```python
def test_poll_once_records_retryable_error_per_session_without_killing_other_sessions(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    state.update({"sessions": {"bad": {"account_id": "acct_bad", "status": "connected", "base_url": "https://bot.example", "token": "bad-token", "cursor": "", "context_tokens": {}}, "good": {"account_id": "acct_good", "status": "connected", "base_url": "https://bot.example", "token": "good-token", "cursor": "", "context_tokens": {}}}})
    ilink = FakeIlinkClient()
    ilink.fail_tokens = {"bad-token": RuntimeError("temporary network")}
    delivered = poll_once(ConnectorConfig(webhook_url="http://coke-api/webhooks/wechat/personal"), state=state, ilink_client=ilink, webhook_client=FakeWebhookClient())
    snapshot = state.snapshot()["sessions"]
    assert delivered == 0
    assert "temporary network" in snapshot["bad"]["last_poll_error"]
    assert snapshot["good"].get("last_poll_error") in {None, ""}
```

- [x] **Step 5: Add failing tests for iLink send body failure mapping**

Add tests showing connector `/send` does not report success for iLink business failures:

```python
def test_send_endpoint_maps_ilink_business_failure_to_clear_502(state):
    ilink = FakeIlinkClient()
    ilink.send_failure = {"ret": -2, "errmsg": "invalid context_token"}
    app = create_app(ConnectorConfig(api_key="connector-key"), state=state, ilink_client=ilink, webhook_client=FakeWebhookClient())
    response = app.test_client().post("/send", json={"account_id": "acct_1", "to": "wxid_alice", "context_token": "ctx-bad", "text": "hello"}, headers={"Authorization": "Bearer connector-key"})
    assert response.status_code == 502
    assert response.get_json()["error"] == "ilink_send_failed"
    assert response.get_json()["ilink"] == {"ret": -2, "errmsg": "invalid context_token"}
```

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
```

Expected: the new tests fail before implementation.

Observed red: connector tests failed because one session error aborted polling, retry backoff was absent, stale top-level health status hid connected sessions, the connector compose did not join the clean runtime network, connector `/send` returned success for an iLink business failure body, and Coke provider mapping collapsed structured connector failures to `provider_http_502`.

## Task 3: Implement Minimal Connector Fixes

- [x] **Step 6: Implement iLink response validation**

Update `IlinkClient.send_text()` and `IlinkClient.get_updates()` so HTTP non-2xx, JSON `ret != 0`, JSON `errcode != 0`, and `-14` are surfaced as structured connector failures. `/send` returns a non-2xx connector response with an error body, and Coke records it as failed.

- [x] **Step 7: Implement per-session poll error handling and resume**

Update polling so one session's `ConnectError`, `ReadTimeout`, or iLink business failure is stored on that session and does not stop other sessions. On app startup with `WECHAT_CONNECTOR_AUTOSTART_POLL=1`, resume polling for every persisted `status=connected` session.

- [x] **Step 8: Preserve context-token cache by account and wxid**

Keep `context_tokens` keyed by sender `wxid` within the session. On inbound, persist each token before or with cursor advancement. On `/send`, require the caller-supplied token and fail clearly when the connected account session is missing or expired.

- [x] **Step 9: Run focused tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
```

Expected: all connector tests pass.

Observed: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v` passed with `14 passed`.

## Task 4: Coke-Side Context Verification

- [x] **Step 10: Verify Coke stores latest inbound context token**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_latest_context_token_reads_newest_inbound_message_payload tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py::test_outbound_delivery_reads_latest_inbound_context_token_for_wechat_personal -v
```

Expected: both tests pass. If either fails, fix Coke-side context storage or selection with failing tests first.

Observed: both targeted tests passed; Coke already stores and selects the latest inbound `context_token` for personal-WeChat outbound delivery.

- [x] **Step 11: Add a failing Coke-side test only if live evidence proves stale context selection**

If the 409 is caused by Coke choosing the wrong inbound token, add a failing test that selects the context token for the causal inbound turn instead of an unrelated newer message. Then implement the smallest Coke-side change.

Observed: live and unit evidence did not show stale Coke-side context selection, so no Coke composition/repository change was made.

## Task 5: Deploy And Live Delivery Proof

- [x] **Step 12: Run focused and full unit verification**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py -v
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: focused tests and full unit suite pass.

Observed:

- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_latest_context_token_reads_newest_inbound_message_payload tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py::test_outbound_delivery_reads_latest_inbound_context_token_for_wechat_personal -v` passed with `2 passed`.
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py tests/unit/coke/channel_reachability/test_provider_adapters.py -v` passed with `58 passed`.
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed with `415 passed`.

- [x] **Step 13: Deploy connector and clean Coke non-disruptively**

Preserve `/home/whoami/coke-clean/.env`, keep `evolution-*` and web up, rebuild/restart only touched clean backend/connector services, and confirm health:

```bash
ssh gcp-coke 'cd /home/whoami/wechat-personal-connector && docker compose up -d --build'
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose up -d coke-api coke-worker coke-scheduler coke-outbox'
```

Observed: rsynced only touched connector/backend files, preserved both `.env` files, updated connector `WECHAT_CONNECTOR_WEBHOOK_URL` to `http://coke-api:8000/webhooks/wechat/personal`, added `WECHAT_CONNECTOR_COKE_NETWORK=coke-clean_default`, recreated the existing `wechat-personal-connector` compose project with `-p wechat-personal-connector`, and rebuilt/recreated clean `coke-api`, `coke-worker`, `coke-scheduler`, and `coke-outbox-relay`. `coke-web`, Postgres, Redis, and Evolution stayed running. Clean API health returned `{"ok":true}`.

- [x] **Step 14: Confirm whether re-scan is required**

Validate persisted bot tokens with `getupdates` or `/poll/once`. If iLink returns `-14` for an account, mark that account as requiring re-scan and stop live outbound proof for that account without faking delivery.

Observed: connector health returned `connected=true`, `connected_session_count=2`; `/poll/once` returned HTTP 202 `{"delivered":0}` and left both real connected sessions active with tokens. No `ret:-14` expired-token response was observed, so no re-scan is indicated. The connector is attached to both `wechat-personal-connector_default` and `coke-clean_default`, and an in-container GET to `http://coke-api:8000/healthz` returned HTTP 200.

- [x] **Step 15: Prove outbound reply delivery for both real accounts**

For each account that has a valid session, drive a connector-shaped inbound through `/webhooks/wechat/personal`, allow the turn to reply, then query clean Postgres for the latest `delivery_attempt` row:

```sql
select provider_type, provider_idempotency_key, status, error_code, provider_message_id, attempted_at
from delivery_attempt
where provider_type = 'wechat_personal'
order by attempted_at desc
limit 20;
```

Expected: the relevant rows are `sent` or `delivered`, not `failed/provider_http_409`.

Observed:

- Direct connector probe for olivers with `context_token=codex-invalid-context-token` returned HTTP 202 `{"status":"sent"}` from the connector/iLink path. Current iLink did not reproduce a context-token 409 for the connected olivers session.
- Olivers inbound `codex-smoke-20260530T1838Z-olivers-reminder` produced delivery attempt `inbound:codex-smoke-20260530T1838Z-olivers-reminder:reply|sent||coke-1780166445763-a127f28e9b63`.
- Olivers inbound `codex-smoke-20260530T1845Z-olivers-friend-link` produced delivery attempt `inbound:codex-smoke-20260530T1845Z-olivers-friend-link:reply|sent||coke-1780166587879-338698e854c4`.
- Lizihao inbound `codex-smoke-20260530T1848Z-lizihao-join-friend` accepted and created the active friendship, but the turn failed `invalid_output_protocol` before a reply delivery attempt was created.

## Task 6: Formal End-To-End Smoke And Commit

- [ ] **Step 16: Run the two-account formal flow**

Use real connected wxids and DB as verdict:

1. olivers timed reminder create: one `reminder` plus delivered/sent reply.
2. olivers friend link request: `friend_link` plus delivered/sent reply containing a code.
3. lizihao joins via code: active `friendship`.
4. olivers shared reminder with lizihao: active `shared_reminder`, participant projections, notification facts/recipients, and delivered/sent replies/notifications.
5. Reminder fire: `reminder_fire`; delivery is sent/delivered if iLink accepts latest context token, otherwise an honest failed/undelivered delivery record.

Observed partial:

- The exact olivers reminder phrase found an existing active timed reminder for `跑步` at `2026-05-31 01:00:00+00` and replied that it was already present; it did not create a duplicate reminder.
- Olivers friend-link request returned the active link `https://coke.example/friends/friend_link_tJm4MJt4NQ3Vdaq5ntJtmHG_-K9Qhsif` and delivered/sent the reply to iLink.
- Lizihao joined through that link; DB verdict: friendship `cd671792-c126-4d9e-ad43-ac4221ef2bf6` is active between `635d3bdc-1b02-4a08-acf4-9940b91a9de5` and `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`.
- Blocker: the lizihao join inbound turn failed with `invalid_output_protocol`, so there was no join reply delivery attempt. Because the formal flow requires delivered/sent replies for each phase, shared-reminder creation and reminder-fire delivery were not claimed as complete in this run.

- [ ] **Step 17: Update plan status and commit**

After verification passes, set `Plan Status: complete`, mark every completed checkbox, then commit:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-outbound-durability.md provider_edges/wechat_personal_connector/app.py tests/unit/coke/provider_edges/test_wechat_personal_connector.py coke tests/unit/coke
git commit -m "fix: make personal wechat outbound durable"
```

Expected: one coherent commit on the current branch.
