---
kind: verification_report
status: complete
surface:
  - conversation-runtime
  - worker-runtime
  - production-smoke
  - llm-runtime
severity: P1
created_at: 2026-06-09
updated_at: 2026-06-09
---

# 2026-06-09 Real-User Turn Latency Phase Probe

## What Was Probed

Two focused webhook probe runs simulated real user messages through the clean
production stack after the transaction-pinning fix was deployed:

- `latency_probe_20260609T074447Z`: English greeting, personal reminder create,
  and reminder list.
- `latency_probe_cn_20260609T074947Z`: Chinese greeting, personal reminder
  create, and reminder list.

The probes used an active connected production route and posted inbound
Evolution webhook events to `/webhooks/whatsapp/evolution`. Each case waited for
the corresponding `turn` row to complete and recorded outbound delivery count.

Raw local evidence was copied to:

- `artifacts/evidence/latency-probe/latency_probe_20260609T074447Z.json`
- `artifacts/evidence/latency-probe/latency_probe_cn_20260609T074947Z.json`

Those raw JSON files were left untracked because they include real production
route identifiers. This report records the route-independent timing summary.

## Result Summary

All six simulated user turns completed with `disposition='replied'` and
`reason_code='reply_ready'`.

Per-turn completion time from the database:

| case | db turn time |
| --- | ---: |
| English greeting | 16.9s |
| English create reminder | 20.4s |
| English list reminders | 13.0s |
| Chinese greeting | 27.7s |
| Chinese create reminder | 16.5s |
| Chinese list reminders | 14.0s |

Worker phase telemetry:

| case | turn.total | semantic_interpreter | context_assembly | agent.primary | tools |
| --- | ---: | ---: | ---: | ---: | ---: |
| English greeting | 16.9s | 2.8s | 0.0s | 14.1s | 0 |
| English create reminder | 23.6s | 2.8s | 0.0s | 17.5s | 1 |
| English list reminders | 13.1s | 3.1s | 0.0s | 9.8s | 1 |
| Chinese greeting | 27.7s | 9.7s | 0.0s | 18.0s | 0 |
| Chinese create reminder | 21.2s | 3.2s | 0.0s | 13.2s | 1 |
| Chinese list reminders | 14.1s | 2.2s | 0.0s | 11.7s | 1 |

Aggregate phase timing:

- `turn.total`: 6 samples, average 19.4s, range 13.1s-27.7s.
- `agent.primary`: 6 samples, average 14.0s, range 9.8s-18.0s.
- `turn.semantic_interpreter`: 6 samples, average 4.0s, range 2.2s-9.7s.
- `turn.context_assembly`: effectively 0ms.

Reminder creation also emitted detector telemetry:

- English `detected_reminder_fields`: 3.1s.
- Chinese `detected_reminder_fields`: 4.6s.

## Interpretation

The dominant latency source for normal turns is the serial Interaction Agent
phase, not the database, context assembly, or provider delivery. In this probe
set, `agent.primary` accounts for roughly 72% of the average `turn.total`
duration.

The third-party architecture feedback is directionally correct: replacing a
provider can reduce individual model-call duration, but it does not remove the
current serial shape:

1. semantic interpreter LLM call on every turn;
2. Interaction Agent LLM/tool loop for the user-visible response;
3. reminder detector LLM call inside create-reminder tool paths.

For example, the no-tool greeting cases still spend 14.1s and 18.0s in
`agent.primary`. That path has no reminder tool work to optimize away. It pays
the Interaction Agent cost primarily to produce the user-visible prose.

For reminder creation, the system pays the semantic interpreter cost, then the
Interaction Agent cost, then the detector cost. That confirms a serial
multi-call shape on a routine state-changing turn.

## Code Path Anchors

- `coke/turn/runner.py` wraps semantic interpretation in
  `turn.semantic_interpreter` before invoking the agent.
- `coke/turn/runner.py` wraps the universal user-visible agent call in
  `agent.primary`.
- `coke/llm/agno_interaction_agent.py` instructs reminder creation to call
  `reminder_tool` with `operation=detect_and_create`.
- `coke/composition.py` routes `detect_and_create` reminder tool calls to the
  reminder detector path.

## Cleanup And Safety Checks

The two probe-created reminders were soft-deleted after the run. Follow-up
production checks returned:

- `0` active reminders matching either probe marker.
- `0` `reminder_fire` rows for either probe marker.
- `0` lock waits or idle transactions on the follow-up check.

## Optimization Candidates

1. Add deeper `agent.primary` telemetry before changing behavior.
   Current phase telemetry proves the agent dominates, but does not yet split
   one long model call from a multi-call Agno tool loop. Instrumenting model
   calls with `turn_id`, agent role, tool call count, and attempt count should
   be the next low-risk step.

2. Collapse the create-reminder serial chain.
   A designed path could run reminder detection before the full Interaction
   Agent response for semantic decisions that are already classified as
   reminder creation, then pass structured detector output into the response
   renderer. This targets a whole serial LLM segment, not a small provider
   speedup.

3. Consider a narrow light-response path for no-tool turns.
   Greetings and simple acknowledgements currently pay the full Interaction
   Agent cost even when `tool_count=0`. Any shortcut must be designed against
   the product contract and evals; it should not be a broad keyword heuristic.

4. Evaluate safe parallelization only after instrumentation.
   Detector-first or speculative detector parallelism may reduce reminder-create
   latency, but it changes cancellation, side-effect, and response ownership
   boundaries. It needs a spec and tests before implementation.

