# GCP Compose Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `gcp-coke` as a clean, repeatable Docker Compose deployment for Coke and its gateway/bridge stack.

**Architecture:** A single Python image runs the Coke services with command overrides, the existing gateway Dockerfile serves API + exported web, and host Nginx routes public paths to localhost-bound container ports. Remote cleanup removes the old PM2 and ad-hoc runtime state before the new stack is started.

**Tech Stack:** Docker Compose, Python 3.12, Node 22, PostgreSQL, MongoDB, Redis, Nginx, systemd

---

### Task 1: Add Python production container assets

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Add the Python service image build**

Create `Dockerfile` that:

- uses `python:3.12-slim`
- installs `ffmpeg`, `curl`, and certificates
- copies the repo
- installs `requirements.txt`
- sets `PYTHONUNBUFFERED=1`

- [ ] **Step 2: Add the Docker build ignore rules**

Create `.dockerignore` to exclude:

- `.git`
- `.worktrees`
- `.venv`
- `__pycache__`
- `.pytest_cache`
- `logs`
- `data`
- `htmlcov`
- `gateway/node_modules`

- [ ] **Step 3: Build the image locally**

Run: `docker build -t coke-python:test .`

Expected: image builds successfully without copying worktree noise or local virtualenv contents.

### Task 2: Add production compose and server-side templates

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `deploy/config/coke.config.json`
- Create: `deploy/env/coke.env.example`
- Create: `deploy/nginx/coke.conf`
- Create: `deploy/systemd/coke-compose.service`

- [ ] **Step 1: Define the compose stack**

Create `docker-compose.prod.yml` with services:

- `mongo`
- `redis`
- `postgres`
- `coke-agent`
- `coke-bridge`
- `ecloud-input`
- `ecloud-output`
- `gateway`

Use localhost-only port publishing for ingress-facing containers:

- `127.0.0.1:4040:4040`
- `127.0.0.1:4041:4041`
- `127.0.0.1:8090:8090`
- `127.0.0.1:8080:8080`
- `127.0.0.1:8081:8081`

- [ ] **Step 2: Add the production Coke config template**

Create `deploy/config/coke.config.json` with container hostnames:

- Mongo -> `mongo`
- Redis -> `redis`
- gateway internal API -> `http://gateway:4041`

Keep public URLs pointing at `https://coke.keep4oforever.com`.

- [ ] **Step 3: Add the env template**

Create `deploy/env/coke.env.example` listing the required secrets and runtime variables for:

- LLM keys
- Aliyun / Ecloud credentials
- bridge auth secrets
- Stripe / Creem
- WhatsApp Evolution values

- [ ] **Step 4: Add Nginx path routing**

Create `deploy/nginx/coke.conf` that:

- redirects HTTP to HTTPS
- proxies `/` to `127.0.0.1:4040`
- proxies `/api/`, `/auth`, `/gateway`, `/health` to `127.0.0.1:4041`
- proxies exact `/bridge` with websocket headers to `127.0.0.1:4041`
- proxies `/bridge/`, `/user/`, `/bind/` to `127.0.0.1:8090`
- proxies `/message`, `/webhook/creem`, `/webhook/stripe` to `127.0.0.1:8080`
- proxies `/webhook/whatsapp` to `127.0.0.1:8081`

- [ ] **Step 5: Add systemd wrapper**

Create `deploy/systemd/coke-compose.service` that runs:

`docker compose -f /home/whoami/coke/docker-compose.prod.yml up -d`

and stops with:

`docker compose -f /home/whoami/coke/docker-compose.prod.yml down`

### Task 3: Add repeatable deployment tooling and docs

**Files:**
- Create: `scripts/deploy-compose-to-gcp.sh`
- Create: `scripts/reset-gcp-coke.sh`
- Modify: `docs/deploy.md`
- Modify: `README.md`

- [ ] **Step 1: Add the deploy script**

Create `scripts/deploy-compose-to-gcp.sh` that:

- rsyncs tracked deployment files to `gcp-coke:~/coke`
- excludes `.worktrees`, `.venv`, caches, local logs, and `gateway/node_modules`
- optionally restarts the compose stack remotely

- [ ] **Step 2: Add the reset script**

Create `scripts/reset-gcp-coke.sh` that remotely:

- stops PM2
- stops old Docker containers
- removes old deployment directories
- disables host Redis
- truncates oversized MongoDB logs

- [ ] **Step 3: Document the new path**

Update `docs/deploy.md` and `README.md` to describe:

- required env files
- compose startup
- nginx install path
- systemd enable/restart commands

### Task 4: Clean the server and deploy

**Files:**
- Use: remote host `gcp-coke`

- [ ] **Step 1: Sync the new deployment assets**

Run: `./scripts/deploy-compose-to-gcp.sh`

Expected: deployment directory on `gcp-coke` contains the new compose, nginx, env template, and scripts.

- [ ] **Step 2: Reset the old runtime**

Run: `./scripts/reset-gcp-coke.sh`

Expected: no PM2 services, no old Coke containers, reclaimed disk space, and no host Redis port conflict.

- [ ] **Step 3: Install server-side env and config**

Copy:

- `deploy/env/coke.env.example` -> remote `.env`
- `deploy/config/coke.config.json` -> remote `conf/config.json`
- `deploy/nginx/coke.conf` -> `/etc/nginx/sites-available/coke`

Expected: remote files are present and tailored with production secrets.

- [ ] **Step 4: Start the stack**

Run on remote:

`docker compose -f ~/coke/docker-compose.prod.yml up -d --build`

Expected: all core services start.

- [ ] **Step 5: Enable boot-time orchestration**

Run on remote:

- `sudo cp ~/coke/deploy/systemd/coke-compose.service /etc/systemd/system/coke-compose.service`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable coke-compose.service`

Expected: the compose stack is managed by systemd.

### Task 5: Verify ingress and runtime health

**Files:**
- Use: remote host `gcp-coke`

- [ ] **Step 1: Verify compose health**

Run on remote:

- `docker compose -f ~/coke/docker-compose.prod.yml ps`
- `docker compose -f ~/coke/docker-compose.prod.yml logs --tail=100`

- [ ] **Step 2: Verify internal health endpoints**

Run on remote:

- `curl -sS http://127.0.0.1:4041/health`
- `curl -sS http://127.0.0.1:8090/bridge/healthz`

- [ ] **Step 3: Verify public ingress**

Run:

- `curl -k -I https://coke.keep4oforever.com/`
- `curl -k https://coke.keep4oforever.com/api/health`
- `curl -k https://coke.keep4oforever.com/bridge/healthz`

- [ ] **Step 4: Record the outcome**

Document:

- final running services
- public URLs
- remaining known gaps such as optional Evolution bootstrap
