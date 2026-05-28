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
- Later explicit shared-invite turns for Eva/olivers did not call
  `scheduling_domain` at all and instead replied that the friend account could
  not be found, even though active friendship rows existed.
- A `reminder.fired` turn delivered `reminders:思考会` to olivers, leaking an
  internal protocol-style label as user-visible text.

## Why It Mattered

The first two failures blocked shared-reminder creation for otherwise valid
requests and caused either a fallback reply or an invented account-not-found
reply. The third failure allowed internal reminder classification text to reach
the user.

## Root Cause

The `scheduling_domain` tool description told the model to pass canonical
fields for shared-reminder and friendship actions, but the Python wrapper only
declared a small subset of those fields. Agno/Pydantic rejected the call before
the runtime could normalize or validate the canonical scheduling payload.

Reminder-fire output already rejected malformed JSON and serialized tool-call
markup, but it did not reject successful JSON text whose visible content began
with an internal `reminders:` label.

For explicit shared-invite turns without an active focus candidate, the runtime
called the semantic interpreter without an LLM client. That failed closed and
left the main chat model responsible for calling `scheduling_domain`; in the
observed Eva/olivers turns, the model skipped the tool and invented a missing
account explanation.

## Affected Surfaces

- Main interaction-agent `scheduling_domain` entrypoint.
- Scheduling intents with top-level canonical fields, including shared-reminder
  create/cancel and friendship-link creation.
- Explicit shared-invite routing without an active focus candidate.
- Reminder-fire visible output repair.

## Evidence

- Production agent logs at 2026-05-28 13:09:42 and 13:10:39 UTC showed
  `scheduling_domain(...)` validation errors for unexpected `title`,
  `fire_at`, and `duration_minutes` arguments, followed by the no-visible-reply
  fallback.
- Production Mongo `outputmessages` at 2026-05-28 13:00:15 UTC showed
  `reminders:思考会` delivered to olivers.
- Production `agent_sessions` for the Eva/olivers create attempts had no tool
  events and returned account-not-found wording from the main model.
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

Clear shared-invite utterances such as `帮我和 eva 约...` now create a semantic
interpreter client even without an active focus candidate, so scheduling intent
preselection can run before the main chat model. Personal "remind me to contact
X" turns and external activity reservation wording remain outside this routing.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -k "top_level_create_args or top_level_action_args" -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -k "internal_label_leak" -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_execution_agents.py -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -k "explicit_shared_invite_without_focus or activity_reservation_phrase or personal_contact_reminder" -q`
- `git diff --check -- agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py docs/issues/2026-05-28-scheduling-domain-schema-and-reminder-label-leak.md`
- `zsh scripts/verify-surface repo-os-docs worker-runtime`
- `./scripts/deploy-compose-to-gcp.sh --restart`
- Production container smoke confirmed no missing `scheduling_domain` fields and
  `reminders:` maps to `internal_protocol_label_leak`.
- Post-deploy `coke-agent`, `coke-bridge`, and `gateway` logs had no matching
  new `unexpected keyword argument`, traceback, or error-level output in the
  checked window.

## Resolution

Fix commit: `0c25ec95`.
