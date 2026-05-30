# Coke Clean Rebuild: Web + Personal WeChat Pairing

Plan Status: complete

## Goal

Make the live Coke web app usable for a two-account personal-WeChat test on
gcp-coke by restoring the web service, wiring web-first personal-WeChat pairing
codes through the clean API and connector webhook path, provisioning two
verified test accounts, deploying non-disruptively, and verifying the live
flows.

## Constraints

- Build only on `coke/schema.py`; do not add or fork schema.
- Do not add compatibility shims, legacy imports, fallback prose, keyword
  routing, or auto-provisioning for `wechat_personal`.
- Keep backend ownership boundaries:
  - `IdentityAccess` owns `auth_artifact` and `channel_identity`.
  - `ChannelReachability` owns `channel`, route status, provider connect state.
  - Web is a thin client over the Python API.
- Only shared runtime file edit allowed outside owned surfaces is `coke/app.py`
  if a blueprint registration change is required.
- Use `/data/projects/coke/.venv/bin/python` and run pytest from repository
  root.
- Commit small coherent changes on the current branch; do not push.

## Steps

- [x] Confirm current service/deploy failure shape from local compose/deploy
      files and live `gcp-coke` process state without printing secrets.
- [x] Write failing backend tests for web-first personal-WeChat connect:
      - channel connect route issues or reuses a pending `pairing_code`;
      - channel status surfaces pending `pairing_code`, expiry, and
        instructions;
      - inbound `/webhooks/wechat/personal` accepts connector payloads with
        `pairing_code` and passes them to channel reachability;
      - reachability binds an unbound `wxid` only when a valid code is present
        and rejects unbound messages without a valid code.
- [x] Run the new backend tests and capture the expected failures.
- [x] Implement backend pairing support:
      - add identity-access lookup/ensure methods for unconsumed
        `pairing_code` artifacts;
      - add reachability service pending-connect behavior for
        `wechat_personal`;
      - expose a clean API route for `POST
        /api/channels/wechat-personal/connect`;
      - include pending pairing fields in channel status responses.
- [x] Run the backend tests again and keep the relevant unit suite green.
- [x] Write failing web tests for the clean auth/channel API contract and the
      channels page pairing-code display.
- [x] Implement web thin-client changes:
      - map login/register/profile to the clean Python auth API;
      - map the WeChat channel helpers to the clean channel status/connect
        API;
      - display pairing code, expiry/state, and instructions instead of a QR
        code for personal-WeChat pairing.
- [x] Run web tests/build for the touched web surfaces.
- [x] Fix deployment stability:
      - remove `coke-web` profile gating from the clean compose service;
      - remove deploy-script behavior that deletes `coke-web`;
      - preserve existing clean `.env` values while adding required web/API
        public URLs;
      - include web health evidence in deploy verification.
- [x] Run diff-aware repository verification and the broad unit command:
      - `zsh scripts/suggest-verification --base HEAD~1`;
      - `zsh scripts/review-trigger --base HEAD~1`;
      - `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`.
- [x] Commit verified local code/docs/test changes.
- [x] Deploy non-disruptively to `gcp-coke` while preserving `.env`,
      connector, and Evolution services.
- [x] Provision verified active test accounts for:
      - `olivers`;
      - `lizihao`.
- [x] Verify live behavior:
      - `/healthz` returns 200;
      - `http://127.0.0.1:4042/auth/login` returns 200 on the host;
      - `https://coke.keep4oforever.com/auth/login` returns 200 through nginx;
      - both test accounts can log in through `/api/auth/login`;
      - connect issues a real pairing code;
      - simulated connector POST to `/webhooks/wechat/personal` binds a test
        `wxid` to the correct account and connects the channel;
      - follow-up message creates the expected conversation/turn/reminder
        evidence, or record the exact blocker if the runtime cannot complete
        reminder creation.
- [x] Update this plan with completed checkboxes and set Plan Status to
      `complete` only after verification passes.

## Verification Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
cd web && pnpm test
cd web && pnpm build
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

## Live Smoke Commands

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4042/auth/login
curl -sS -o /dev/null -w '%{http_code}\n' https://coke.keep4oforever.com/auth/login
curl -sS https://coke.keep4oforever.com/healthz
```
