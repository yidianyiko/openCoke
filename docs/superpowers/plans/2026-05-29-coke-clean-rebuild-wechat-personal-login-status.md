# WeChat Personal Login Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** in_progress

**Goal:** Make personal-WeChat login-status polling return promptly and never turn transient connector slowness into a customer API 500.

**Architecture:** The provider-edge connector owns iLink protocol polling and caches the latest per-session login state. Coke's `wechat_personal` adapter treats connector read timeouts as retryable pending status while preserving the existing rule that only a real confirmed/connected iLink status binds a wxid and marks the channel connected.

**Tech Stack:** Python Flask connector, `httpx`, existing clean Coke provider/domain services, pytest with fakes/in-memory state, Docker Compose deployment on `gcp-coke`.

---

## Files

- Modify: `provider_edges/wechat_personal_connector/app.py` for cached login status polling and non-blocking connector request handling.
- Modify: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py` for connector cached-status and background-poll tests.
- Modify: `coke/providers/wechat_personal.py` for pending-on-timeout provider behavior and shorter status timeout.
- Modify: `tests/unit/coke/channel_reachability/test_provider_adapters.py` for provider timeout behavior.
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-login-status.md` to track execution and final verification.

## Task 1: Diagnose The Live Timeout

- [x] **Step 1: Inspect the deployed connector process and logs**

Run:

```bash
ssh gcp-coke 'cd /home/whoami/wechat-personal-connector && docker compose ps && docker compose logs --tail=200 wechat-personal-connector'
```

Observed: connector logs show `/login/status` raising `httpx.ReadTimeout` from `_poll_login_status_once -> IlinkClient.get_qr_status`, so the request handler is doing inline iLink status polling.

- [x] **Step 2: Time connector endpoints inside the connector container**

Run:

```bash
ssh gcp-coke 'docker exec wechat-personal-connector-wechat-personal-connector-1 sh -lc "time curl -sS -o /tmp/health.out -w \"%{http_code}\\n\" http://127.0.0.1:8095/healthz && cat /tmp/health.out"'
```

Then repeat for `/login/status` with a real account/session pair from the live state file.

Observed: `/healthz` returned `200` in `0.277s`. A later `/login/status` for an already-expired session returned `200` in `0.904s`, but the live logs captured the reproduced failure path where pending sessions waited on iLink until `ReadTimeout`. State inspection showed only waiting sessions and zero connected sessions, so the reproduced timeout was not caused by a connected-session `getupdates` loop.

## Task 2: Provider Timeout Contract

- [x] **Step 1: Write a failing provider test**

Add this behavior in `tests/unit/coke/channel_reachability/test_provider_adapters.py`:

```python
def test_wechat_personal_login_status_timeout_returns_pending_status():
    request = httpx.Request(
        "GET",
        "https://connector.example/login/status?account_id=acct_1&session_id=session_1",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow connector", request=request)

    adapter = WeChatPersonalAdapter(
        endpoint_url="https://connector.example/send",
        api_key="wx-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    status = adapter.poll_login_status(account_id="acct_1", session_id="session_1")

    assert status == {
        "account_id": "acct_1",
        "session_id": "session_1",
        "status": "waiting_for_scan",
        "connector_status": "timeout",
        "retryable": True,
    }
```

- [x] **Step 2: Run the failing provider test**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py::test_wechat_personal_login_status_timeout_returns_pending_status -v
```

Observed: failed with `httpx.ReadTimeout: slow connector`.

- [x] **Step 3: Implement minimal provider timeout handling**

Update `WeChatPersonalAdapter.poll_login_status()` so `httpx.TimeoutException` and `httpx.NetworkError` return:

```python
{
    "account_id": account_id,
    "session_id": session_id,
    "status": "waiting_for_scan",
    "connector_status": "timeout",
    "retryable": True,
}
```

Keep non-timeout HTTP status failures as real errors.

- [x] **Step 4: Verify the provider test passes**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py::test_wechat_personal_login_status_timeout_returns_pending_status -v
```

Observed: `1 passed`.

## Task 3: Connector Cached Login Status

- [x] **Step 1: Write failing connector cached-status tests**

Add tests in `tests/unit/coke/provider_edges/test_wechat_personal_connector.py`:

```python
def test_login_status_returns_cached_waiting_state_without_inline_ilink_poll(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    state.update_session(
        "session-1",
        {
            "account_id": "acct_1",
            "status": "waiting_for_scan",
            "qrcode": "qr-1",
            "qrcode_image": "https://weixin.qq.com/x/1",
            "qrcode_image_data_url": "data:image/png;base64,qr",
        },
    )
    ilink = FakeIlinkClient()
    app = create_app(
        ConnectorConfig(api_key="connector-key"),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    response = app.test_client().get(
        "/login/status?account_id=acct_1&session_id=session-1",
        headers={"Authorization": "Bearer connector-key"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "waiting_for_scan"
    assert ilink.status_calls == []
```

Also add a background-poll test that calls the new helper once and asserts `confirmed` becomes public `connected`.

- [x] **Step 2: Run the failing connector tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_login_status_returns_cached_waiting_state_without_inline_ilink_poll -v
```

Observed: cached-status test failed because `/login/status` changed the session to `connected`; background-poll test failed because `/login/start` left the session `waiting_for_scan`.

- [x] **Step 3: Implement background login polling**

Update connector code so:

```text
/login/start creates the session and starts a daemon login poll thread for that session.
/login/status only reads `ConnectorState` and returns `_session_public_view(...)`.
The login poll thread repeatedly calls `_poll_login_status_once(...)` until connected, expired, or login_error.
When the session becomes connected, start the existing getupdates poll loop.
```

Use per-session thread bookkeeping so duplicate `/login/status` calls do not start duplicate iLink status calls.

- [x] **Step 4: Verify connector tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
```

Observed: the two new connector tests passed.

## Task 4: Focused And Full Verification

- [x] **Step 1: Run focused unit tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py tests/unit/coke/channel_reachability/test_provider_adapters.py tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py -v
```

Observed: `56 passed`.

- [x] **Step 2: Run the requested unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Observed: `408 passed`.

- [x] **Step 3: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Observed: `suggest-verification` suggested clean-rebuild backend, web, and repo-OS docs because `HEAD~1` also includes prior committed web changes; this turn's working diff is connector/provider/tests/plan only. `review-trigger` reported `human_review_required: no`. `zsh scripts/check` passed for the repo-OS plan/doc surface.

## Task 5: Deploy And Live Smoke

- [ ] **Step 1: Commit the verified code and plan**

Run:

```bash
git add provider_edges/wechat_personal_connector/app.py tests/unit/coke/provider_edges/test_wechat_personal_connector.py coke/providers/wechat_personal.py tests/unit/coke/channel_reachability/test_provider_adapters.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-wechat-personal-login-status.md
git commit -m "fix: keep personal wechat login status nonblocking"
```

- [ ] **Step 2: Redeploy the connector and Coke API if needed**

Preserve `/home/whoami/coke-clean/.env`, keep `evolution-*` and web up, rebuild/recreate only the connector and clean API if provider code changed.

- [ ] **Step 3: Prove live status polling is prompt**

For olivers (`ae02ff016fcd4d39a189e51c8c8a31e6`) and lizihao (`635d3bdc1b024a08acf49940b91a9de5`), reset personal-WeChat channel/session state, start two new connects, then call:

```bash
GET /api/channels/wechat-personal/login-status?account_id=<id>&session_id=<sid>
```

several times for both sessions. Record HTTP code, elapsed time, and JSON body. Expected: HTTP 200 quickly with `connection_state=connecting` and `connector_status=waiting_for_scan` until a real iLink confirmation occurs.

- [ ] **Step 4: Mark plan complete**

After tests and live smoke pass, set `Plan Status: complete` and commit the plan update if needed.
