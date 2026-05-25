# Agent Turn Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `AgentTurnTrace` runtime evidence surface described in `docs/superpowers/specs/2026-05-26-agent-turn-trace-design.md`.

**Architecture:** Add a focused trace model/builder module under Agent Runtime, keep `AgentRunResult.trace` as the only trace attachment point, and emit optional JSONL evidence through an allowlist serializer. The runtime generates metadata traces by default, local/dev/eval can write full content evidence to JSONL, and trace persistence fails open.

**Tech Stack:** Python frozen dataclasses, existing Agent Runtime result contracts, pytest, JSONL files under `artifacts/evidence/agent-turn-traces/`.

---

## Files

- Create: `agent/agno_agent/runtime/trace.py`
  - Owns trace dataclasses, env profile resolution, allowlist serialization, JSONL path helpers, and fail-open writer.
- Modify: `agent/agno_agent/runtime/result.py`
  - Changes `AgentRunResult.trace` to normalize into `AgentTurnTrace`.
- Modify: `agent/agno_agent/runtime/__init__.py`
  - Exports trace contracts used by tests and future callers.
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
  - Builds `AgentTurnTrace` for success, empty output, timeout, unknown tool, and exception paths.
- Modify: `scripts/reminder_eval/runner.py`
  - Adds trace pointer metadata to eval summary payloads without duplicating trace records.
- Create: `tests/unit/agent/agno_agent/runtime/test_agent_turn_trace.py`
  - Covers trace profile defaults, metadata redaction, JSONL writer behavior, and fail-open persistence.
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
  - Verifies `run_agent_runtime` returns structured trace data.
- Modify: `tests/evals/test_reminder_eval_runner.py`
  - Verifies reminder eval summaries point to the trace JSONL path.

## Task 1: Trace Model And Serializer

- [ ] **Step 1: Write failing trace model tests**

Add tests in `tests/unit/agent/agno_agent/runtime/test_agent_turn_trace.py` that import:

```python
from agent.agno_agent.runtime.trace import (
    AgentTurnTrace,
    TraceOutput,
    build_agent_turn_trace,
    emit_agent_turn_trace_jsonl,
    resolve_agent_turn_trace_config,
    trace_evidence_path,
)
```

Required assertions:

- default config is enabled, profile `local`, content `full`
- server profile is enabled, content `metadata`
- metadata serialization does not include raw input text, raw output text, recent history, tool content, domain facts, or traceback text
- full JSONL evidence can include explicit `content_evidence`
- writer returns `False` and logs `trace_emit_failed` when persistence raises

- [ ] **Step 2: Run failing trace model tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/agno_agent/runtime/test_agent_turn_trace.py -q
```

Expected: FAIL because `agent.agno_agent.runtime.trace` does not exist yet.

- [ ] **Step 3: Implement trace model**

Create `agent/agno_agent/runtime/trace.py` with frozen dataclasses:

```python
AgentTurnTrace
TraceTurn
TraceRuntime
TraceRouting
TraceAgentCall
TraceResultRef
TraceGuardrail
TraceOutput
TraceError
TraceRedaction
```

Also implement:

```python
resolve_agent_turn_trace_config()
build_agent_turn_trace(...)
serialize_agent_turn_trace(...)
trace_evidence_path(...)
emit_agent_turn_trace_jsonl(...)
trace_summary_pointer(...)
```

Use allowlist serialization only. Metadata mode must not serialize raw text, payloads, full domain facts, tracebacks, prompts, or Agno messages.

- [ ] **Step 4: Run trace model tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/agno_agent/runtime/test_agent_turn_trace.py -q
```

Expected: PASS.

## Task 2: Result Contract Integration

- [ ] **Step 1: Write failing result contract test**

Update `tests/unit/agent/agno_agent/runtime/test_agent_run_result_contract.py` so constructed `AgentRunResult.trace` is an `AgentTurnTrace`, not a plain mapping.

- [ ] **Step 2: Run failing result contract test**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/agno_agent/runtime/test_agent_run_result_contract.py -q
```

Expected: FAIL until `AgentRunResult.__post_init__` normalizes trace data.

- [ ] **Step 3: Update result contract**

Modify `agent/agno_agent/runtime/result.py` to import `AgentTurnTrace` and normalize `trace` through `coerce_agent_turn_trace`.

- [ ] **Step 4: Run result contract tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/agno_agent/runtime/test_agent_run_result_contract.py tests/unit/agent/test_agent_runtime_types.py -q
```

Expected: PASS after test assertions use `result.trace.runtime.name` or equivalent structured fields.

## Task 3: Runtime Trace Generation

- [ ] **Step 1: Write failing runtime tests**

Update `tests/unit/agent/test_agent_runtime_construction.py` to assert:

- normal no-tool run returns `result.trace.schema_version == "agent_turn_trace.v1"`
- result trace route is `direct_reply`
- trace is metadata-safe when `COKE_AGENT_TURN_TRACE_PROFILE=server`
- timeout trace status is `timeout`
- exception trace has `TraceError.code == "agent_runtime_exception"`

- [ ] **Step 2: Run failing runtime tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_returns_agent_run_result_for_no_tool_run tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_fails_closed_when_agent_raises tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_times_out_when_agent_hangs -q
```

Expected: FAIL until `agent_runtime.py` builds structured traces.

- [ ] **Step 3: Wire trace builder into runtime**

Modify `agent/agno_agent/runtime/agent_runtime.py` so every return path calls the trace builder with:

- turn identity from `AgentInput` and `AgentRunContext`
- status and failure stage
- route and stable reason
- captured domain/capability results
- output disposition
- timeout seconds
- error disposition

When JSONL env is configured, emit trace evidence and ignore write failures.

- [ ] **Step 4: Run runtime tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q
```

Expected: PASS.

## Task 4: Eval Trace Pointer

- [ ] **Step 1: Write failing eval pointer test**

Update `tests/evals/test_reminder_eval_runner.py` to assert normal reminder eval payloads include:

```python
payload["trace"]["enabled"] is True
payload["trace"]["schema_version"] == "agent_turn_trace.v1"
payload["trace"]["path"].startswith("artifacts/evidence/agent-turn-traces/reminder-normal/")
```

- [ ] **Step 2: Run failing eval test**

Run:

```bash
.venv/bin/python -m pytest tests/evals/test_reminder_eval_runner.py -q
```

Expected: FAIL until `scripts/reminder_eval/runner.py` adds the trace pointer.

- [ ] **Step 3: Add eval trace pointer**

Modify `scripts/reminder_eval/runner.py` to add `trace_summary_pointer(suite="reminder-normal", run_id=run_id, record_count=<case count>)` to output payloads.

- [ ] **Step 4: Run eval tests**

Run:

```bash
.venv/bin/python -m pytest tests/evals/test_reminder_eval_runner.py -q
```

Expected: PASS.

## Task 5: Verification And Commit

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/agno_agent/runtime/test_agent_turn_trace.py tests/unit/agent/agno_agent/runtime/test_agent_run_result_contract.py tests/unit/agent/test_agent_runtime_types.py tests/unit/agent/test_agent_runtime_construction.py tests/evals/test_reminder_eval_runner.py -q
```

- [ ] **Step 2: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [ ] **Step 3: Run surface verification**

Run:

```bash
zsh scripts/verify-surface repo-os-docs worker-runtime
```

- [ ] **Step 4: Check staged diff**

Run:

```bash
git diff --check
git status --short
```

- [ ] **Step 5: Commit only trace-related files**

Run:

```bash
git add agent/agno_agent/runtime/trace.py agent/agno_agent/runtime/result.py agent/agno_agent/runtime/__init__.py agent/agno_agent/runtime/agent_runtime.py scripts/reminder_eval/runner.py tests/unit/agent/agno_agent/runtime/test_agent_turn_trace.py tests/unit/agent/agno_agent/runtime/test_agent_run_result_contract.py tests/unit/agent/test_agent_runtime_types.py tests/unit/agent/test_agent_runtime_construction.py tests/evals/test_reminder_eval_runner.py docs/superpowers/plans/2026-05-26-agent-turn-trace.md
git commit -m "feat: add agent turn trace evidence"
```
