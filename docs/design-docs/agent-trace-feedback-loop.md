# Agent Trace Feedback Loop

Agent improvements should come from runtime evidence, not from memory or
grep-based log reconstruction.

The loop is:

1. Observe: emit `AgentTurnTrace` records from local, eval, or server metadata
   runs.
2. Analyze: run `scripts/analyze_agent_turn_traces.py` over the trace JSONL
   files.
3. Choose: pick the smallest high-impact finding, such as a route mismatch,
   fallback output cluster, unused exposed tool, runtime error, or guardrail
   failure.
4. Change: update the matching layer only: routing, prompt policy, tool schema,
   runtime handling, or eval fixture.
5. Verify: rerun the same eval, unit, smoke, or surface verification command.
6. Compare: analyze the new traces and compare the route, tool, output,
   guardrail, and error distribution against the earlier run.
7. Record: keep the decision and evidence in the relevant spec, plan, issue, or
   `artifacts/evidence/` file.

This follows the repository rule that evidence is stronger than confidence. It
also keeps trace data out of conversation memory, prompts, chat history, and
user-visible output. Full local/eval traces may contain content evidence, but
the analyzer consumes only the serialized `trace` metadata by default.
