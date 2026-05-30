# Coke Clean Rebuild Runtime Readiness RR7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the clean Coke stack deployable to `gcp-coke` as a non-disruptive Stage-1 compose project under `/home/whoami/coke-clean`.

**Architecture:** The deploy path creates a separate clean compose project named `coke-clean` with fresh Postgres and Redis containers, localhost-only free host ports, and no dependency on the deleted Gateway submodule. The old `/home/whoami/coke` production stack remains untouched; the only remote action is creating/updating `/home/whoami/coke-clean`, writing a clean `.env`, starting `docker compose -p coke-clean`, running Alembic, and smoking the clean API/webhook path.

**Tech Stack:** Bash, rsync, Docker Compose, Flask/Gunicorn, Alembic, Postgres 17, Redis 7, pytest, PyYAML.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Source Specs:**
- `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

## File Structure

- Create `scripts/deploy-compose-to-gcp.sh`: clean-stack deploy command with `--dry-run`, rsync allowlist, clean env generation from the old stack `.env`, compose startup, one-shot Alembic, and `/healthz` check.
- Create `docker-compose.clean.yml`: non-disruptive compose override with localhost-only free ports, distinct clean volume names, host-gateway access for Evolution, and clean runtime environment.
- Create `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`: contract tests for the clean override and deploy script so legacy Gateway/submodule behavior cannot re-enter this path.
- Modify `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr7.md`: mark checklist progress and set `Plan Status: complete` only after verification passes.

### Task 1: Write Deploy Contract Tests

**Files:**
- Create: `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`
- Read: `docker-compose.prod.yml`
- Read: `scripts/deploy-compose-to-gcp.sh`

- [x] **Step 1: Write failing tests for clean compose override and deploy script**

Create tests that assert:
- `docker-compose.clean.yml` binds Postgres to `127.0.0.1:${COKE_CLEAN_POSTGRES_PORT:-55432}:5432`, Redis to `127.0.0.1:${COKE_CLEAN_REDIS_PORT:-56379}:6379`, API to `127.0.0.1:${COKE_CLEAN_API_PORT:-8000}:8000`, and web to `127.0.0.1:${COKE_CLEAN_WEB_PORT:-4042}:4040`.
- clean volumes are named with the `coke_clean_` prefix.
- api/worker/scheduler/outbox-relay use compose-internal `DATABASE_URL`, `REDIS_URL`, `APP_ENV=production`, `AGNO_TELEMETRY=false`, and `COKE_AGNO_CREATE_SCHEMA=1`.
- api and worker include `extra_hosts: ["host.docker.internal:host-gateway"]`.
- the deploy script contains `docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml up -d --build`, `alembic upgrade head`, rsync includes clean stack paths, a `--dry-run` branch, and no `gateway`, `pymongo`, `memo_runtime`, or submodule sync terms.

- [x] **Step 2: Run RED verification**

Run:
```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Expected: FAIL because `docker-compose.clean.yml`, `tests/unit/coke/deploy/`, and `scripts/deploy-compose-to-gcp.sh` do not yet exist.

### Task 2: Implement Clean Compose Override And Deploy Script

**Files:**
- Create: `docker-compose.clean.yml`
- Create: `scripts/deploy-compose-to-gcp.sh`

- [x] **Step 3: Add `docker-compose.clean.yml`**

Implement the override with:
- localhost-only host ports defaulting to `8000`, `4042`, `55432`, and `56379`;
- distinct `coke_clean_postgres_data` and `coke_clean_redis_data` volume names;
- shared clean runtime env for api/worker/scheduler/outbox-relay;
- `extra_hosts` on `coke-api` and `coke-worker` for `host.docker.internal`;
- no `COKE_LLM_FAKE`.

- [x] **Step 4: Add `scripts/deploy-compose-to-gcp.sh`**

Implement:
- env defaults: `REMOTE_HOST=gcp-coke`, `REMOTE_ROOT=/home/whoami/coke-clean`, `PROJECT_NAME=coke-clean`, `COKE_CLEAN_API_PORT=8000`, `COKE_CLEAN_WEB_PORT=4042`, `COKE_CLEAN_POSTGRES_PORT=55432`, `COKE_CLEAN_REDIS_PORT=56379`;
- `--dry-run` support that prints/executes rsync in dry-run mode and does not run remote compose;
- rsync of `coke/`, `web/`, `migrations/`, `deploy/`, `scripts/`, `docker-compose.prod.yml`, `docker-compose.clean.yml`, `Dockerfile`, `requirements.txt`, and `alembic.ini`, excluding `.git`, `.venv`, `.worktrees`, `.env`, `__pycache__`, and `node_modules`;
- remote `.env` generation in `/home/whoami/coke-clean/.env` from old `/home/whoami/coke/.env`, copying only required secrets and mapping Evolution URL host `127.0.0.1`/`localhost` to `host.docker.internal`;
- `docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml up -d --build`;
- one-shot `docker compose ... run --rm coke-migrate alembic upgrade head`;
- `curl -fsS "http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz"`.

- [x] **Step 5: Run GREEN verification for deploy contract**

Run:
```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Expected: all tests pass.

### Task 3: Local Guardrails And Commit

**Files:**
- `scripts/deploy-compose-to-gcp.sh`
- `docker-compose.clean.yml`
- `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`
- `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr7.md`

- [x] **Step 6: Run diff-aware verification routing**

Run:
```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: suggestions include deploy/repo checks; review-trigger may report deployment risk but must not block the commit.

- [x] **Step 7: Run required local checks**

Run:
```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
zsh scripts/check
```

Expected: both commands exit 0.

- [x] **Step 8: Commit local deploy assets**

Run:
```bash
git add docker-compose.clean.yml scripts/deploy-compose-to-gcp.sh tests/unit/coke/deploy/test_clean_compose_deploy_contract.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr7.md
git commit -m "deploy clean coke stack non-disruptively"
```

Expected: one coherent commit on `main`.

### Task 4: Non-Disruptive Deploy And On-Box Smoke

**Files:**
- No committed file changes expected.
- Remote dir: `/home/whoami/coke-clean`

- [x] **Step 9: Run dry-run locally**

Run:
```bash
REMOTE_HOST=gcp-coke REMOTE_ROOT=/home/whoami/coke-clean PROJECT_NAME=coke-clean scripts/deploy-compose-to-gcp.sh --dry-run
```

Expected: rsync dry-run output only; no compose actions.

- [x] **Step 10: Run Stage-1 clean deploy**

Run:
```bash
REMOTE_HOST=gcp-coke REMOTE_ROOT=/home/whoami/coke-clean PROJECT_NAME=coke-clean COKE_CLEAN_API_PORT=8000 COKE_CLEAN_WEB_PORT=4042 COKE_CLEAN_POSTGRES_PORT=55432 COKE_CLEAN_REDIS_PORT=56379 scripts/deploy-compose-to-gcp.sh
```

Expected: clean compose project starts under `/home/whoami/coke-clean`; old `/home/whoami/coke` stack is not stopped or modified.

- [x] **Step 11: Verify clean health and schema on the box**

Run on `gcp-coke`:
```bash
curl -fsS http://127.0.0.1:8000/healthz
cd /home/whoami/coke-clean
docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml exec -T postgres psql -U coke -d coke -c "select count(*) as public_table_count from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE';"
```

Expected: `{"ok":true}` and `public_table_count >= 28`.

- [x] **Step 12: Run localhost webhook smoke**

POST a synthetic Evolution `messages.upsert` payload to `http://127.0.0.1:8000/webhooks/whatsapp/evolution` with text `提醒我明天早上9点跑步`, wait for worker processing, then query clean Postgres for `account.origin='messaging_first'`, conversation/message/turn rows, and a reminder row. Evolution send failure for the synthetic sender is acceptable; DB rows are the pass bar.

- [x] **Step 13: Confirm old stack remains up**

Run on `gcp-coke`:
```bash
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | egrep 'coke-bridge|coke-gateway|coke-agent|coke-mongo|coke-postgres|coke-redis|evolution-'
ss -ltnp | egrep ':(4040|4041|8090|8081)\b'
```

Expected: old containers and old ports remain present; no `docker compose down` was run against the old project.

- [x] **Step 14: Mark plan complete and commit plan status update**

After local and remote verification pass, set `Plan Status: complete`, tick all checklist boxes, and commit the plan status update.
