# Public Locale Hydration Fix

Date: 2026-04-27

Status: Deployed

## Context

Local public site rendering on port 4040 reported two browser errors:

- React hydration mismatch between server English navigation text and client
  Chinese navigation text.
- React console warning for rendering an inline script tag from the root layout.

## Root Cause

The static-exported server HTML rendered the public shell in English, while the
client provider read persisted browser locale state before hydration. That
allowed the first client render to differ from the server HTML. The
before-interactive locale bootstrap script was also unnecessary once client
locale reconciliation was moved after hydration.

## Changes

- Pass a stable static-export-safe English snapshot into `LocaleProvider` so the
  first client render matches the server HTML.
- Reconcile persisted client locale after hydration.
- Remove the inline locale bootstrap script from the root layout.
- Update deploy smoke checks to verify current Kap public copy instead of the
  removed bootstrap marker.

## Verification

- `pnpm --dir gateway/packages/web test`
- `bash scripts/test-deploy-compose-to-gcp.sh`
- `pytest tests/unit/test_repo_os_structure.py -v`
- `zsh scripts/check`
- `curl` smoke on local 4040 for `/`, `/auth/login`, and `/global` confirmed
  no `__next_error__`, `dynamic =`, `locale-bootstrap`, or `__COKE_LOCALE__`.
- Playwright smoke on local 4040 with persisted `coke-locale=zh` confirmed no
  hydration/script console errors and post-hydration Chinese navigation.
- `./scripts/deploy-compose-to-gcp.sh --restart`
- Production `curl` smoke on `https://coke.keep4oforever.com` for `/`,
  `/auth/login`, and `/global` confirmed no `__next_error__`, `dynamic =`,
  `locale-bootstrap`, or `__COKE_LOCALE__`.
- Production Playwright smoke with persisted `coke-locale=zh` confirmed no
  hydration/script console errors and post-hydration Chinese navigation.
