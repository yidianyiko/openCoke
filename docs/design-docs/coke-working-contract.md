# Coke Working Contract

This document defines the repository-specific work surfaces in `coke` and how
to reason about them when planning or reviewing a change.

## Core Runtime Surfaces

### 1. Worker Runtime

Primary files:

- `agent/runner/agent_runner.py`
- `agent/runner/message_processor.py`
- `agent/runner/agent_handler.py`
- `agent/agno_agent/workflows/`
- `agent/prompt/`

Use this surface when the change affects:

- message acquisition or queue mode
- turn processing
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

### 3. Gateway Platform Layer

Primary files:

- `gateway/packages/api`
- `gateway/packages/web`
- `gateway/packages/shared`

Use this surface when the change affects:

- ClawScale customer/channel/admin APIs
- Coke user auth, bind, or payment web flows
- shared-channel and delivery-route behavior
- platformization logic and Prisma schema

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

- task-local state goes in `tasks/`
- new multi-step plans go in `docs/exec-plans/`
- durable repository workflow rules go in `docs/design-docs/` or `docs/adr/`
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
