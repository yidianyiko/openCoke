# SiliconFlow Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the agent runtime from hardcoded DeepSeek calls to a configurable Agno model factory, default it to SiliconFlow, and verify real requests succeed with the SiliconFlow key already present in `.env`.

**Architecture:** Introduce one small model-factory module that translates repo config into Agno provider instances, then route every current DeepSeek construction site through that factory. Keep the change narrow: one config block, one factory, focused test coverage, and a live SiliconFlow smoke test.

**Tech Stack:** Python 3.12, Agno, SiliconFlow OpenAI-compatible API, pytest

---

### Task 1: Add config-driven model factory

**Files:**
- Create: `agent/agno_agent/model_factory.py`
- Modify: `conf/config.json`
- Test: `tests/unit/agent/test_model_factory.py`

- [ ] **Step 1: Write the failing tests**

```python
from agno.models.deepseek import DeepSeek
from agno.models.siliconflow import Siliconflow

from agent.agno_agent import model_factory


def test_create_llm_model_uses_siliconflow_config(monkeypatch):
    monkeypatch.setitem(
        model_factory.CONF,
        "llm",
        {
            "provider": "siliconflow",
            "model_id": "zai-org/GLM-5.1",
            "api_key": "sk-test",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
        },
    )

    model = model_factory.create_llm_model(max_tokens=4096)

    assert isinstance(model, Siliconflow)
    assert model.id == "zai-org/GLM-5.1"
    assert model.api_key == "sk-test"
    assert model.base_url == "https://api.siliconflow.cn/v1"
    assert model.max_retries == 2
    assert model.max_tokens == 4096


def test_create_llm_model_supports_deepseek(monkeypatch):
    monkeypatch.setitem(
        model_factory.CONF,
        "llm",
        {"provider": "deepseek", "model_id": "deepseek-chat", "max_retries": 3},
    )

    model = model_factory.create_llm_model(max_tokens=2048)

    assert isinstance(model, DeepSeek)
    assert model.id == "deepseek-chat"
    assert model.max_retries == 3
    assert model.max_tokens == 2048
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agent/test_model_factory.py -q`
Expected: FAIL because `agent.agno_agent.model_factory` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat
from agno.models.siliconflow import Siliconflow

from conf.config import CONF


def create_llm_model(*, max_tokens: int):
    llm_conf = CONF.get("llm", {})
    provider = (llm_conf.get("provider") or "deepseek").lower()
    model_id = llm_conf.get("model_id") or "deepseek-chat"
    max_retries = llm_conf.get("max_retries", 2)

    if provider == "siliconflow":
        return Siliconflow(
            id=model_id,
            api_key=llm_conf.get("api_key"),
            base_url=llm_conf.get("base_url") or "https://api.siliconflow.cn/v1",
            max_retries=max_retries,
            max_tokens=max_tokens,
        )
    if provider == "openai":
        return OpenAIChat(
            id=model_id,
            api_key=llm_conf.get("api_key"),
            base_url=llm_conf.get("base_url"),
            max_retries=max_retries,
            max_tokens=max_tokens,
        )
    if provider == "deepseek":
        return DeepSeek(id=model_id, max_retries=max_retries, max_tokens=max_tokens)
    raise ValueError(f"Unsupported llm provider: {provider}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agent/test_model_factory.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conf/config.json agent/agno_agent/model_factory.py tests/unit/agent/test_model_factory.py
git commit -m "feat(agent): add configurable llm provider factory"
```

### Task 2: Route existing agents through the factory

**Files:**
- Modify: `agent/agno_agent/agents/__init__.py`
- Modify: `agent/agno_agent/workflows/chat_workflow_streaming.py`
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Test: `tests/unit/agent/test_model_factory.py`

- [ ] **Step 1: Write the failing tests**

```python
from agno.models.siliconflow import Siliconflow

from agent.agno_agent.agents import create_llm_model
from agent.agno_agent.workflows.chat_workflow_streaming import StreamingChatWorkflow


def test_agents_module_exposes_factory_backed_model(monkeypatch):
    from agent.agno_agent import model_factory

    monkeypatch.setitem(
        model_factory.CONF,
        "llm",
        {
            "provider": "siliconflow",
            "model_id": "zai-org/GLM-5.1",
            "api_key": "sk-test",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
        },
    )

    model = create_llm_model(max_tokens=1024)
    workflow = StreamingChatWorkflow()

    assert isinstance(model, Siliconflow)
    assert isinstance(workflow.agent.model, Siliconflow)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agent/test_model_factory.py -q`
Expected: FAIL because workflows still construct `DeepSeek(...)` directly.

- [ ] **Step 3: Write minimal implementation**

```python
from agent.agno_agent.model_factory import create_llm_model

# agents/__init__.py
model=create_llm_model(max_tokens=8000)

# chat_workflow_streaming.py
model=create_llm_model(max_tokens=4096)

# post_analyze_workflow.py
model=create_llm_model(max_tokens=8000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agent/test_model_factory.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/agents/__init__.py agent/agno_agent/workflows/chat_workflow_streaming.py agent/agno_agent/workflows/post_analyze_workflow.py tests/unit/agent/test_model_factory.py
git commit -m "refactor(agent): route agno models through provider factory"
```

### Task 3: Verify with focused tests and a live SiliconFlow smoke

**Files:**
- Modify: `conf/config.json`
- Test: `tests/unit/agent/test_model_factory.py`

- [ ] **Step 1: Run focused unit tests**

Run: `pytest tests/unit/agent/test_model_factory.py tests/unit/agent/test_message_processor_stream.py -q`
Expected: PASS

- [ ] **Step 2: Run import/build sanity checks**

Run: `python3 -m compileall agent/agno_agent conf`
Expected: `Compiling ...` with no failures

- [ ] **Step 3: Run a real SiliconFlow API smoke test**

Run:

```bash
python3 - <<'PY'
from agent.agno_agent.model_factory import create_llm_model

model = create_llm_model(max_tokens=128)
resp = model.response("Reply with exactly: siliconflow-ok")
print(resp.content)
PY
```

Expected: response content contains `siliconflow-ok`

- [ ] **Step 4: Commit**

```bash
git add conf/config.json
git commit -m "test(agent): verify siliconflow runtime smoke"
```
