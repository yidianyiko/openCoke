# GCP Deploy Submodule Sync Design

## Goal

Make `scripts/deploy-compose-to-gcp.sh` reliably deploy the latest merged gateway/web changes by
eliminating stale submodule sync mistakes and adding deployment-time verification for the public
site.

## Problem

The root repository deploy flow copies the whole checkout with one `rsync` pass. The `gateway/`
directory is a git submodule, but the script does not verify that the local `gateway/` worktree is
checked out at the exact commit recorded in the root repo. That makes it easy to deploy an older
gateway tree even when the root repo itself is current.

Observed symptoms:

- Local root repo points at gateway commit `554edfe`.
- The deployed public site still serves the old homepage/dashboard shape.
- The remote `~/coke/gateway/packages/web` tree still contains the old route structure.

## Constraints

- Keep the existing `rsync -> remote docker compose up --build` deployment model.
- Do not depend on the remote server being a healthy git checkout.
- Preserve the remote `.env` secrets file.
- Allow deployment verification to target the current public domain `https://coke.ydyk123.top`.

## Chosen Approach

### 1. Enforce submodule commit alignment before sync

Before any file transfer, the deploy script must compare:

- the gateway commit recorded in the root repo (`git ls-tree HEAD gateway`)
- the current local gateway checkout (`git -C gateway rev-parse HEAD`)

If they differ, the script must fail fast with a clear error that tells the operator to update the
local submodule checkout first.

This closes the most likely path for “root repo is current but deployed gateway is stale”.

### 2. Sync the root repo and the gateway submodule separately

The root `rsync` pass should explicitly exclude `gateway/`.

Then a second `rsync` pass should copy `gateway/` into `REMOTE_ROOT/gateway/`, with its own exclude
rules for:

- `gateway/.git`
- `node_modules`
- `.next`
- `dist`
- `out`

This makes the submodule sync explicit, removes old gateway files on the remote host, and avoids
shipping a broken submodule `.git` pointer file.

### 3. Support a public base URL override for deploy-time verification

The script should accept a public base URL override via `PUBLIC_BASE_URL`. When provided, the script
updates the remote `.env` public URL fields before restart:

- `DOMAIN_CLIENT`
- `CORS_ORIGIN`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_COKE_API_URL`

For this environment, deployment will use:

- `PUBLIC_BASE_URL=https://coke.ydyk123.top`

This ensures the rebuilt gateway web bundle points at the current public domain instead of the old
`keep4oforever.com` values still present on the server.

### 4. Add post-restart verification

When `--restart` is used, the script should verify four things:

1. Remote source tree contains the new homepage files.
2. Remote compose services report healthy internal endpoints.
3. Public homepage contains the locale bootstrap marker and no longer serves the old bilingual CTA text.
4. Public `/coke/login` returns `200`, while the old `/login` entry remains `404`.

These checks should run from the remote host when possible so local network/proxy behavior does not
mask deployment status.

## Out of Scope

- Replacing the deployment model with release bundles or image registry publishing.
- Reworking the production Nginx site management flow.
- Changing business logic in the gateway web or API beyond what is required for correct deployment.

## Success Criteria

Deployment is successful when all of the following are true:

- The deploy script refuses to run if local `gateway/` is not on the root repo’s recorded commit.
- The remote `~/coke/gateway/packages/web` tree contains the new homepage source files after sync.
- `docker compose -f docker-compose.prod.yml up -d --build --remove-orphans` completes successfully.
- Remote health checks for gateway and bridge succeed.
- `https://coke.ydyk123.top/` serves the new locale-aware public homepage.
- `https://coke.ydyk123.top/coke/login` returns `200`.
- `https://coke.ydyk123.top/login` returns `404`.
