# P1 Backend Security Gap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the p1-backend conformance and security gaps without touching web paths or `coke/app.py` blueprint registration.

**Architecture:** Keep domain ownership intact: ChannelReachability observes usable channels and calls an injected deferred-friend-link port, SocialScheduling owns friendship completion and notification delivery state, CalendarImport consults IdentityAccess before import work, and provider webhooks authenticate at the route boundary before adapter normalization. No schema changes are allowed; all persistence stays on `coke/schema.py`.

**Tech Stack:** Python 3.12, Flask blueprints, SQLAlchemy metadata contracts, in-memory domain repositories, pytest, existing clean-rebuild domain services.

---

**Plan Status:** complete
**Status Date:** 2026-05-31
**Freshness Check:** Read master plan Task 5/9/10 and Architecture Issues, requirements §5.1/§5.3/§5.6/§5.9/§5.10/§5.13, target architecture §3.1/§3.2/§3.5/§3.6/§4/§6/§9/§14, `coke/schema.py`, IdentityAccess/ChannelReachability/SocialScheduling/CalendarImport services, provider webhook routes, and connector tests on 2026-05-31.

## File Structure

- Modify: `coke/domains/channel_reachability/service.py` to accept an optional deferred friend-link completion port and call it after a channel becomes usable.
- Modify: `tests/unit/coke/channel_reachability/test_channel_reachability_service.py` for deferred friend-link self-completion and idempotency.
- Modify: `coke/domains/calendar_import/service.py` to require an IdentityAccess-style access gate before import starts.
- Modify: `tests/unit/coke/calendar_import/test_calendar_import_service.py` and `tests/unit/coke/calendar_import/test_calendar_import_routes.py` for denied/allowed access behavior.
- Modify: `coke/config.py` to add optional `COKE_WEBHOOK_INBOUND_SECRET`.
- Modify: `coke/api/provider_webhooks.py` to enforce `X-Coke-Webhook-Secret` / `X-Webhook-Secret` / bearer-token authentication when the secret is configured.
- Modify: `tests/unit/coke/channel_reachability/test_provider_webhooks.py` for configured-secret rejection, correct-secret acceptance, and unset-secret transition mode.
- Modify: `provider_edges/wechat_personal_connector/app.py`, `provider_edges/wechat_personal_connector/README.md`, and `tests/unit/coke/provider_edges/test_wechat_personal_connector.py` so the owned connector sends the shared secret header.
- Modify: `deploy/env/coke.env.example`, `docs/deploy.md`, and/or `docs/clawscale_bridge.md` only to document deploy-time webhook secret configuration.
- Modify: `coke/domains/reminder/service.py` if the raw `str(ValueError)` batch reason path is confirmed as user-visible API output.
- Modify: existing route tests for cleaned error output.

## Task 1: Deferred Friend-Link Self-Completion

**Files:**
- Modify: `tests/unit/coke/channel_reachability/test_channel_reachability_service.py`
- Modify: `coke/domains/channel_reachability/service.py`

- [x] **Step 1: Write failing channel-ready callback tests**

Add tests that instantiate `ChannelReachabilityService` with a fake `deferred_friend_link_completion` port:

```python
class FakeDeferredFriendLinkCompletion:
    def __init__(self) -> None:
        self.calls = []

    def complete_pending_for_account(self, account_id: str) -> None:
        self.calls.append(account_id)
```

Cover:
- `mark_connected("joiner", "channel_1")` calls the port once after route resolution and `observe_usable_channel`.
- calling `mark_connected` again for the same already-connected channel still calls the port safely, relying on SocialScheduling idempotency.
- inbound provisioning through `accept_provider_inbound()` also calls the port when it creates/connects the usable channel.

- [x] **Step 2: Verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_channel_reachability_service.py -q
```

Expected: the new tests fail because `ChannelReachabilityService.__init__` does not accept the deferred completion port and no call is made on usable-channel observation.

- [x] **Step 3: Implement the port call**

Add a small protocol in `coke/domains/channel_reachability/service.py`:

```python
class DeferredFriendLinkCompletionPort(Protocol):
    def complete_pending_for_account(self, account_id: str) -> None: ...
```

Accept `deferred_friend_link_completion: DeferredFriendLinkCompletionPort | None = None` in `ChannelReachabilityService.__init__`. After `identity_access.observe_usable_channel(account_id)` in `mark_connected`, call:

```python
if self.deferred_friend_link_completion is not None:
    self.deferred_friend_link_completion.complete_pending_for_account(account_id)
```

Do not import SocialScheduling from ChannelReachability.

- [x] **Step 4: Verify GREEN**

Run the same focused channel test command. Expected: all tests in the file pass.

## Task 2: Calendar Import Access Gate

**Files:**
- Modify: `tests/unit/coke/calendar_import/test_calendar_import_service.py`
- Modify: `tests/unit/coke/calendar_import/test_calendar_import_routes.py`
- Modify: `coke/domains/calendar_import/service.py`
- Modify: `coke/api/calendar_import_routes.py`

- [x] **Step 1: Write failing service and route tests**

Add a fake access gate:

```python
class FakeAccessGate:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.calls = []

    def check_access_for_action(self, account_id: str, action: str):
        self.calls.append((account_id, action))
        return SimpleNamespace(
            allowed=self.allowed,
            fact={"type": "account_access_denied", "denial_reason": "subscription_inactive"},
        )
```

Service tests:
- denied account raises `CalendarImportError("access_denied")`
- Google client is not called and no import run is created
- allowed account proceeds and imports as before

Route test:
- when the route receives an access-denied service error, response is a safe structured error with code/fact, not raw exception text.

- [x] **Step 2: Verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/calendar_import -q
```

Expected: the denied service test fails because no access gate is checked before authorization/preflight/import.

- [x] **Step 3: Implement fail-closed calendar gate**

Add an optional `access_gate` constructor dependency to `CalendarImportService`. In `import_google_calendar`, before `_require_active_authorization()` and before `google_client.list_events()`, call:

```python
decision = self.access_gate.check_access_for_action(account_id, "calendar_import")
if not decision.allowed:
    raise CalendarImportError("access_denied", fact=dict(decision.fact))
```

If no access gate was injected, raise `CalendarImportError("access_gate_unavailable")` rather than importing fail-open.

If route construction owns the only available `identity_service`, set `calendar_import_service.access_gate = identity_service` inside `create_calendar_import_blueprint()` before route handlers execute, without changing `coke/app.py`.

- [x] **Step 4: Verify GREEN**

Run the same calendar import test command. Expected: all calendar import tests pass.

## Task 3: Provider Webhook Source Authentication

**Files:**
- Modify: `tests/unit/coke/channel_reachability/test_provider_webhooks.py`
- Modify: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py`
- Modify: `coke/config.py`
- Modify: `coke/api/provider_webhooks.py`
- Modify: `provider_edges/wechat_personal_connector/app.py`
- Modify: `provider_edges/wechat_personal_connector/docker-compose.yml`
- Modify: `provider_edges/wechat_personal_connector/README.md`
- Modify: `deploy/env/coke.env.example`
- Modify: `docs/deploy.md` and/or `docs/clawscale_bridge.md`

- [x] **Step 1: Write failing webhook auth tests**

In provider webhook route tests, cover:
- `webhook_secret="secret-1"` and no header returns `401 {"error": {"code": "webhook_unauthorized"}}` and does not call adapter normalization.
- correct `X-Coke-Webhook-Secret: secret-1` accepts the payload.
- correct `X-Webhook-Secret: secret-1` also accepts the payload for Evolution configurability.
- correct `Authorization: Bearer secret-1` accepts the payload.
- unset secret accepts the payload for transition mode.

In connector tests, assert posted webhook headers include:

```python
{"X-Coke-Webhook-Secret": "clean-webhook-secret"}
```

when the connector config has `webhook_inbound_secret="clean-webhook-secret"`.

- [x] **Step 2: Verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_webhooks.py tests/unit/coke/provider_edges/test_wechat_personal_connector.py -q
```

Expected: route auth tests fail because no secret gate exists; connector header tests fail because the connector only sends the old webhook API key.

- [x] **Step 3: Implement route and connector wiring**

Add `webhook_inbound_secret: str | None = None` to `Settings` loaded from `COKE_WEBHOOK_INBOUND_SECRET`.

Add `webhook_secret: str | None = None` to `create_provider_webhook_blueprint()` and enforce before `_json_payload()` / adapter normalization:

```python
if webhook_secret and not _webhook_secret_matches(request.headers, webhook_secret):
    raise ChannelReachabilityError("webhook_unauthorized")
```

Map `webhook_unauthorized` to HTTP 401. Accept any of:
- `X-Coke-Webhook-Secret: <secret>`
- `X-Webhook-Secret: <secret>`
- `Authorization: Bearer <secret>`

Update the owned WeChat personal connector config to read `COKE_WEBHOOK_INBOUND_SECRET` and include `X-Coke-Webhook-Secret` on posts to Coke. Document Evolution deploy config: configure the Evolution webhook to send the same value as either `X-Webhook-Secret` or `Authorization: Bearer <secret>`.

- [x] **Step 4: Verify GREEN**

Run the same webhook/connector focused command. Expected: tests pass.

## Task 4: Raw Exception-String Hygiene

**Files:**
- Modify: `tests/unit/coke/reminder/test_reminder_routes.py` or `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `coke/domains/reminder/service.py`

- [x] **Step 1: Confirm and write failing test**

The suspected path is `ReminderService.execute_batch()` returning `ReminderItemResult(reason=str(error))` when repository/reminder creation raises `ValueError`. Write a test where the fake repository raises:

```python
ValueError("duplicate key value violates unique constraint reminder_owner_idx")
```

Assert the returned item has a typed safe reason such as `"reminder_write_failed"` and the raw SQL/constraint text is absent from the result body.

- [x] **Step 2: Verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder -q
```

Expected: the new test fails because the raw exception string is returned as the item reason.

- [x] **Step 3: Replace raw exception reason**

Change only the generic `except ValueError` path in `ReminderService.execute_batch()` to return:

```python
ReminderItemResult(state="failed", reason="reminder_write_failed", fact={"type": "reminder_write_failed"})
```

Keep existing typed `ReminderError` behavior unchanged.

- [x] **Step 4: Verify GREEN**

Run the same reminder focused command. Expected: tests pass.

## Task 5: Full Verification And Commit

**Files:**
- Modify this plan file to mark all steps complete and set `Plan Status: complete` only after verification passes.

- [x] **Step 1: Run focused suites**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability tests/unit/coke/calendar_import tests/unit/coke/provider_edges/test_wechat_personal_connector.py tests/unit/coke/reminder -q
```

Expected: all focused tests pass.

- [x] **Step 2: Run full unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: full unit suite passes.

- [x] **Step 3: Run integration command requested by leader**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration -q
```

If there is no `tests/integration` path or local Postgres is unavailable, record the exact output as a verification gap instead of claiming it passed.

- [x] **Step 4: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Use any additional suggested surface command that applies to the touched files.

- [x] **Step 5: Mark plan complete and commit**

After verification, update this file:

```markdown
**Plan Status:** complete
```

Then commit coherent changes on `fix/p1-backend`:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-p1-backend.md coke tests provider_edges deploy docs
git commit -m "fix: close p1 backend security gaps"
```
