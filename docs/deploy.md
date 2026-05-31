# Deployment Notes

This document describes the clean-rebuild deployment target. Legacy deployment
commands in older plans may describe the pre-rebuild Gateway/Bridge topology and
must not be used as architectural truth.

## Future Clean-Rebuild Services

- `coke-api`: Python ingress/egress HTTP tier.
- `coke-worker`: Python Redis Stream turn workers.
- `coke-scheduler`: singleton Python reminder scheduler.
- `coke-outbox-relay`: Postgres outbox to Redis Stream relay.
- `coke-web`: Next.js thin client.
- `postgres`: product state, Agno session/history/memory/knowledge, pgvector.
- `redis`: wake-up stream, locks, reply pub/sub.

The standalone ClawScale bridge is superseded. ClawScale remains only as the
`wechat_personal` provider adapter behind Coke's canonical provider contract.

## Network Shape

- Public edge routes web traffic to `coke-web` and API/webhook traffic to
  `coke-api`.
- `coke-api`, `coke-worker`, `coke-scheduler`, and `coke-outbox-relay` share
  Postgres and Redis.
- Provider webhooks terminate at `coke-api`.
- Provider outbound calls are made through adapter code in the Python
  ingress/egress tier.
- Internal callback/wait endpoints stay private:
  `/internal/outbound/delivery-callback` and
  `/internal/reply-wait/:causal_inbound_event_id`.

## State And Restart Semantics

- Postgres is durable product, runtime, outbox, Agno, and pgvector state.
- Redis stores only stream wake-up, locks, and reply pub/sub.
- Redis restart must not strand work; unacknowledged outbox rows replay.
- `coke-scheduler` is singleton.
- Workers scale horizontally behind per-conversation locks.

## Deploy Verification

Docs-only clean-rebuild changes:

```bash
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Backend implementation changes:

```bash
.venv/bin/python -m pytest tests/unit/coke -v
```

Web implementation changes:

```bash
cd web && pnpm test
cd web && pnpm build
```

The clean compose deploy runs `coke-web` from a bind-mounted `web/` directory.
Next.js build output in `web/.next` is generated inside the running container,
so deploy sync must not delete it without recreating the web service. The
canonical deploy script preserves `.next` during rsync and force-recreates
`coke-web` after migration checks so static assets and route manifests match
the current source.

Deployment implementation tasks must add task-specific smoke evidence for the
real user path they claim. Structure checks alone do not prove runtime delivery.

## Superseded Deployment Assumptions

Do not use deployment instructions that require:

- TypeScript Gateway API as product owner
- standalone bridge process ownership
- Mongo as durable runtime storage
- Gateway-to-Bridge notification enqueue
- bridge-owned reply waiting or outbound dispatch
- legacy route aliases or compatibility stacks

If a later task reintroduces any of these, it must first update the canonical
architecture and verification docs with the current requirement.
