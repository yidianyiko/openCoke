# Old Main To OpenCoke Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `openCoke` up to the old repository's `main` code level while preserving the open-source sanitized boundary.

**Architecture:** Start from the existing `chore/opencoke-migration` branch, compare it against the old repository `main`, and import only source-controlled code, tests, docs, and submodule wiring that belong in the public repository. Keep `openCoke` governance files, exclude runtime artifacts and private deployment material, and re-scan imported content for secrets or signed URLs before final verification.

**Tech Stack:** Git worktree workflow, Python 3.12, pytest, ripgrep, Git submodules

---

### Task 1: Classify Remaining `main`-Only Changes

**Files:**
- Modify: `docs/superpowers/plans/2026-03-31-old-main-to-opencoke-sync.md`
- Inspect: `.gitmodules`
- Inspect: `api/app.py`
- Inspect: `connector/ecloud/ecloud_api.py`
- Inspect: `conf/config.json`

- [ ] **Step 1: Capture the remaining diff from old `main`**

Run:

```bash
git diff --name-status chore/opencoke-migration..main
```

Expected: Shows `api/`, `third_party/openclaw`, `.gitmodules`, Gateway runner changes, and excluded artifact candidates like `data/`, `logs/`, `.vscode/`, `scripts/deploy-to-gcp.sh`.

- [ ] **Step 2: Split files into migrate vs exclude buckets**

Use this target split:

```text
Migrate:
- .gitmodules
- agent/requirements.txt
- agent/runner/agent_handler.py
- agent/runner/agent_runner.py
- agent/runner/agent_start.sh
- agent/runner/message_processor.py
- agent/util/message_util.py
- api/**
- conf/config.json
- connector/adapters/**
- connector/ecloud/ecloud_api.py
- dao/conversation_dao.py
- entity/message.py
- requirements.txt
- tests/unit/api/**
- tests/unit/agent/test_agent_handler.py
- tests/unit/connector/test_stream_publish.py
- tests/unit/dao/test_conversation_dao_gateway.py
- tests/unit/runner/test_agent_runner_gateway.py
- tests/unit/runner/test_message_acquirer_gateway.py
- tests/unit/test_character_alias_migration.py
- tests/unit/test_timezone_tools.py
- third_party/openclaw

Exclude:
- .DS_Store
- .vscode/settings.json
- data/**
- logs/**
- scripts/deploy-to-gcp.sh
```

- [ ] **Step 3: Confirm sanitized files stay public-safe**

Run:

```bash
git diff chore/opencoke-migration..main -- connector/ecloud/ecloud_api.py conf/config.json api app.py
```

Expected: No hard-coded secrets are required; any example values remain generic or env-backed.

### Task 2: Apply Old `main` Code Delta

**Files:**
- Modify: `.gitignore`
- Modify: `agent/runner/agent_handler.py`
- Modify: `agent/runner/agent_runner.py`
- Modify: `agent/runner/agent_start.sh`
- Modify: `agent/runner/message_processor.py`
- Modify: `agent/util/message_util.py`
- Create: `api/__init__.py`
- Create: `api/app.py`
- Create: `api/config.py`
- Create: `api/delivery.py`
- Create: `api/ingest.py`
- Create: `api/openclaw_client.py`
- Create: `api/payment_webhooks.py`
- Create: `api/schema.py`
- Modify: `conf/config.json`
- Modify: `connector/adapters/__init__.py`
- Modify: `connector/adapters/ecloud/__init__.py`
- Modify: `connector/ecloud/ecloud_api.py`
- Delete: `connector/ecloud/ecloud_input.py`
- Delete: `connector/ecloud/ecloud_output.py`
- Delete: `connector/ecloud/ecloud_start.sh`
- Modify: `dao/conversation_dao.py`
- Modify: `entity/message.py`
- Modify: `requirements.txt`
- Create: `.gitmodules`
- Create: `third_party/openclaw`

- [ ] **Step 1: Apply the old `main` versions for migrate-listed files**

Run:

```bash
git checkout main -- \
  .gitmodules \
  agent/requirements.txt \
  agent/runner/agent_handler.py \
  agent/runner/agent_runner.py \
  agent/runner/agent_start.sh \
  agent/runner/message_processor.py \
  agent/util/message_util.py \
  api \
  conf/config.json \
  connector/adapters/__init__.py \
  connector/adapters/ecloud/__init__.py \
  connector/ecloud/ecloud_api.py \
  connector/ecloud/ecloud_input.py \
  connector/ecloud/ecloud_output.py \
  connector/ecloud/ecloud_start.sh \
  dao/conversation_dao.py \
  entity/message.py \
  requirements.txt \
  third_party/openclaw
```

Expected: Working tree now reflects old `main` for Gateway/OpenClaw code paths.

- [ ] **Step 2: Remove files that old `main` deleted**

Run:

```bash
git rm -f connector/ecloud/ecloud_input.py connector/ecloud/ecloud_output.py connector/ecloud/ecloud_start.sh
```

Expected: Legacy Flask Ecloud webhook files are removed from the migration branch.

- [ ] **Step 3: Keep `openCoke`-specific governance files**

Run:

```bash
git checkout origin/main -- .github/dependabot.yml CONTRIBUTING.md SECURITY.md
```

Expected: Public repo governance files remain present after syncing code from old `main`.

### Task 3: Apply Tests Before Final Fixups

**Files:**
- Modify: `tests/unit/agent/test_agent_handler.py`
- Create: `tests/unit/api/test_app.py`
- Create: `tests/unit/api/test_config.py`
- Create: `tests/unit/api/test_delivery.py`
- Create: `tests/unit/api/test_ingest.py`
- Create: `tests/unit/api/test_openclaw_client.py`
- Create: `tests/unit/api/test_payment_webhooks.py`
- Create: `tests/unit/api/test_schema.py`
- Modify: `tests/unit/connector/test_stream_publish.py`
- Create: `tests/unit/dao/test_conversation_dao_gateway.py`
- Create: `tests/unit/runner/test_agent_runner_gateway.py`
- Create: `tests/unit/runner/test_message_acquirer_gateway.py`
- Modify: `tests/unit/test_character_alias_migration.py`
- Modify: `tests/unit/test_timezone_tools.py`

- [ ] **Step 1: Restore test files from old `main`**

Run:

```bash
git checkout main -- \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/api \
  tests/unit/connector/test_stream_publish.py \
  tests/unit/dao/test_conversation_dao_gateway.py \
  tests/unit/runner/test_agent_runner_gateway.py \
  tests/unit/runner/test_message_acquirer_gateway.py \
  tests/unit/test_character_alias_migration.py \
  tests/unit/test_timezone_tools.py
```

Expected: Gateway/API tests are present before behavior-level verification.

- [ ] **Step 2: Run a focused failing test slice**

Run:

```bash
python3 -m pytest -q \
  tests/unit/api/test_config.py \
  tests/unit/api/test_schema.py \
  tests/unit/api/test_ingest.py \
  tests/unit/runner/test_agent_runner_gateway.py
```

Expected: If anything is inconsistent after sync, at least one test fails with a concrete import or contract error that guides the fix.

- [ ] **Step 3: Fix only the failing public-safe integration points**

Allowed fix targets:

```text
- openCoke-specific keepers accidentally overwritten
- secret/env handling regressions
- test isolation regressions introduced by the sync
- submodule/config path mismatches
```

### Task 4: Re-Sanitize and Verify

**Files:**
- Modify: `.gitignore`
- Inspect: `.gitmodules`
- Inspect: `api/**`
- Inspect: `connector/ecloud/ecloud_api.py`
- Inspect: `conf/config.json`

- [ ] **Step 1: Restore the public-safe ignore policy**

Check these lines remain in `.gitignore`:

```gitignore
.env
.env.*
*.pem
*.key
*.p12
*.pfx
*.db
*.sqlite
logs/
data/
.worktrees/
.cache_ggshield
.DS_Store
```

- [ ] **Step 2: Scan staged content for obvious secret patterns**

Run:

```bash
git diff origin/main -- . ':(exclude)data/**' ':(exclude)logs/**' ':(exclude).vscode/**' ':(exclude)scripts/deploy-to-gcp.sh' | \
rg '^\+.*(x-oss-|aliyuncs\.com|oss-cn-|LTAI|AKIA|ASIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|https?://[^[:space:]]*\?[^[:space:]]*=)'
```

Expected: No matches.

- [ ] **Step 3: Run final focused verification**

Run:

```bash
python3 -m pytest -q \
  tests/unit/api/test_app.py \
  tests/unit/api/test_config.py \
  tests/unit/api/test_delivery.py \
  tests/unit/api/test_ingest.py \
  tests/unit/api/test_openclaw_client.py \
  tests/unit/api/test_payment_webhooks.py \
  tests/unit/api/test_schema.py \
  tests/unit/runner/test_agent_runner_gateway.py \
  tests/unit/runner/test_message_acquirer_gateway.py \
  tests/unit/connector/test_stream_publish.py \
  tests/unit/agent/test_agent_handler.py
```

Expected: PASS with 0 failures.

- [ ] **Step 4: Commit**

Run:

```bash
git add -A
git commit -m "feat(gateway): sync old main into openCoke baseline"
```

Expected: One new commit on `chore/opencoke-migration` that brings the branch up to the old `main` code level while preserving open-source sanitization.
