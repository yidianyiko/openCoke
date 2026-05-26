# Agent Trace Analyzer Design

## Context

`AgentTurnTrace` now records one structured sidecar record per agent turn. That
solves the first observability problem: the runtime can explain what route,
tools, output disposition, guardrails, and error state occurred without mixing
diagnostic evidence into logs, prompts, chat history, or user-visible output.

The next step is to consume that evidence. Raw JSONL files still require a
human to inspect each turn manually. That does not create the positive loop we
want: observe runtime behavior, analyze patterns, choose one small improvement,
run evals again, and compare whether the trace distribution improved.

## Goal

Add a small offline analyzer for `AgentTurnTrace` JSONL files and document the
feedback loop that turns trace evidence into routing, prompt, and tool-interface
improvements.

## Non-Goals

- Do not add a production trace database.
- Do not add an admin UI.
- Do not read raw `content_evidence` text in the analyzer.
- Do not change runtime behavior or trace emission.
- Do not make analyzer results part of user-visible responses.

## Design

Create `scripts/agent_turn_trace_analyzer.py` as an importable module and
`scripts/analyze_agent_turn_traces.py` as the CLI wrapper.

The analyzer accepts one or more trace JSONL files or directories. Directories
are scanned recursively for `*.jsonl` files. Each valid record contributes the
safe serialized `trace` object only. The analyzer ignores `content_evidence`
even when full local/eval traces contain it.

The output is a deterministic JSON summary:

- `schema_version`: `agent_trace_analysis.v1`
- `source_files`: analyzed JSONL files
- `record_count`
- `invalid_record_count`
- `route_counts`
- `status_counts`
- `output_source_counts`
- `error_counts`
- `guardrail_failure_counts`
- `tool_exposure_counts`
- `selected_tool_counts`
- `unused_exposed_tool_counts`
- `findings`
- `positive_loop`

`findings` are lightweight, rule-based pointers for the next improvement:

- non-ok runtime status points to runtime reliability or timeout work
- fallback/empty output points to output synthesis or route handling work
- guardrail failures point to visible-output acceptance and durable-write
  safety work
- tools exposed but never selected point to ACI/tool documentation or routing
  clarity work

## Positive Loop

The durable loop is:

1. Observe: emit `AgentTurnTrace` records from local, eval, or server metadata
   runs.
2. Analyze: run the trace analyzer to aggregate route, tool, output, guardrail,
   and error patterns.
3. Choose: pick the smallest high-impact improvement indicated by the findings.
4. Change: adjust routing, prompt policy, tool schema, or runtime handling.
5. Verify: rerun the same eval or smoke surface.
6. Compare: run the analyzer again and compare trace deltas.
7. Record: keep the evidence and decision in the relevant spec, plan, issue, or
   evidence artifact.

This keeps agent improvements grounded in environment feedback instead of
memory, intuition, or grep-based log reconstruction.

## Verification

- Unit tests cover file discovery, safe aggregation, invalid-line accounting,
  finding generation, and the rule that raw `content_evidence` text is ignored.
- CLI tests cover writing a JSON summary to `--output`.
- Diff-aware verification decides the final repo surface command.
