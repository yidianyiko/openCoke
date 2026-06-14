# DeepSeek Detector Express Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch only the validated low-risk Coke text roles (`detector` and `express`) to DeepSeek V4 Flash while keeping `planner` and `interaction` on GLM-5.1.

**Architecture:** Add per-role provider selection to the existing `ZAILLMConfig` instead of replacing the whole text stack. `interaction` and `planner` keep Z.AI GLM-5.1 defaults; `detector` and `express` may independently use DeepSeek credentials, base URL, and model id through env config.

**Tech Stack:** Python dataclasses, Agno `OpenAILike`, pytest, production deploy shell contract, GCP clean compose deploy.

---

### Task 1: Live Provider Guard

**Files:**
- Create evidence: `artifacts/evidence/deepseek-model-bakeoff/<timestamp>-detector-express-switch-guard.json`
- Modify: `docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md`

- [x] **Step 1: Run real DeepSeek and GLM detector/express calls**

Run an ad hoc Python probe using local `ZAI_API_KEY` and `DEEPSEEK_API_KEY`. Detector cases must include absolute reminders, relative reminders, vague time, recurrence, duration, and no-reminder input. Express cases must include created reminders, list replies, needs-input, conflict, and first-use no-action.

- [x] **Step 2: Accept or stop**

Accept the switch only if DeepSeek V4 Flash has no DeepSeek-specific failures versus GLM-5.1 on the probe and Express returns valid JSON reply segments for every case. If the detector has failures shared by GLM and DeepSeek, record them as existing prompt/corpus gaps rather than DeepSeek blockers.

### Task 2: Configuration Tests

**Files:**
- Modify: `tests/unit/coke/llm/test_config.py`
- Modify: `tests/unit/coke/test_backend_foundation.py`

- [x] **Step 1: Write failing LLM config tests**

Add assertions that `ZAILLMConfig.from_env` reads `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `COKE_DETECTOR_PROVIDER`, `COKE_EXPRESS_PROVIDER`, and `COKE_EXPRESS_MODEL`, and that `create_detector_model()` plus `create_express_model()` use the DeepSeek key/base/model only for the selected roles.

- [x] **Step 2: Write failing Settings tests**

Add production validation that `DEEPSEEK_API_KEY` is required when `COKE_DETECTOR_PROVIDER=deepseek` or `COKE_EXPRESS_PROVIDER=deepseek`, while fake LLM mode still starts without provider keys.

- [x] **Step 3: Run red tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py -q
```

Expected: FAIL because the DeepSeek fields and `create_express_model()` do not exist yet.

### Task 3: Runtime Wiring

**Files:**
- Modify: `coke/llm/config.py`
- Modify: `coke/config.py`
- Modify: `coke/composition.py`
- Modify: `coke/turn/inbound/express.py`
- Modify: `tests/integration/coke/test_runtime_wiring.py`

- [x] **Step 1: Implement per-role provider selection**

Keep defaults as Z.AI GLM-5.1. Add DeepSeek constants and validated provider fields. `create_interaction_model()` and `create_planner_model()` must continue using Z.AI. `create_detector_model()` and `create_express_model()` must use their configured provider credentials.

- [x] **Step 2: Wire Express to its own model role**

Change `ExpressAgent.from_config()` to call `config.create_express_model()` instead of `config.create_interaction_model()`.

- [x] **Step 3: Run wiring tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py -q
```

Expected: PASS, with detector and express using DeepSeek when configured and planner/interaction still using Z.AI.

### Task 4: Deploy Contract

**Files:**
- Modify: `scripts/deploy-compose-to-gcp.sh`
- Modify: `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`

- [x] **Step 1: Write deploy contract expectations**

Assert the deploy script reads and writes `DEEPSEEK_API_KEY`, requires it for the DeepSeek detector/express rollout, and writes:

```dotenv
COKE_DETECTOR_PROVIDER=deepseek
COKE_DETECTOR_MODEL=deepseek-v4-flash
COKE_EXPRESS_PROVIDER=deepseek
COKE_EXPRESS_MODEL=deepseek-v4-flash
```

- [x] **Step 2: Implement deploy env rewrite**

Preserve existing clean/old env values where needed, but for this rollout write detector and express provider/model env values explicitly to DeepSeek V4 Flash.

- [x] **Step 3: Run deploy contract test**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -q
```

Expected: PASS.

### Task 5: Verification, Commit, Deploy

**Files:**
- Modify: `docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md`
- Possibly create evidence under: `artifacts/evidence/deepseek-model-bakeoff/`

- [ ] **Step 1: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [ ] **Step 2: Run selected local verification**

At minimum run the changed unit/integration tests and the surface suggested by the routing output.

- [ ] **Step 3: Commit**

Commit code, tests, docs, and forced evidence artifacts needed for the record.

- [ ] **Step 4: Seed server DeepSeek key if missing**

Check the clean server env without printing secrets. If `DEEPSEEK_API_KEY` is missing, copy the local key into the clean env with restrictive permissions.

- [ ] **Step 5: Deploy and smoke**

Run the clean compose deploy script, then verify production env role selection, container health, `/healthz`, and a runtime config smoke that proves detector and express use DeepSeek V4 Flash while planner and interaction still use GLM-5.1.
