# Reminder And Streaming Failure Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix confirmed reminder and chat-turn failure paths so missing reminder actions, millisecond timestamps, and provider-side streaming failures do not silently break user-visible behavior.

**Architecture:** Harden the tool and handler boundaries instead of relying on LLM compliance. Normalize timestamps at the reminder entrypoint, add a narrow recovery path for missing reminder actions, and propagate chat streaming failures to the handler so the turn is rolled back or failed instead of being finalized as success.

**Tech Stack:** Python 3.12, pytest, Agno agents/workflows

### Task 1: Reproduce and lock down reminder action/timestamp bugs

**Files:**
- Modify: `tests/unit/test_reminder_tools_gtd.py`
- Modify: `tests/unit/reminder/test_parser.py`
- Modify: `tests/unit/reminder/test_service.py`

**Step 1: Write the failing tests**

```python
def test_create_reminder_without_action_but_single_create_payload_recovers(...):
    ...

def test_time_parser_normalizes_millisecond_base_timestamp_for_relative_time():
    ...

def test_service_parser_receives_normalized_base_timestamp():
    ...
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_reminder_tools_gtd.py tests/unit/reminder/test_parser.py tests/unit/reminder/test_service.py -v`
Expected: FAIL on missing-action recovery and millisecond timestamp normalization assertions.

**Step 3: Write minimal implementation**

```python
# reminder_tools.py
normalized_timestamp = validate_timestamp(raw_timestamp, "input_timestamp", default_to_now=False)
inferred_action = _infer_action_from_payload(...)

# parser.py
self.base_timestamp = validate_timestamp(base_timestamp, "base_timestamp", default_to_now=False)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_reminder_tools_gtd.py tests/unit/reminder/test_parser.py tests/unit/reminder/test_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_reminder_tools_gtd.py tests/unit/reminder/test_parser.py tests/unit/reminder/test_service.py agent/agno_agent/tools/reminder_tools.py agent/agno_agent/tools/reminder/parser.py agent/agno_agent/tools/reminder/service.py
git commit -m "fix(reminder): recover missing actions and normalize timestamps"
```

### Task 2: Make streaming provider failures visible to the handler

**Files:**
- Create: `tests/unit/agent/test_agent_handler.py`
- Modify: `agent/runner/agent_handler.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_handle_message_marks_stream_provider_error_for_rollback(monkeypatch, sample_context):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agent/test_agent_handler.py -v`
Expected: FAIL because handler currently logs the error and returns success-like state.

**Step 3: Write minimal implementation**

```python
stream_error = None
elif event["type"] == "error":
    stream_error = event["data"].get("error")
    is_rollback = True
    break
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agent/test_agent_handler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/agent/test_agent_handler.py agent/runner/agent_handler.py
git commit -m "fix(chat): rollback turns on streaming provider failure"
```

### Task 3: Verify the integrated fix set

**Files:**
- Modify: `agent/agno_agent/tools/reminder_tools.py`
- Modify: `agent/agno_agent/tools/reminder/parser.py`
- Modify: `agent/runner/agent_handler.py`

**Step 1: Run targeted regression suite**

Run: `pytest tests/unit/test_reminder_tools_gtd.py tests/unit/reminder/test_parser.py tests/unit/reminder/test_service.py tests/unit/agent/test_agent_handler.py -v`
Expected: PASS

**Step 2: Run adjacent workflow tests**

Run: `pytest tests/unit/test_prepare_workflow_web_search.py -v`
Expected: PASS

**Step 3: Review diff for scope control**

Run: `git diff --stat`
Expected: Only reminder tool/parser/service, handler, and the new/updated tests changed.

**Step 4: Commit**

```bash
git add agent/agno_agent/tools/reminder_tools.py agent/agno_agent/tools/reminder/parser.py agent/agno_agent/tools/reminder/service.py agent/runner/agent_handler.py tests/unit/test_reminder_tools_gtd.py tests/unit/reminder/test_parser.py tests/unit/reminder/test_service.py tests/unit/agent/test_agent_handler.py docs/plans/2026-03-17-reminder-and-streaming-failure-fixes.md
git commit -m "fix(agent): harden reminder and streaming failure handling"
```
