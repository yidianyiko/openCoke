# Coke Feature Tree

Status: manual baseline, created 2026-05-09.

This file indexes the product and API surfaces that agents should inspect
before changing routes, endpoints, channel flows, or user-visible capabilities.
It is intentionally smaller than Routa's generated tree until Coke has a
checked generator.

This file is the entry point for route and endpoint discovery. It is a
repo-local map, not a product roadmap and not a replacement for
`docs/roadmap.md`.

For Ownership system classification, use
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.
This feature tree remains a discovery map; it does not decide ownership by
directory alone.

## Runtime Surfaces

- Worker runtime
  - `agent/runner/agent_runner.py`
  - `agent/runner/message_processor.py`
  - `agent/runner/reminder_scheduler.py`
  - `agent/runner/reminder_event_handler.py`
  - `agent/agno_agent/runtime/`
  - `agent/agno_agent/capabilities/`
- Reminder System
  - visible reminder command protocol through
    `agent/agno_agent/tools/reminder_protocol/`
  - durable state in MongoDB `reminders`
  - internal agent follow-up state in MongoDB `reminders` with
    `visibility=internal` and `fire_mode=followup`
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
- Memo runtime contract
  - headless embedded package: `memo-runtime/`
  - Coke agent adapter: `agent/agno_agent/capabilities/memo.py`
  - product behavior: memo cards, search, review queue, and agent proposals
  - frontend implementation is a consumer and must not own memo business rules
- Timezone System
  - domain service: `agent/timezone_service.py`
  - runtime port: `agent/agno_agent/capabilities/timezone_port.py`
  - tool adapter: `agent/agno_agent/tools/timezone_tools.py`
  - runtime identity resolution: `agent/runner/identity.py`
  - durable state read/write: `dao/user_dao.py`

## Bridge Surfaces

- ClawScale bridge runtime
  - `connector/clawscale_bridge/app.py`
  - `/bridge/healthz`
  - `/bridge/inbound`
  - bridge ingress, egress, synchronous reply waiting, and late reply promotion
- Outbound dispatch
  - `connector/clawscale_bridge/output_dispatcher.py`
  - gateway `/api/outbound`

## Platform / Gateway Surfaces

- Frontend App
  - `gateway/packages/web`
  - public homepage, customer auth, customer account, and customer product-entry surfaces
- Platform System
  - `gateway/packages/api/src/routes/customer-auth-routes.ts`
  - `gateway/packages/api/src/routes/customer-claim-routes.ts`
  - subscription and account-management routes
- User Link Scheduling
  - public web entry: `gateway/packages/web/app/u/[code]/page.tsx`
  - public QR route: `gateway/packages/web/app/u/[code]/qr/route.ts`
  - public API: `gateway/packages/api/src/routes/public-user-link-routes.ts`
  - customer API: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
  - internal agent API: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
  - Gateway domain services: `gateway/packages/api/src/scheduling/`
  - Worker agent tools: `agent/agno_agent/capabilities/scheduling.py`
- User Agent Instance Settings
  - customer web entry:
    `gateway/packages/web/app/(customer)/account/my-agent/page.tsx`
  - customer API:
    `gateway/packages/api/src/routes/customer-agent-instance-routes.ts`
  - gateway bridge client:
    `gateway/packages/api/src/lib/agent-instance-runtime-client.ts`
  - bridge internal API: `/bridge/internal/agent-instances`
  - bridge service: `connector/clawscale_bridge/agent_instance_service.py`
  - worker storage: MongoDB `agent_instances` through
    `dao/agent_instance_dao.py`
  - runtime prompt composition:
    `agent/runner/context.py`,
    `agent/agno_agent/runtime/context.py`,
    `agent/agno_agent/runtime/chat_response_instructions.py`
- Calendar Import Integration
  - customer API:
    `gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts`
  - customer callback API:
    `gateway/packages/api/src/routes/customer-google-calendar-import-callback-routes.ts`
  - handoff API:
    `gateway/packages/api/src/routes/calendar-import-handoff-routes.ts`
  - bridge adapter:
    `connector/clawscale_bridge/google_calendar_import_service.py`
  - agent capability and handoff tool:
    `agent/agno_agent/capabilities/calendar_import_port.py`,
    `agent/agno_agent/tools/calendar_import_handoff.py`

## Channel Surfaces

- Channel System
  - `gateway/packages/api/src/gateway/message-router.ts`
  - `gateway/packages/api/src/lib/route-message.ts`
  - `gateway/packages/api/src/routes/customer-channel-routes.ts`
  - `gateway/packages/api/src/routes/outbound.ts`
  - provider-specific config and dispatch helpers under `gateway/packages/api/src/lib/`

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
