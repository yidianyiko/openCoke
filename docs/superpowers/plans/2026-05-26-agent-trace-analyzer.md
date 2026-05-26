# Agent Trace Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline analyzer that turns `AgentTurnTrace` JSONL evidence into aggregate findings and documents the positive feedback loop.

**Architecture:** Add an importable analyzer module under `scripts/`, a thin CLI wrapper, focused unit tests, and a durable workflow doc. The analyzer reads only serialized trace metadata, ignores raw content evidence, and emits deterministic JSON.

**Tech Stack:** Python standard library, `pytest`, JSONL trace evidence under `artifacts/evidence/agent-turn-traces/`.

---

### Task 1: Analyzer Contract Tests

**Files:**
- Create: `tests/unit/test_agent_turn_trace_analyzer.py`
- Create later: `scripts/agent_turn_trace_analyzer.py`

- [ ] **Step 1: Write failing tests**

Add tests that create synthetic JSONL records with `trace.routing.route`,
`trace.runtime.status`, `trace.output.output_source`, `trace.agent_calls`,
`trace.guardrails`, and optional `content_evidence`.

Assert that:

- route/status/output/error/guardrail/tool counts are aggregated
- exposed-but-unselected tools are counted
- raw `content_evidence` values do not appear in the summary JSON
- malformed JSONL lines increment `invalid_record_count`
- findings identify fallback output, runtime errors, guardrail failures, and
  unused exposed tools

- [ ] **Step 2: Verify tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_agent_turn_trace_analyzer.py -q
```

Expected: FAIL because `scripts.agent_turn_trace_analyzer` does not exist.

### Task 2: Analyzer Implementation

**Files:**
- Create: `scripts/agent_turn_trace_analyzer.py`

- [ ] **Step 1: Implement analyzer module**

Create functions:

- `discover_trace_files(paths: Sequence[Path]) -> list[Path]`
- `analyze_trace_records(paths: Sequence[Path]) -> dict[str, Any]`
- `analysis_to_json(summary: Mapping[str, Any]) -> str`

The analyzer must read only `record["trace"]` and ignore `content_evidence`.

- [ ] **Step 2: Verify analyzer tests pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_agent_turn_trace_analyzer.py -q
```

Expected: PASS.

### Task 3: CLI Wrapper

**Files:**
- Create: `scripts/analyze_agent_turn_traces.py`
- Modify: `tests/unit/test_agent_turn_trace_analyzer.py`

- [ ] **Step 1: Add CLI test**

Add a subprocess test that runs:

```bash
.venv/bin/python scripts/analyze_agent_turn_traces.py <trace-file> --output <summary-json>
```

Assert return code `0` and the output file contains
`schema_version == "agent_trace_analysis.v1"`.

- [ ] **Step 2: Verify CLI test fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_agent_turn_trace_analyzer.py -q
```

Expected: FAIL because the CLI wrapper does not exist.

- [ ] **Step 3: Implement CLI wrapper**

Add argparse handling for positional trace paths and optional `--output`. Print
JSON to stdout when `--output` is omitted.

- [ ] **Step 4: Verify CLI test passes**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_agent_turn_trace_analyzer.py -q
```

Expected: PASS.

### Task 4: Positive Loop Documentation

**Files:**
- Create: `docs/design-docs/agent-trace-feedback-loop.md`
- Modify: `docs/design-docs/index.md`

- [ ] **Step 1: Document the loop**

Write the durable loop:

`observe -> analyze -> choose -> change -> verify -> compare -> record`

Name the analyzer command and explain that it consumes trace metadata, not raw
conversation memory.

- [ ] **Step 2: Link from design index**

Add `agent-trace-feedback-loop.md` to `docs/design-docs/index.md`.

### Task 5: Verification And Evidence

**Files:**
- Create: `artifacts/evidence/2026-05-26-agent-trace-analyzer-verification.md`

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_agent_turn_trace_analyzer.py -q
```

- [ ] **Step 2: Run analyzer on synthetic fixture from tests or temporary trace**

Run:

```bash
.venv/bin/python scripts/analyze_agent_turn_traces.py <trace-file>
```

- [ ] **Step 3: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [ ] **Step 4: Run suggested surface verification**

Use the command suggested by `scripts/suggest-verification`.

- [ ] **Step 5: Record evidence**

Write the verification output summary to
`artifacts/evidence/2026-05-26-agent-trace-analyzer-verification.md`.

- [ ] **Step 6: Commit scoped files**

Stage only analyzer-related files, docs, tests, plan, spec, and evidence.
