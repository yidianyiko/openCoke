# Coke Feature Tree

Status: manual baseline, created 2026-05-09.

This file indexes the product and API surfaces that agents should inspect
before changing routes, endpoints, channel flows, or user-visible capabilities.
It is intentionally smaller than Routa's generated tree until Coke has a
checked generator.

This file is the entry point for route and endpoint discovery. It is a
repo-local map, not a product roadmap and not a replacement for
`docs/roadmap.md`.

## Runtime Surfaces

- Worker runtime
  - `agent/runner/agent_runner.py`
  - `agent/runner/message_processor.py`
  - `agent/runner/reminder_scheduler.py`
  - `agent/runner/reminder_event_handler.py`
  - `agent/runner/deferred_action_scheduler.py`
  - `agent/runner/deferred_action_executor.py`
  - `agent/agno_agent/runtime/`
  - `agent/agno_agent/capabilities/`
- Reminder System
  - visible reminder command protocol through
    `agent/agno_agent/tools/reminder_protocol/`
  - durable state in MongoDB `reminders`
  - fired-event handoff through `ReminderFireEventHandler`
  - owner-scoped reminder management service:
    `connector/clawscale_bridge/reminder_management_service.py`
  - bridge internal reminder management API:
    `/bridge/internal/reminders`
  - feature-flagged pending-workflow side channel: typed envelope in
    `agent/agno_agent/runtime/pending_workflow.py`, persistence through
    `dao/pending_workflow_dao.py` against the `pending_workflows` collection;
    runtime gated by `pending_workflow.reminders.enabled` and
    `pending_workflow.reminders.execution_envelope.enabled` (both default off)
- Deferred Actions
  - durable state in MongoDB `deferred_actions` and
    `deferred_action_occurrences`
  - executor handoff through normal conversation locking and `handle_message()`

## Bridge Surfaces

- ClawScale bridge runtime
  - `connector/clawscale_bridge/app.py`
  - `/bridge/healthz`
  - `/bridge/inbound`
  - bind and account lifecycle endpoints implemented by the bridge app
- Outbound dispatch
  - `connector/clawscale_bridge/output_dispatcher.py`
  - gateway `/api/outbound`

## Gateway Surfaces

- Gateway web
  - `gateway/packages/web`
  - public homepage and customer account/channel surfaces
  - customer reminder board: `/account/reminders`
- Gateway API
  - `gateway/packages/api`
  - shared-channel webhook normalization
  - outbound delivery route
  - customer reminder management API: `/api/customer/reminders`
  - Google Calendar import and customer claim flows

## Operations Surfaces

- Deployment
  - `docker-compose.prod.yml`
  - `scripts/deploy-compose-to-gcp.sh`
  - `docs/deploy.md`
- Release and rollout
  - `docs/release-guide.md`
  - `docs/RELEASE_CHECKLIST.md`
- Architecture
  - `docs/ARCHITECTURE.md`
  - `docs/clawscale_bridge.md`

## Update Rule

- Update this file when adding, removing, renaming, or retiring user-visible
  routes, bridge endpoints, gateway APIs, worker-triggered product surfaces, or
  deployment entrypoints.
- Keep behavioral intent in design docs, ADRs, or architecture docs. Keep this
  file focused on discoverability.
- If this file becomes generated, document the generator command here and wire
  it into repo-OS checks before claiming generated status.
