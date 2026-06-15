# DeepSeek Planner Interaction Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Improve real DeepSeek V4 replacement success for Coke Planner, and harden Interaction only where it is safe without enabling false-success state changes.

**Status:** Completed. Final role decision after real API optimization:
`planner=deepseek-v4-pro`, `detector=deepseek-v4-flash`,
`express=deepseek-v4-flash`, and `interaction=glm-5.1`. The decisive Planner
evidence is
`artifacts/evidence/deepseek-model-bakeoff/20260615T024537Z-deepseek-planner-interaction-optimization-r2.json`,
where DeepSeek V4 Pro reached 36/36 with parse 36/36, mean latency 1.362s, and
p95 1.695s. Flash reached 35/36 in the third round but still had a
participant-casing miss, so production deploy uses Pro for Planner.

**Architecture:** Planner remains the semantic Plan stage and gets a provider-selectable OpenAI-compatible model plus a DeepSeek-tuned planner contract. Planner output is still normalized into `TurnPlan` before Execute; unsafe or out-of-contract params fail closed. Interaction remains on GLM unless real API verification proves the current Agno tool loop no longer misses required settings tools.

**Tech Stack:** Python, Agno `OpenAILike`, pytest, DeepSeek chat completions, Coke turn pipeline.

---

## File Structure

- Modify `coke/llm/config.py`: add planner role provider support and select DeepSeek credentials for Planner when configured.
- Modify `coke/config.py`: read `COKE_PLANNER_PROVIDER` and require `DEEPSEEK_API_KEY` when Planner uses DeepSeek in production.
- Modify `coke/composition.py`: pass planner provider into `ZAILLMConfig`.
- Modify `coke/turn/inbound/plan.py`: add provider-aware prompt selection, DeepSeek planner addendum, required/allowed param validation, timezone validation, and precision-key cleanup/rejection.
- Modify `coke/llm/agno_interaction_agent.py`: widen tool `command` annotation to accept DeepSeek's serialized command payloads before normalization.
- Modify tests under `tests/unit/coke/llm/`, `tests/unit/coke/turn/inbound/`, `tests/unit/coke/`, and `tests/integration/coke/`.
- Update `docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md` with final measured outcome and decision.
- Generate new evidence under `artifacts/evidence/deepseek-model-bakeoff/`.

## Task 1: Planner Provider Configuration

**Files:**
- Modify: `coke/llm/config.py`
- Modify: `coke/config.py`
- Modify: `coke/composition.py`
- Test: `tests/unit/coke/llm/test_config.py`
- Test: `tests/unit/coke/test_backend_foundation.py`
- Test: `tests/integration/coke/test_runtime_wiring.py`

- [x] **Step 1: Write failing config tests**

Add tests that prove `COKE_PLANNER_PROVIDER=deepseek` routes only Planner to DeepSeek while Interaction stays on Z.AI:

```python
def test_zai_config_allows_deepseek_planner_role_override():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "zai-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "DEEPSEEK_BASE_URL": "https://deepseek.example",
            "COKE_PLANNER_PROVIDER": "deepseek",
            "COKE_PLANNER_MODEL": "deepseek-v4-flash",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    interaction_model = config.create_interaction_model()
    planner_model = config.create_planner_model()

    assert interaction_model.id == DEFAULT_INTERACTION_MODEL
    assert interaction_model.api_key == "zai-key"
    assert str(interaction_model.base_url) == ZAI_BASE_URL
    assert planner_model.id == "deepseek-v4-flash"
    assert planner_model.api_key == "deepseek-key"
    assert str(planner_model.base_url).rstrip("/") == "https://deepseek.example"
    assert planner_model.timeout == 31.5
    assert planner_model.extra_body == {"thinking": {"type": "disabled"}}
```

Also extend existing production key-requirement parameterization to include `COKE_PLANNER_PROVIDER`.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py::test_zai_config_allows_deepseek_planner_role_override -q
```

Expected: FAIL because `planner_provider` does not exist and Planner still uses Z.AI credentials.

- [x] **Step 3: Implement provider wiring**

Add `DEFAULT_PLANNER_PROVIDER = TEXT_PROVIDER_ZAI`, `planner_provider` fields, env parsing, production key checks, and use `provider=self.planner_provider` in `create_planner_model()`.

- [x] **Step 4: Run focused config tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py::test_settings_from_env_reads_runtime_entrypoint_configuration tests/integration/coke/test_runtime_wiring.py::test_runtime_wires_media_text_resolver_when_media_models_are_configured -q
```

Expected: PASS.

## Task 2: DeepSeek Planner Contract and Validation

**Files:**
- Modify: `coke/turn/inbound/plan.py`
- Modify: `tests/unit/coke/turn/inbound/test_plan.py`
- Modify: `tests/unit/coke/turn/inbound/test_plan_cases.py`

- [x] **Step 1: Write failing planner contract tests**

Add tests for:

```python
def test_planner_rejects_unknown_param_keys() -> None:
    planner = SiliconFlowPlanner(
        StubJSONClient(
            {
                "actions": [
                    {
                        "domain": "reminder",
                        "operation": "list",
                        "params": {"date_phrase": "今天", "invented": "x"},
                    }
                ],
                "reply_necessity": "reply_needed",
            }
        )
    )

    with pytest.raises(PlannerOutputError, match="invalid action.params.invented"):
        planner.plan(_request("看一下今天的提醒"))
```

```python
def test_planner_rejects_precise_shared_reminder_time_keys() -> None:
    planner = SiliconFlowPlanner(
        StubJSONClient(
            {
                "actions": [
                    {
                        "domain": "social_scheduling",
                        "operation": "create_shared_reminder",
                        "params": {
                            "participant": "Amy",
                            "content": "send the deck",
                            "time_phrase": "tomorrow",
                            "local_trigger_at": "2026-06-16T09:00:00",
                        },
                    }
                ],
                "reply_necessity": "reply_needed",
            }
        )
    )

    with pytest.raises(PlannerOutputError, match="precise time"):
        planner.plan(_request("remind Amy tomorrow to send the deck"))
```

```python
def test_planner_rejects_non_iana_timezone_text() -> None:
    planner = SiliconFlowPlanner(
        StubJSONClient(
            {
                "actions": [
                    {
                        "domain": "settings",
                        "operation": "set_timezone",
                        "params": {"timezone_text": "东京"},
                    }
                ],
                "reply_necessity": "reply_needed",
            }
        )
    )

    with pytest.raises(PlannerOutputError, match="invalid timezone_text"):
        planner.plan(_request("把我的时区改成东京"))
```

Update the `zh set timezone` corpus expected value to `{"timezone_text": "Asia/Tokyo"}` because the current product contract requires IANA timezone identifiers.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/inbound/test_plan.py tests/unit/coke/turn/inbound/test_plan_cases.py -q
```

Expected: FAIL on new validation and the timezone corpus until implementation lands.

- [x] **Step 3: Implement contract checks and prompt addendum**

In `plan.py`, use `required_params_by_operation()` and `PARAM_KEY_SCHEMA` to validate required and allowed keys. Add a DeepSeek planner prompt addendum with:

```text
Chinese shared reminder rule:
"提醒我/帮我记得/让我..." is a personal reminder.
"提醒/让/叫/通知 + <other person/friend> + <task>" is a shared reminder.
Example: "明天提醒小王交报告" -> social_scheduling.create_shared_reminder with participant "小王", content "交报告", time_phrase "明天".

Availability date granularity:
For social_scheduling.availability_query, date_phrase is date granularity only:
今天, 明天, 后天, 周一, 6月15日, 2026-06-15.
Do not include period-of-day words such as 上午/下午/晚上 in date_phrase.

Settings timezone:
Convert natural city/place names to IANA timezone IDs.
Example: "把我的时区改成东京" -> timezone_text "Asia/Tokyo".
```

Reject `timezone_text` values that `zoneinfo.ZoneInfo` cannot load. Reject precise time keys such as `trigger_time` and `local_trigger_at` from Planner output.

- [x] **Step 4: Run focused planner tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/inbound/test_plan.py tests/unit/coke/turn/inbound/test_plan_cases.py -q
```

Expected: PASS.

## Task 3: Interaction Tool Argument Hardening

**Files:**
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [x] **Step 1: Write failing interaction annotation test**

Add a unit test proving the generated tool accepts `Any` for `command`, so Agno/Pydantic does not reject serialized JSON command strings before `_normalize_agno_tool_payload()` can parse them:

```python
def test_tool_callable_command_annotation_accepts_serialized_payloads() -> None:
    tool = agno_agent_module._tool_callable(
        "settings",
        RecordingToolPort(),
        _request("以后叫我 Alex"),
    )

    assert tool.__annotations__["command"] == Any | None
```

Also call the tool with `command='{"operation":"update_settings","preference":"concise replies"}'` and assert the recorded command has `operation == "update_settings"`.

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_tool_callable_command_annotation_accepts_serialized_payloads -q
```

Expected: FAIL because the annotation is currently `dict | None`.

- [x] **Step 3: Implement minimal hardening**

Change the nested tool signature from:

```python
def tool(command: dict | None = None, **kwargs) -> dict:
```

to:

```python
def tool(command: Any | None = None, **kwargs) -> dict:
```

Do not change Interaction provider defaults or add keyword-based success guards in this task.

- [x] **Step 4: Run focused interaction tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: PASS.

## Task 4: Real API Bake-Off

**Files:**
- Create generated evidence: `artifacts/evidence/deepseek-model-bakeoff/<timestamp>-deepseek-planner-interaction-optimization.json`
- Modify: `docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md`

- [x] **Step 1: Run local test gate**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py tests/unit/coke/turn/inbound/test_plan.py tests/unit/coke/turn/inbound/test_plan_cases.py tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: PASS.

- [x] **Step 2: Run real Planner provider eval**

Use the live `DEEPSEEK_API_KEY` and the current planner corpus. Compare:

```text
planner|glm-5.1|current|disabled
planner|deepseek-v4-flash|current_deepseek_addendum|disabled
planner|deepseek-v4-flash|current_deepseek_addendum|enabled_high
planner|deepseek-v4-pro|current_deepseek_addendum|disabled
```

Pass condition for replacing Planner: DeepSeek Flash or Pro non-thinking must
beat GLM current-prompt correctness, keep parse OK at 100%, and avoid
case-specific prompt fragility. The final production choice is Pro because it
reached 36/36 with a low latency tail; Flash stayed slightly faster but missed
one corpus case after the third optimization round.

- [x] **Step 3: Run real Interaction settings-update repeat**

Repeat the existing `settings_update` DeepSeek Flash Agno path after the annotation hardening. Pass condition for replacing Interaction: no blank output, no false-success reply, and every state-changing settings request must record a native `settings_tool` event.

- [x] **Step 4: Update issue with evidence**

Append a short section to `docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md` with the exact evidence path, summary table, and final decision:

```text
Planner: switchable / not switchable, with measured pass rate and latency.
Interaction: switchable / not switchable, with explicit false-success status.
```

## Task 5: Commit and Verification

**Files:**
- All files changed above.

- [x] **Step 1: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and identify relevant backend/repo surfaces.

- [x] **Step 2: Run final verification**

Run at minimum:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py tests/unit/coke/turn/inbound/test_plan.py tests/unit/coke/turn/inbound/test_plan_cases.py tests/unit/coke/llm/test_interaction_agent.py -q
zsh scripts/verify-surface repo-os-docs
```

Expected: PASS.

- [x] **Step 3: Commit**

Run:

```bash
git add coke/llm/config.py coke/config.py coke/composition.py coke/turn/inbound/plan.py coke/llm/agno_interaction_agent.py tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py tests/unit/coke/turn/inbound/test_plan.py tests/unit/coke/turn/inbound/test_plan_cases.py tests/unit/coke/llm/test_interaction_agent.py docs/issues/2026-06-15-deepseek-v4-replacement-investigation.md docs/superpowers/plans/2026-06-15-deepseek-planner-interaction-optimization.md
git add -f artifacts/evidence/deepseek-model-bakeoff/<timestamp>-deepseek-planner-interaction-optimization.json
git commit -m "feat(llm): improve deepseek planner candidate"
```

Expected: one commit containing code, tests, docs, and forced evidence artifact.

## Self-Review

- Spec coverage: Planner provider selection, prompt/validation optimization, Interaction hardening, real API verification, documentation, and commit are all covered.
- Placeholder scan: no deferred implementation placeholders are present.
- Type consistency: new provider fields use the existing provider constants and `OpenAILike` construction path.
