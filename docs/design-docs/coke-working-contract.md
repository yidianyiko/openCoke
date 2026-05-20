# Coke Working Contract

This document defines the repository-specific work surfaces in `coke` and how
to reason about them when planning or reviewing a change.

## Ownership Axis

Planning surfaces describe where verification runs. Ownership systems describe
who owns behavior and contracts. Use
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
for Frontend App, Platform System, Channel System, Reminder System, Memo
System, Calendar Import System, Timezone System, Bridge System, Agent Runtime
System, and State/Infrastructure ownership.

A change can touch one planning surface while affecting multiple ownership
systems. Name both in non-trivial plans and reviews.

## Core Runtime Surfaces

### 1. Worker Runtime

Primary files:

- `agent/runner/agent_runner.py`
- `agent/runner/message_processor.py`
- `agent/runner/agent_handler.py`
- `agent/agno_agent/runtime/`
- `agent/agno_agent/capabilities/`
- `agent/agno_agent/adapters/`
- `agent/agno_agent/schemas/`
- `agent/agno_agent/model_factory.py`
- `agent/agno_agent/workflows/`
- `agent/agno_agent/tools/`
- `agent/prompt/`

Use this surface when the change affects:

- message acquisition or queue mode
- turn processing
- single-Agent runtime, typed runtime events, and capability tool wrappers
- background handling
- prompt or workflow behavior
- reminder, context, or runtime state logic

### 2. Coke Bridge

Primary files:

- `connector/clawscale_bridge/app.py`
- `connector/clawscale_bridge/output_dispatcher.py`
- `connector/clawscale_bridge/message_gateway.py`
- `connector/clawscale_bridge/reply_waiter.py`
- `connector/clawscale_bridge/gateway_*_client.py`

Use this surface when the change affects:

- inbound request translation
- synchronous reply waiting
- late reply promotion
- outbound push delivery
- bridge auth, identity, or delivery-route integration

### 3. Gateway Planning Surface

Primary files:

- `gateway/packages/api`
- `gateway/packages/web`
- `gateway/packages/shared`

Use this surface when the change affects:

- gateway-hosted API or web files change
- customer, channel, admin, reminder, calendar-import, or subscription routes under `gateway/` change
- shared frontend/backend DTOs under `gateway/packages/shared` change
- Prisma schema or gateway platformization logic changes

### 4. Deployment And Rollout

Primary files:

- `docker-compose.prod.yml`
- `deploy/nginx/coke.conf`
- `deploy/systemd/coke-compose.service`
- `scripts/deploy-compose-to-gcp.sh`
- `scripts/test-deploy-compose-to-gcp.sh`
- `docs/deploy.md`

Use this surface when the change affects:

- production topology
- deploy flow
- public URL or env propagation
- rollout and smoke-check procedures

## Control-Plane Artifacts

For non-trivial work:

- human/AI collaboration and verification trust rules live in
  `docs/design-docs/human-ai-working-contract.md`
- new multi-step plans go in `docs/superpowers/plans/`
- durable repository workflow rules go in `docs/design-docs/` or `docs/adr/`
- local issues, incidents, one-off repairs, and historical runbooks go in
  `docs/issues/`
- product and API surface discovery goes in
  `docs/product-specs/FEATURE_TREE.md`
- release workflow and rollout closeout go in `docs/release-guide.md` and
  `docs/RELEASE_CHECKLIST.md`
- generated verification evidence goes in `artifacts/evidence/`
- historical design and implementation context remains in
  `docs/superpowers/specs/` and `docs/superpowers/plans/`

## Planning Rule

Every non-trivial task should name the surfaces it touches. At minimum, choose
from:

- `worker-runtime`
- `bridge`
- `gateway-api`
- `gateway-web`
- `deploy`
- `repo-os`

That keeps verification scoped to the actual blast radius instead of defaulting
to vague "run tests" language.
