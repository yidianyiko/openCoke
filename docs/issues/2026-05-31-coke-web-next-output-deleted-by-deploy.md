---
kind: incident
status: resolved
surface:
  - clean-web
  - deploy
created_at: 2026-05-31
updated_at: 2026-05-31
---

# 2026-05-31 Coke Web Next Output Deleted By Deploy

## What Happened

The production homepage at `https://coke.keep4oforever.com/` rendered with a
broken visual structure. The HTML still returned 200, but one of the
stylesheet URLs referenced by the page returned `500 Internal Server Error`.

## Why It Matters

Direct route checks were not enough: the page shell was reachable while the
static CSS and route manifest files needed by the browser were missing from the
running Next.js app.

## Affected Surfaces

- `coke-web` on `gcp-coke:/home/whoami/coke-clean`
- `scripts/deploy-compose-to-gcp.sh`
- `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`

## Evidence

- Before recovery, the homepage referenced
  `/_next/static/css/e62b464d71afcabe.css`, but that URL returned
  `500 text/plain` with `Internal Server Error`.
- `coke-web` logs reported missing client reference manifests, including
  `Invariant: The client reference manifest for route "/demos" does not exist`.
- The running container had no `/app/.next` directory after deployment.
- `coke-web` had been up longer than the recently redeployed backend services,
  which matched a deploy that rsynced source files and deleted build output
  without recreating the web container.

## Root Cause

The clean deploy script rsynced `web/` with `--delete` but did not exclude
Next.js build output. Because `coke-web` runs from a bind-mounted source
directory and builds `.next` inside the container at startup, rsync deleted the
remote `web/.next` directory while the existing Next process continued serving
cached HTML that referenced the now-missing assets.

## Resolution

- Recreated only `coke-web` on production, which rebuilt `.next` and restored
  the missing CSS and client reference manifests.
- Updated the deploy script to preserve `.next` during rsync and force-recreate
  `coke-web` after backend migration checks.
- Added a deploy-contract test covering both safeguards.

## Verification

- Production CSS after recovery:
  - `/_next/static/css/e8807a053b2422f8.css` returned `200 text/css`.
  - `/_next/static/css/e62b464d71afcabe.css` returned `200 text/css`.
- Production routes `/auth/register` and `/demos` returned `200 text/html`.
- Playwright loaded the homepage with no failed requests; `.hero-grid`
  computed to `display: grid`, `.site-header__inner` computed to
  `display: flex`, and both stylesheet responses were 200.
