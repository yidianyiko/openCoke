# Coke WeChat User Entry Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead user bind QR with a real Coke-owned landing page and make the bind flow complete without depending on a missing iLink end-user deep link.

**Architecture:** Keep the existing website-first bind session model, but stop returning the raw public WeChat entry URL directly to the browser. Instead, each bind session will generate a Coke bridge landing URL that always opens, render per-session instructions there, and allow binding by either inbound `contextToken` or a one-time bind code carried in the user's first WeChat message.

**Tech Stack:** Flask bridge, Mongo DAOs, Next.js web frontend, pytest

---

### Task 1: Bind Session Model And Matching

**Files:**
- Modify: `connector/clawscale_bridge/wechat_bind_session_service.py`
- Modify: `dao/wechat_bind_session_dao.py`
- Test: `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`

- [ ] Add failing tests for three behaviors:
  - bind sessions return a Coke bridge landing URL instead of the raw public entry template
  - placeholder / missing public entry configuration does not leak a dead URL into the user QR
  - a one-time bind code in the inbound message text can consume the pending session

- [ ] Run the focused test file and confirm the new tests fail before implementation:
  - `pytest tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py -v`

- [ ] Implement the minimal data and service changes:
  - generate and persist a short `bind_code` per session
  - build `connect_url` from `bind_base_url + /user/wechat-bind/entry/<bind_token>`
  - treat `placeholder.invalid` as unavailable public-entry config
  - add lookup / consume-by-bind-code support alongside existing `contextToken` support

- [ ] Re-run:
  - `pytest tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py -v`

### Task 2: Bridge Landing Page And Inbound Fallback

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `connector/clawscale_bridge/identity_service.py`
- Modify: `connector/clawscale_bridge/templates/bind.html`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Test: `tests/unit/connector/clawscale_bridge/test_identity_service.py`

- [ ] Add failing tests for:
  - `/user/wechat-bind/entry/<bind_token>` renders a valid page for an active session
  - expired / missing sessions render a clear unavailable state
  - inbound messages without `contextToken` can still bind when the text contains the pending bind code

- [ ] Run the focused bridge tests and confirm RED:
  - `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_identity_service.py -v`

- [ ] Implement the minimal bridge behavior:
  - add a Coke-owned landing route for bind sessions
  - render instructions plus the one-time bind code
  - optionally expose a real public WeChat entry link when configured
  - fall back to bind-code matching before returning `bind_required`

- [ ] Re-run:
  - `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_identity_service.py -v`

### Task 3: User-Facing Copy And Verification

**Files:**
- Modify: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
- Optionally modify: `docs/clawscale_bridge.md`
- Test: `gateway/packages/web/lib/coke-user-bind.test.ts`

- [ ] Update the Coke bind page copy so it no longer promises a direct chat deep link when the system may need the landing-page instructions.

- [ ] If helper logic changes, add or update the smallest relevant web test and run:
  - `pnpm -C gateway --filter @clawscale/web test`

- [ ] Run full focused verification for this fix:
  - `pytest tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_identity_service.py -v`
  - `pnpm -C gateway --filter @clawscale/web test`

- [ ] Do a local smoke check in the worktree:
  - create a bind session
  - open the generated landing URL
  - confirm it no longer points at `placeholder.invalid`
