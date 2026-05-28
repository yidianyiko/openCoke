---
kind: incident
status: resolved
surface: agent-runtime
owner: agent
created_at: 2026-05-28
resolved_at: 2026-05-28
---

# Scheduling Domain Schema and Reminder Label Leak

## What Happened

During production log review for the two hours before 2026-05-28 13:14 UTC,
two user-visible runtime failures were found:

- Shared-reminder create turns for 李梓豪 failed before scheduling execution
  because the main interaction-agent `scheduling_domain` wrapper rejected
  top-level create arguments such as `title`, `fire_at`, and
  `duration_minutes`.
- A `reminder.fired` turn delivered `reminders:思考会` to olivers, leaking an
  internal protocol-style label as user-visible text.

## Why It Mattered

The first failure blocked shared-reminder creation for otherwise valid requests
and caused a fallback reply. The second failure allowed internal reminder
classification text to reach the user.

## Root Cause

The `scheduling_domain` tool description told the model to pass canonical
fields for shared-reminder and friendship actions, but the Python wrapper only
declared a small subset of those fields. Agno/Pydantic rejected the call before
the runtime could normalize or validate the canonical scheduling payload.

Reminder-fire output already rejected malformed JSON and serialized tool-call
markup, but it did not reject successful JSON text whose visible content began
with an internal `reminders:` label.

## Affected Surfaces

- Main interaction-agent `scheduling_domain` entrypoint.
- Scheduling intents with top-level canonical fields, including shared-reminder
  create/cancel and friendship-link creation.
- Reminder-fire visible output repair.

## Evidence

- Production agent logs at 2026-05-28 13:09:42 and 13:10:39 UTC showed
  `scheduling_domain(...)` validation errors for unexpected `title`,
  `fire_at`, and `duration_minutes` arguments, followed by the no-visible-reply
  fallback.
- Production Mongo `outputmessages` at 2026-05-28 13:00:15 UTC showed
  `reminders:思考会` delivered to olivers.
- Production Postgres `outbound_deliveries` for the reviewed window were all
  `succeeded`, so these were runtime-content failures rather than transport
  delivery failures.
- Verification report:
  `artifacts/evidence/agent-runtime/2026-05-28-scheduling-domain-schema-and-reminder-label-leak.md`.

## Fix

The main interaction-agent `scheduling_domain` wrapper now accepts the canonical
top-level scheduling fields it advertises and forwards them into the existing
forced-argument validation path. For live-style shared-reminder create calls,
`friend_name` is normalized to `receiver_name` only for
`create_shared_reminder`.

Reminder-fire visible output now treats `reminders:`/`reminder:` prefixes as a
repairable internal protocol-label leak, including reminder turns without a
durable write in the same agent call.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -k "top_level_create_args or top_level_action_args" -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -k "internal_label_leak" -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_execution_agents.py -q`
- `git diff --check -- agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py docs/issues/2026-05-28-scheduling-domain-schema-and-reminder-label-leak.md`
- `zsh scripts/verify-surface repo-os-docs worker-runtime`

## Resolution

Fix commit: `5c594e09`.
