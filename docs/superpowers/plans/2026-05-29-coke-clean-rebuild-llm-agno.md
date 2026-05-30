# Coke Clean Rebuild LLM Agno Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the Turn LLM ports to SiliconFlow through Agno without changing the existing Turn contracts or composition wiring.

**Architecture:** This slice creates a new `coke.llm` package that adapts SiliconFlow/OpenAI-compatible model access to the existing `InteractionAgent`, `SemanticInterpreter`, and `ReminderDetectorPort` protocols. Agno remains the agent-loop substrate for the Interaction Agent, while interpreter and detector are utility LLM calls with strict JSON parsing and trusted-or-invalid behavior. The runner remains responsible for first-answer output validation, so malformed model output is returned as-is for the runner to mark failed.

**Tech Stack:** Python 3.12, Agno 2.5 `Agent`, `OpenAILike`, Agno Postgres DB hooks, dataclasses, pytest fakes, no live network in unit tests.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Freshness Check:** Checked against master plan Task 7 and architecture-watch notes, runtime-readiness RR5, requirements §5.4/§5.8/§5.9/§5.11, target architecture §3.7/§4/§8/§9/§11, current `coke/schema.py`, and current Turn port definitions.
**Verification Note:** `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed with `331 passed in 4.79s`; routed `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed with `331 passed in 4.81s` plus `scripts/check` `check passed`.

**Source Specs:**
- `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`
- `docs/superpowers/plans/2026-05-30-coke-runtime-readiness.md`
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

## File Structure

- Create `coke/llm/__init__.py`: exports the public RR5 implementations and config helpers.
- Create `coke/llm/config.py`: reads SiliconFlow env (`SiliconFlow_API_KEY`, model overrides, optional Agno DB URL) and builds `OpenAILike` instances with base URL `https://api.siliconflow.cn/v1`.
- Create `coke/llm/agno_interaction_agent.py`: implements `InteractionAgent` using Agno `Agent`, Agno tools mapped from `AgentToolPorts`, Postgres-backed Agno session/history/memory when configured, and no output repair.
- Create `coke/llm/semantic_interpreter.py`: implements `SemanticInterpreter` as one structured LLM classification pass.
- Create `coke/llm/reminder_detector.py`: implements `ReminderDetectorPort` as one structured GLM-5.1 extraction pass with no regex recovery.
- Create `tests/unit/coke/llm/test_config.py`: asserts env/config/model wiring without network.
- Create `tests/unit/coke/llm/test_interaction_agent.py`: asserts Agno response mapping, protocol-invalid passthrough, tool mapping, memory switch parameters, and async completion.
- Create `tests/unit/coke/llm/test_semantic_interpreter.py`: asserts structured decision mapping and invalid output failure.
- Create `tests/unit/coke/llm/test_reminder_detector.py`: asserts structured reminder-field mapping and invalid output failure.

## Task 1: Red Tests

**Files:**
- Create: `tests/unit/coke/llm/test_config.py`
- Create: `tests/unit/coke/llm/test_interaction_agent.py`
- Create: `tests/unit/coke/llm/test_semantic_interpreter.py`
- Create: `tests/unit/coke/llm/test_reminder_detector.py`

- [x] **Step 1: Write config tests**

Assert `SiliconFlow_API_KEY`, `COKE_INTERACTION_MODEL`, `COKE_INTERPRETER_MODEL`, and `COKE_DETECTOR_MODEL` map to a config object and that `OpenAILike` receives the SiliconFlow base URL and selected model id.

- [x] **Step 2: Write interaction-agent tests**

Use fake Agno agent/model factories. Assert a valid model response returns `AgentResult.completed({"type": "reply", "segments": [...]})`, malformed response is passed through without replacement prose, tool ports become callable Agno tools that call `StateChangingToolPort.execute(command, guard)`, and memory-enabled/disabled turns set Agno memory flags without auto-extraction.

- [x] **Step 3: Write interpreter tests**

Use a fake JSON client. Assert one valid classification maps to `SemanticDecision(reply_necessity, intent_family, language_hint)` and invalid JSON/invalid enums raise a runtime error instead of keyword fallback.

- [x] **Step 4: Write detector tests**

Use a fake JSON client. Assert a valid GLM-5.1 extraction maps ISO datetime, recurrence rule, duration, and kind to `DetectedReminderFields`; invalid JSON/invalid enums raise a runtime error without regex recovery.

- [x] **Step 5: Run red tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm -v
```

Expected: FAIL because `coke.llm` does not exist yet.

## Task 2: Implementation

**Files:**
- Create: `coke/llm/__init__.py`
- Create: `coke/llm/config.py`
- Create: `coke/llm/agno_interaction_agent.py`
- Create: `coke/llm/semantic_interpreter.py`
- Create: `coke/llm/reminder_detector.py`

- [x] **Step 1: Implement config**

Read env without secrets in code. Defaults: base URL `https://api.siliconflow.cn/v1`, interaction model `zai-org/GLM-5.1`, interpreter model `zai-org/GLM-5.1`, detector model `zai-org/GLM-5.1`, with `COKE_*_MODEL` overrides and required `SiliconFlow_API_KEY`.

- [x] **Step 2: Implement `AgnoInteractionAgent`**

Instantiate Agno `Agent` with `OpenAILike`, per-request system framing from trusted facts/context, tool wrappers around injected ports, `add_session_state_to_context=False`, Postgres Agno DB/memory hooks when configured, and Agno auto-extraction off. Return parsed model output as `AgentResult.completed(output)` or `AgentResult.timeout(task_id)`; never rewrite invalid output.

- [x] **Step 3: Implement `SiliconFlowSemanticInterpreter`**

Send one structured JSON classification prompt through the configured model client. Accept only `reply_needed`/`intentional_no_reply` and the declared intent-family enum; return `SemanticDecision`; raise `LLMOutputError` on malformed output.

- [x] **Step 4: Implement `SiliconFlowReminderDetector`**

Send one structured JSON extraction prompt through the configured detector model. Parse only trusted fields into `DetectedReminderFields`; parse ISO datetimes; raise `LLMOutputError` on malformed output.

- [x] **Step 5: Run focused tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm -v
```

Expected: all `tests/unit/coke/llm` tests pass.

## Task 3: Full Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-llm-agno.md`
- Add/modify: `coke/llm/`, `tests/unit/coke/llm/`

- [x] **Step 1: Run required backend unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all backend unit tests pass.

- [x] **Step 2: Update plan status**

Set `Plan Status` to `complete`, update verification note with the exact command and pass summary, and check off completed steps.

- [x] **Step 3: Commit**

Run:

```bash
git add coke/llm tests/unit/coke/llm docs/superpowers/plans/2026-05-29-coke-clean-rebuild-llm-agno.md
git commit -m "feat: bind turn llm ports to siliconflow agno"
```

Expected: one coherent RR5 commit on the current branch.
