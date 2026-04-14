# GCP Deploy Submodule Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GCP deploy script sync the gateway submodule safely, update public URL envs for the current domain, and verify the deployed public site after restart.

**Architecture:** Keep the existing rsync-based deployment flow, but split root and gateway sync into separate phases. Add a hard guard that compares the root repo’s recorded gateway commit with the local gateway checkout, then perform remote health and public-site smoke checks after compose restart.

**Tech Stack:** Bash, rsync, ssh, Docker Compose, curl, git

---

### Task 1: Document the deployment fix

**Files:**
- Create: `docs/superpowers/specs/2026-04-14-gcp-deploy-submodule-sync-design.md`
- Create: `docs/superpowers/plans/2026-04-14-gcp-deploy-submodule-sync-plan.md`

- [ ] **Step 1: Write the design doc**

Describe:

- why stale gateway submodule deploys are possible
- why a separate gateway rsync pass is required
- why `PUBLIC_BASE_URL` must be able to rewrite remote public URL env values
- what post-restart verification proves success

- [ ] **Step 2: Write the implementation plan**

Document the code changes, verification commands, and deployment sequence used for this rollout.

### Task 2: Add a failing deploy-script regression test

**Files:**
- Create: `scripts/test-deploy-compose-to-gcp.sh`
- Modify: `scripts/deploy-compose-to-gcp.sh`

- [ ] **Step 1: Write the failing test harness**

Create a bash test harness that:

- runs the deploy script against stubbed `git`, `ssh`, `rsync`, and `curl` binaries
- asserts the script fails when the gateway submodule commit does not match the root repo record
- asserts the script uses two `rsync` phases when the submodule commit matches

- [ ] **Step 2: Run the test and confirm the red state**

Run:

```bash
bash scripts/test-deploy-compose-to-gcp.sh
```

Expected:

- the “submodule mismatch” case fails for the wrong reason or the “two rsync phases” case fails,
  proving the current script does not yet satisfy the new behavior.

### Task 3: Implement the deploy-script fix

**Files:**
- Modify: `scripts/deploy-compose-to-gcp.sh`

- [ ] **Step 1: Add submodule guard helpers**

Implement bash helpers that:

- read the expected gateway commit from `git ls-tree HEAD gateway`
- read the actual gateway commit from `git -C "$LOCAL_ROOT/gateway" rev-parse HEAD`
- abort when they differ

- [ ] **Step 2: Split the sync into root and gateway phases**

Change the script so that:

- the root `rsync` excludes `gateway/`
- the gateway `rsync` copies `LOCAL_ROOT/gateway/` to `REMOTE_ROOT/gateway/`
- gateway build artifacts and `.git` metadata are excluded

- [ ] **Step 3: Add public URL override handling**

Support `PUBLIC_BASE_URL` so the script can rewrite remote `.env` values for:

- `DOMAIN_CLIENT`
- `CORS_ORIGIN`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_COKE_API_URL`

- [ ] **Step 4: Add post-restart verification**

When `--restart` is provided, run remote verification for:

- source file presence under `~/coke/gateway/packages/web`
- `http://127.0.0.1:4041/health`
- `http://127.0.0.1:8090/bridge/healthz`
- public homepage/login/old-admin-root smoke checks for the configured public URL, based on the new locale bootstrap marker instead of old bilingual CTA copy

### Task 4: Turn the regression test green

**Files:**
- Use: `scripts/test-deploy-compose-to-gcp.sh`

- [ ] **Step 1: Re-run the deploy-script test**

Run:

```bash
bash scripts/test-deploy-compose-to-gcp.sh
```

Expected:

- all assertions pass
- the test proves mismatch failure, two-phase rsync, and post-restart verification wiring

### Task 5: Update deployment docs

**Files:**
- Modify: `docs/deploy.md`

- [ ] **Step 1: Document the new script behavior**

Add usage notes for:

- the gateway submodule guard
- `PUBLIC_BASE_URL=https://coke.ydyk123.top`
- automatic remote `.env` public URL rewrites
- post-restart smoke verification

### Task 6: Deploy and verify on `gcp-coke`

**Files:**
- Use: remote host `gcp-coke`

- [ ] **Step 1: Run the updated deploy script**

Run:

```bash
PUBLIC_BASE_URL=https://coke.ydyk123.top ./scripts/deploy-compose-to-gcp.sh --restart
```

Expected:

- sync completes
- compose rebuild/restart completes
- built-in verification passes

- [ ] **Step 2: Independently verify the remote stack**

Run:

```bash
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml ps gateway coke-bridge'
ssh gcp-coke 'curl -fsS http://127.0.0.1:4041/health'
ssh gcp-coke 'curl -fsS http://127.0.0.1:8090/bridge/healthz'
```

Expected:

- `gateway` and `coke-bridge` are healthy
- both internal health endpoints return success

- [ ] **Step 3: Verify the public domain**

Run:

```bash
ssh gcp-coke 'curl -fsS https://coke.ydyk123.top/ | grep -q "__COKE_LOCALE__"'
ssh gcp-coke '! curl -fsS https://coke.ydyk123.top/ | grep -q "Sign in / 登录"'
ssh gcp-coke 'test "$(curl -k -s -o /dev/null -w "%{http_code}" https://coke.ydyk123.top/coke/login)" = "200"'
ssh gcp-coke 'test \"$(curl -k -s -o /dev/null -w \"%{http_code}\" https://coke.ydyk123.top/login)\" = \"404\"'
```

Expected:

- the new locale-aware public homepage and user login route are live
- the old root admin login is no longer exposed
