# Z.AI Official GLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Coke's text GLM roles to official Z.AI while leaving media models on SiliconFlow.

**Architecture:** Replace the single SiliconFlow-owned LLM config with `ZAILLMConfig` for interpreter, interaction, and detector models, plus `SiliconFlowMediaConfig` for ASR and vision text. Wire both through `Settings`, composition, and deploy env generation so production requires Z.AI for text and SiliconFlow only for configured media.

**Tech Stack:** Python 3.12, Agno `OpenAILike`, pytest, zsh deploy guard scripts, Docker Compose env files.

---

### Task 1: Provider Config Tests

**Files:**
- Modify: `tests/unit/coke/llm/test_config.py`
- Modify: `coke/llm/config.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `ZAILLMConfig`, `SiliconFlowMediaConfig`, `ZAI_BASE_URL`,
`SILICONFLOW_BASE_URL`, and the default model constants. Assert:

- `ZAILLMConfig.from_env({"ZAI_API_KEY": "zai-key"})` defaults text models to
  `glm-5.1`.
- `create_interaction_model()`, `create_interpreter_model()`, and
  `create_detector_model()` use the Z.AI key/base URL and
  `extra_body == {"thinking": {"type": "disabled"}}`.
- `ZAILLMConfig.from_env({})` raises on `ZAI_API_KEY`.
- `SiliconFlowMediaConfig.from_env({"SiliconFlow_API_KEY": "sf-key"})` keeps
  the existing media defaults.
- `SiliconFlowMediaConfig.from_env({})` raises on `SiliconFlow_API_KEY`.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py -v
```

Expected: FAIL because the new config classes and Z.AI constants do not exist.

- [ ] **Step 3: Implement config classes**

Update `coke/llm/config.py`:

- Add `ZAI_BASE_URL = "https://api.z.ai/api/paas/v4/"`.
- Change text model defaults to `glm-5.1`.
- Add `ZAILLMConfig` with text model fields and `create_*_model()` methods.
- Add `SiliconFlowMediaConfig` with media fields.
- Keep `_positive_float`, `_optional_model`, and Agno database helpers shared.
- Use `extra_body={"thinking": {"type": "disabled"}}` for all text GLM roles.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py -v
```

Expected: PASS.

### Task 2: Settings And Composition

**Files:**
- Modify: `tests/unit/coke/test_backend_foundation.py`
- Modify: `tests/integration/coke/test_runtime_wiring.py`
- Modify: `coke/config.py`
- Modify: `coke/composition.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `coke/llm/__init__.py`

- [ ] **Step 1: Write failing tests**

Update settings tests to use `ZAI_API_KEY` for real text LLM and
`SiliconFlow_API_KEY` for media. Add assertions for:

- `settings.zai_api_key == "zai-key"`.
- `settings.zai_base_url == ZAI_BASE_URL`.
- production real LLM raises on missing `ZAI_API_KEY`.
- media settings still read `SiliconFlow_API_KEY` and media model overrides.

Update runtime wiring so a real runtime can be built with both keys and distinct
provider configs.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py -v
```

Expected: FAIL because `Settings` has no Z.AI fields and composition still
requires SiliconFlow for text LLM.

- [ ] **Step 3: Implement settings and composition**

Update `Settings` with `zai_api_key`, `zai_base_url`, and existing text model
fields sourced from Z.AI defaults. Keep `siliconflow_api_key` and
`siliconflow_base_url` for media. In `_llm_from_settings()`, build
`ZAILLMConfig` for text components and `SiliconFlowMediaConfig` only for media
resolver construction.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py -v
```

Expected: PASS.

### Task 3: Deploy Contract

**Files:**
- Modify: `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`
- Modify: `scripts/deploy-compose-to-gcp.sh`

- [ ] **Step 1: Write failing deploy contract test**

Assert the deploy script:

- reads `ZAI_API_KEY`;
- requires `ZAI_API_KEY`;
- writes `ZAI_API_KEY=...` into the clean env;
- does not require `SiliconFlow_API_KEY` as the primary LLM key.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Expected: FAIL because the deploy script still requires `SiliconFlow_API_KEY`
for LLM startup.

- [ ] **Step 3: Implement deploy script changes**

Read `ZAI_API_KEY` from the current clean env or old env. Keep reading
`SiliconFlow_API_KEY`, require it as the media ASR/VLM key while the media
models remain enabled by default, and write both keys into the clean env.
Require `ZAI_API_KEY`, media `SiliconFlow_API_KEY`, Evolution credentials, and
Resend for production.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Expected: PASS.

### Task 4: Routed Verification And Commit

**Files:**
- All modified files.

- [ ] **Step 1: Run targeted LLM/deploy tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Expected: PASS.

- [ ] **Step 2: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and identify any additional required surfaces.

- [ ] **Step 3: Run suggested verification**

Run the highest-signal suggested surface commands for changed Python config,
deploy script, and repo-OS docs. At minimum run:

```bash
zsh scripts/check
```

Expected: PASS, or classify failures before editing.

- [ ] **Step 4: Commit**

Run:

```bash
git status --short
git add coke/ tests/ scripts/deploy-compose-to-gcp.sh docs/superpowers/specs/2026-06-09-zai-official-glm-provider-design.md docs/superpowers/plans/2026-06-09-zai-official-glm-provider.md
git commit -m "feat(llm): route text glm through official zai"
```

Expected: commit succeeds and unrelated untracked files remain untouched.
