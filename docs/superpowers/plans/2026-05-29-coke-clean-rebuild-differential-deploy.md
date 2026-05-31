# Coke Clean Rebuild Differential Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:systematic-debugging for deploy evidence, superpowers:test-driven-development for script behavior changes, and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/deploy-compose-to-gcp.sh` differential so backend-only deploys skip the expensive `coke-web` rebuild, and keep rollback snapshots out of the clean deploy path.

**Architecture:** The deploy script records the last successful deployed git SHA in `/home/whoami/coke-clean/.deployed-sha`, computes the local changed paths against that SHA, classifies the deploy as backend-only, web-including, full, or no-op, and recreates only the affected service containers. It always preserves product data and connected provider sessions by leaving `postgres`, `redis`, accounts/channels, Evolution, and the WeChat connector untouched while still running Alembic upgrade/check and health probes for real deploys.

**Tech Stack:** Bash, SSH, rsync, Docker Compose, Alembic, pytest static deploy-contract tests.

---

**Plan Status:** in-progress
**Status Date:** 2026-05-31
**Source Specs:** `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`; `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md` §5.1/§5.3/§5.13; `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md` §0/§13/§14/§15.

## File Structure

- Modify `scripts/deploy-compose-to-gcp.sh`: add SHA marker discovery, changed-path classification, differential rsync source selection, backend-service-only recreate, optional web recreate, no-op path, marker write after successful deploy, and snapshot-free assertions by absence.
- Modify `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`: replace stale "always recreate web" assertions with tests for backend-only, web, no-op, no-snapshot, Alembic, and health behavior.
- Modify this plan as steps complete; set `Plan Status: complete` only after verification passes.

## Task 1: Root Cause And Plan Gate

- [x] **Step 1: Read only the deploy-relevant source slices**

Read the master clean-rebuild plan package rule and architecture watch section, requirements §5.1/§5.3/§5.13 for login/channel/session preservation checks, target architecture §0/§13/§14/§15 for clean rebuild and no rollback/fallback invariants, `coke/schema.py` table names, the current deploy script, deploy contract tests, compose files, and the existing web-output deploy incident.

- [x] **Step 2: Identify current deploy root cause**

Root cause: `scripts/deploy-compose-to-gcp.sh` always runs broad compose startup and then unconditionally runs:

```bash
docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml up -d --no-deps --force-recreate coke-web
```

Since `coke-web` starts with `pnpm install && pnpm build && pnpm start`, every forced web recreate pays the full Next.js build cost even when only backend/deploy files changed.

## Task 2: Failing Deploy Contract Tests

**Files:**
- Modify: `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`

- [x] **Step 1: Add backend-only differential assertions**

Add a test that reads the deploy script and asserts it has a backend-only service set:

```python
for service in ("coke-api", "coke-worker", "coke-scheduler", "coke-outbox-relay"):
    assert service in script
assert "DEPLOY_TIER=backend" in script
assert "coke-web" not in backend_only_command
```

- [x] **Step 2: Add web-change assertions**

Add a test that asserts web changes select `DEPLOY_TIER=web` and the web recreate command remains present only inside the web/full deploy branch.

- [x] **Step 3: Add no-op and snapshot-removal assertions**

Add tests that assert the script has a clear no-op branch when no relevant changed paths exist and contains none of `pg_dump`, `tar -`, `tar czf`, `rollback`, or `snapshot`.

- [x] **Step 4: Verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -q
```

Expected before implementation: FAIL because the script still always force-recreates `coke-web`, has no deploy tier classifier, and writes no `.deployed-sha` marker.

Red evidence: 5 failed, 8 passed. The failures were the missing `.deployed-sha`
tracking, missing backend/web service arrays, missing no-op branch, and missing
backend/web rsync split.

## Task 3: Differential Deploy Implementation

**Files:**
- Modify: `scripts/deploy-compose-to-gcp.sh`

- [x] **Step 1: Add local SHA and remote marker discovery**

Compute `LOCAL_SHA="$(git rev-parse HEAD)"`, read `${REMOTE_ROOT}/.deployed-sha` through SSH before rsync, and fallback to `DEPLOY_TIER=full` when the marker is missing or invalid.

- [x] **Step 2: Classify changed paths**

Use `git diff --name-only "$LAST_DEPLOYED_SHA" "$LOCAL_SHA"` and classify:

```text
web/ changed -> DEPLOY_TIER=web
backend/deploy changed -> DEPLOY_TIER=backend
no relevant changed paths -> DEPLOY_TIER=none
unknown mixed or missing marker -> DEPLOY_TIER=full
```

Backend/deploy paths are `coke/`, `migrations/`, `requirements.txt`, `alembic.ini`, `scripts/`, `docker-compose*`, `Dockerfile`, `.dockerignore`, and `deploy/`.

- [x] **Step 3: Make rsync source selection match the tier**

For backend-only deploys, rsync backend/deploy sources and skip `web/`. For web/full deploys, include `web/`. Keep excludes for `.git`, `.venv`, `.worktrees`, `.env`, `__pycache__`, `node_modules`, `.pnpm-store`, and `.next`.

- [x] **Step 4: Recreate only affected app service containers**

Run Alembic upgrade/check after rsync. Then recreate backend services with:

```bash
docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml up -d --build --no-deps --force-recreate coke-api coke-worker coke-scheduler coke-outbox-relay
```

Only when `DEPLOY_TIER` is `web` or `full`, also recreate `coke-web`.

- [x] **Step 5: Keep health verification and write deployed marker**

Verify `/healthz` and `/auth/login`; write `LOCAL_SHA` to `${REMOTE_ROOT}/.deployed-sha` only after the deploy and probes succeed.

## Task 4: Local Verification And Commit

- [x] **Step 1: Verify focused deploy tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -q
```

Evidence: 13 passed.

- [x] **Step 2: Verify full Coke unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Evidence: 547 passed in 18.10s.

Surface evidence: `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`
passed with 547 tests in 17.32s and `zsh scripts/check` ending `check passed`.

- [ ] **Step 3: Commit script, tests, and plan progress**

Run:

```bash
git add scripts/deploy-compose-to-gcp.sh tests/unit/coke/deploy/test_clean_compose_deploy_contract.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-differential-deploy.md
git commit -m "fix: deploy clean coke stack differentially"
```

## Task 5: Verification Deploy To gcp-coke

- [ ] **Step 1: Run one real deploy from current `main`**

Run from the worktree root and measure wall-clock time:

```bash
time scripts/deploy-compose-to-gcp.sh
```

Expected for this change set: backend-only differential deploy, `coke-web` left running, no `pnpm install` or `pnpm build` in `coke-web` logs for the deploy window.

- [ ] **Step 2: Verify live backend, web, and sessions**

Verify `/healthz=200`, `/auth/login=200`, login API 200, backend containers restart-stable, both WeChat channels still `connected`, connector `session_count=2`, and worker logs contain no `unsupported_worker_topic`.

- [ ] **Step 3: Verify deployed marker**

Read `${REMOTE_ROOT}/.deployed-sha` and confirm it equals the committed local `HEAD`.

- [ ] **Step 4: Mark plan complete after evidence**

Update this plan with the exact passing test summaries, wall-clock time, deployed marker SHA, and set `Plan Status: complete`.

- [ ] **Step 5: Commit plan closeout**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-differential-deploy.md
git commit -m "docs: record differential deploy verification"
```
