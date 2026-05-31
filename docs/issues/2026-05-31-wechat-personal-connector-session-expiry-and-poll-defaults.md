---
kind: progress_note
status: resolved
title: WeChat personal connector kept expired sessions connected and lost poll defaults
created_at: 2026-05-31
updated_at: 2026-05-31
surface:
  - wechat-personal
  - provider-edge
  - deployment
---

# WeChat Personal Connector Session Expiry And Poll Defaults

## Problem

Production root cause was already confirmed before this repair:

- `/send` returned HTTP 502 for iLink `errcode == -14` session timeout but left
  the connector session as `status: connected`.
- `/healthz` therefore continued to report the account connected after iLink had
  declared the session dead.
- `WECHAT_CONNECTOR_WEBHOOK_URL` and `WECHAT_CONNECTOR_AUTOSTART_POLL` only
  lived in the server `.env`; a rebuild could drop them and leave inbound
  polling disabled without an obvious container-level configuration signal.

## Why It Mattered

The connector could keep stale account reachability state after a failed send,
and a rebuilt service could stop forwarding inbound personal-WeChat messages
even though the container still ran.

## Fix

- The `/send` path now downgrades the matched connected session on iLink
  session-expired business failures using the same state mutation as the poll
  loop: `status: expired`, empty `token`, empty `cursor`, and empty
  `context_tokens`.
- `ret == -2` remains retryable and does not expire the session.
- The connector compose service now provides non-secret defaults for
  `WECHAT_CONNECTOR_WEBHOOK_URL` and `WECHAT_CONNECTOR_AUTOSTART_POLL` while
  keeping `env_file: ../../.env` for secrets and environment overrides.

## Verification

Local verification:

```bash
.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py -v
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Result:

- Connector test module: 19 passed.
- Suggested surface command: `zsh scripts/verify-surface clean-rebuild-backend
  repo-os-docs`.
- Clean-rebuild backend: 587 passed.
- Repo-OS docs check: passed.
