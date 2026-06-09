# Turn Latency Phase Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe phase/call latency telemetry and verify it with an active clean smoke case.

**Architecture:** A small observability helper emits `turn_latency_event`
structured logs. TurnRunner records turn and Interaction Agent call phases, and
AgnoJSONCompletionClient records JSON LLM calls. No prompts, replies, tool args,
or raw model outputs are logged.

**Tech Stack:** Python logging, `time.perf_counter`, pytest `caplog`, existing clean smoke harness.

---

### Task 1: Telemetry Helper

**Files:**
- Create: `coke/observability/turn_latency.py`
- Test: `tests/unit/coke/test_turn_latency_telemetry.py`

- [ ] **Step 1: Write the failing helper tests**

```python
import logging

import pytest

from coke.observability.turn_latency import turn_latency_span


def test_turn_latency_span_logs_safe_completion_fields(caplog):
    clock_values = iter([10.0, 10.125])

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        with turn_latency_span(
            "turn.semantic_interpreter",
            turn_id="turn-1",
            trigger_type="InboundTurn",
            mode="interactive",
            account_id="acct-1",
            conversation_id="conv-1",
            clock=lambda: next(clock_values),
            extra={"model_role": "semantic_interpreter"},
        ):
            pass

    record = caplog.records[-1]
    assert record.event_name == "turn_latency_event"
    assert record.getMessage().startswith("turn_latency_event {")
    assert record.phase == "turn.semantic_interpreter"
    assert record.status == "ok"
    assert record.duration_ms == 125
    assert record.turn_id == "turn-1"
    assert record.model_role == "semantic_interpreter"
    assert not hasattr(record, "prompt")
    assert not hasattr(record, "content")


def test_turn_latency_span_logs_error_status_and_reraises(caplog):
    clock_values = iter([20.0, 20.5])

    with pytest.raises(RuntimeError):
        with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
            with turn_latency_span(
                "agent.primary",
                turn_id="turn-2",
                trigger_type="InboundTurn",
                mode="interactive",
                clock=lambda: next(clock_values),
            ):
                raise RuntimeError("boom")

    record = caplog.records[-1]
    assert record.phase == "agent.primary"
    assert record.status == "error"
    assert record.error_type == "RuntimeError"
    assert record.duration_ms == 500
```

- [ ] **Step 2: Run the helper tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/coke/test_turn_latency_telemetry.py -v`

Expected: fail during import because `coke.observability.turn_latency` does not exist.

- [ ] **Step 3: Implement the helper**

Create `coke/observability/turn_latency.py` with:

```python
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

LOGGER = logging.getLogger(__name__)

SAFE_EXTRA_FIELDS = frozenset(
    {
        "account_id",
        "conversation_id",
        "duration_ms",
        "error_type",
        "event_name",
        "message_count",
        "mode",
        "model",
        "model_provider",
        "model_role",
        "phase",
        "retry_attempt",
        "status",
        "timeout",
        "tool_count",
        "trigger_type",
        "turn_id",
    }
)


@contextmanager
def turn_latency_span(
    phase: str,
    *,
    turn_id: str | None = None,
    trigger_type: str | None = None,
    mode: Any | None = None,
    account_id: str | None = None,
    conversation_id: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
    extra: Mapping[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    start = clock()
    base = {
        "phase": phase,
        "turn_id": turn_id,
        "trigger_type": trigger_type,
        "mode": str(mode) if mode is not None else None,
        "account_id": account_id,
        "conversation_id": conversation_id,
    }
    if extra:
        base.update(dict(extra))
    try:
        yield base
    except Exception as error:
        _log_event(base, clock() - start, status="error", error_type=type(error).__name__)
        raise
    else:
        _log_event(base, clock() - start, status="ok")


def log_turn_latency_event(
    phase: str,
    *,
    duration_seconds: float,
    status: str,
    turn_id: str | None = None,
    trigger_type: str | None = None,
    mode: Any | None = None,
    account_id: str | None = None,
    conversation_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    base = {
        "phase": phase,
        "turn_id": turn_id,
        "trigger_type": trigger_type,
        "mode": str(mode) if mode is not None else None,
        "account_id": account_id,
        "conversation_id": conversation_id,
    }
    if extra:
        base.update(dict(extra))
    _log_event(base, duration_seconds, status=status)


def _log_event(
    fields: Mapping[str, Any],
    duration_seconds: float,
    *,
    status: str,
    error_type: str | None = None,
) -> None:
    payload = {
        key: value
        for key, value in fields.items()
        if key in SAFE_EXTRA_FIELDS and value is not None
    }
    payload["duration_ms"] = max(0, int(round(duration_seconds * 1000)))
    payload["status"] = status
    payload["event_name"] = "turn_latency_event"
    if error_type is not None:
        payload["error_type"] = error_type
    LOGGER.info(
        "turn_latency_event %s",
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
        extra=payload,
    )
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/coke/test_turn_latency_telemetry.py -v`

Expected: both tests pass.

### Task 2: TurnRunner Phase Instrumentation

**Files:**
- Modify: `coke/turn/runner.py`
- Test: `tests/unit/coke/turn/test_turn_runner.py`

- [ ] **Step 1: Add failing TurnRunner telemetry tests**

Add focused tests near the existing TurnRunner tests that run a normal inbound
turn and a protocol-retry turn, then assert `caplog` contains:

```python
expected_phases = {
    "turn.semantic_interpreter",
    "turn.context_assembly",
    "agent.primary",
    "turn.total",
}
assert expected_phases <= {
    record.phase
    for record in caplog.records
    if getattr(record, "event_name", None) == "turn_latency_event"
}
```

For the protocol retry case, assert `"agent.protocol_retry"` is present and has
`retry_attempt == 1`.

- [ ] **Step 2: Run the new TurnRunner tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -k 'latency or protocol_retry' -v`

Expected: fail because no `turn_latency_event` records are emitted.

- [ ] **Step 3: Instrument synchronous and async TurnRunner paths**

Import `turn_latency_span` and wrap the existing code blocks:

```python
with turn_latency_span("turn.total", turn_id=start.turn.id, trigger_type=trigger.trigger_type, mode=TurnMode.INTERACTIVE.value, account_id=trigger.account_id, conversation_id=trigger.conversation_id):
    ...
with turn_latency_span("turn.semantic_interpreter", ...):
    semantic_decision = self.semantic_interpreter.interpret(...)
with turn_latency_span("turn.context_assembly", ...):
    trusted_facts = ...
    context = self.context_assembler.build(...)
```

In `_invoke_agent_and_record` and `_invoke_agent_and_record_async`, wrap the
primary and retry `interaction_agent.invoke` / `ainvoke` calls with
`agent.primary` and `agent.protocol_retry` spans. Include `retry_attempt=1` on
the retry span.

- [ ] **Step 4: Run TurnRunner tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -k 'latency or protocol_retry' -v`

Expected: selected tests pass.

### Task 3: LLM Call Instrumentation

**Files:**
- Modify: `coke/llm/semantic_interpreter.py`
- Test: `tests/unit/coke/llm/test_semantic_interpreter.py`

- [ ] **Step 1: Add failing LLM telemetry tests**

Add tests asserting AgnoJSONCompletionClient emits `llm_json.semantic_decision`
or `llm_json.detected_reminder_fields` without prompt/content fields.

- [ ] **Step 2: Run the LLM tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/coke/llm/test_semantic_interpreter.py -k latency -v`

Expected: fail because the LLM-level telemetry is not emitted.

- [ ] **Step 3: Implement LLM call logging**

Use `turn_latency_span` in AgnoJSONCompletionClient.complete_json. For
`schema_name`, map directly to
`phase=f"llm_json.{schema_name}"` and `model_role=schema_name`.

- [ ] **Step 4: Run the LLM tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/coke/llm/test_semantic_interpreter.py -k latency -v`

Expected: selected tests pass.

### Task 4: Smoke Evidence With Real Case Harness

**Files:**
- Modify only if needed: `scripts/smoke/clean_smoke.py`
- Evidence: `artifacts/evidence/clean-smoke/<run-id>.json`

- [ ] **Step 1: Dry-run the harness locally**

Run: `.venv/bin/python -m scripts.smoke.clean_smoke --dry-run --run-id latency-dry-run`

Expected: JSON status `passed` and query compilation evidence.

- [ ] **Step 2: Deploy the telemetry change**

Run the repository deploy command from `docs/deploy.md` for the clean stack.
Confirm `/home/whoami/coke-clean/.deployed-sha` matches the new commit.

- [ ] **Step 3: Run active webhook-mode smoke**

Run with production-safe env and a marker:

```bash
.venv/bin/python -m scripts.smoke.clean_smoke --mode webhook --run-id latency-YYYYMMDDTHHMMSSZ
```

Expected: smoke evidence status is `passed` or a failure evidence file points to
the exact phase that failed.

- [ ] **Step 4: Collect latency evidence**

Query Postgres for marker-matched turns and inspect worker logs for
`turn_latency_event`. Record turn ids, total durations, Interaction Agent
durations, and telemetry phase durations.

### Task 5: Verification and Commit

**Files:**
- Modify: implementation/test/docs files touched above

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_turn_latency_telemetry.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_semantic_interpreter.py tests/unit/coke/llm/test_reminder_detector.py tests/unit/coke/smoke/test_clean_smoke.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run diff-aware verification**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete; follow any required surface command suggestions.

- [ ] **Step 3: Commit**

Run:

```bash
git add coke/observability coke/turn/runner.py coke/llm/semantic_interpreter.py tests/unit/coke docs/superpowers/specs/2026-06-09-turn-latency-phase-telemetry-design.md docs/superpowers/plans/2026-06-09-turn-latency-phase-telemetry.md
git commit -m "feat(observability): add turn latency phase telemetry"
```
