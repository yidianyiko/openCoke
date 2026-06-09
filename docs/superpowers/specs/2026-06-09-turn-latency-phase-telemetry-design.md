# Turn Latency Phase Telemetry Design

## Status

approved-for-implementation

## Problem

Real user turns show a 20-30 second median and severe tail latency, but current
durable data only gives turn start/completion and Agno run metrics for the final
Interaction Agent run. It does not reliably answer how much time was spent in
SemanticInterpreter, context assembly, Interaction Agent primary run, protocol
retry, delivery recording, or detector/tool execution. This makes provider
latency and architecture latency easy to conflate.

## Goal

Add metadata-only latency telemetry that can break a turn into phases and model
calls, then actively sample the deployed stack with the existing real-user smoke
case harness instead of waiting only for natural traffic.

## Non-Goals

- Do not change model provider, prompts, tool behavior, or user-visible reply
  behavior.
- Do not persist prompt text, reply text, user message text, tool arguments, or
  raw model output in telemetry.
- Do not add a new database table in this slice.
- Do not hand-write production inbound payloads when a repository smoke harness
  covers the path.

## Architecture

Telemetry is a thin structured-log layer. `TurnRunner` owns turn phase timing,
`AgnoInteractionAgent` owns Interaction Agent call timing, and
`AgnoJSONCompletionClient` owns JSON-completion call timing for interpreter and
detector users. Each event logs safe identifiers and counters only: turn id,
conversation id, account id, trigger type, mode, phase or model role,
duration_ms, status, retry attempt, timeout flag, tool_count, and message_count
where available.

The log message prefix is stable: `turn_latency_event`. The same safe payload
lives in the record `extra` fields and as compact JSON in the log message so
Docker logs and Python test `caplog` can consume it without parsing user
content.

## Phase Coverage

- `turn.total`: full synchronous turn body from start row to result.
- `turn.semantic_interpreter`: SemanticInterpreter call plus post-processing.
- `turn.context_assembly`: trusted facts, recoverable context, memory load, and
  ContextAssembler.
- `agent.primary`: first Interaction Agent invocation.
- `agent.protocol_retry`: second Interaction Agent invocation after output
  protocol validation failure.
- `llm_json.semantic_decision`: JSON completion used by SemanticInterpreter.
- `llm_json.detected_reminder_fields`: JSON completion used by reminder
  detector.

## Active Verification

After deployment, run the clean smoke harness with a unique latency marker:

```bash
.venv/bin/python -m scripts.smoke.clean_smoke --mode webhook --run-id latency-YYYYMMDDTHHMMSSZ
```

If real WhatsApp sending is available and the operator wants provider-delivered
inbound instead of synthetic webhook inbound, run:

```bash
.venv/bin/python -m scripts.smoke.clean_smoke --mode real --run-id latency-YYYYMMDDTHHMMSSZ
```

Both modes must write an evidence JSON under `artifacts/evidence/clean-smoke/`.
The verification report must include the marker, turn ids, turn durations, Agno
run durations when joinable, and matching `turn_latency_event` log summaries.

## Safety

Webhook mode simulates provider webhook input against real clean production
services. Real mode requires manually sending the listed WhatsApp messages from
the configured real accounts, so it can create real reminders and push real
messages. All runs use a unique marker. The smoke harness writes durable
evidence and uses clean Postgres as the verdict.

## Tests

- Unit-test the telemetry helper with safe field filtering, duration
  measurement, and failure status.
- Unit-test TurnRunner logging for semantic, context, agent primary, protocol
  retry, and total phase events using existing fake ports.
- Unit-test AgnoInteractionAgent logging for normal and timeout results without
  logging content.
- Unit-test AgnoJSONCompletionClient logging using a fake model response.
- Run the relevant turn, LLM, smoke, and repo-OS verification surfaces before
  deployment.
