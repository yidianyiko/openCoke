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

## Provider Webhook Authentication

`coke-api` accepts unauthenticated provider webhooks only while
`COKE_WEBHOOK_INBOUND_SECRET` is unset. Once the variable is set, every provider
webhook must present the same shared secret before Coke reads the JSON payload.

- WeChat personal connector: set `COKE_WEBHOOK_INBOUND_SECRET` in the connector
  environment; it sends `X-Coke-Webhook-Secret: <secret>`.
- Evolution/WhatsApp: configure the webhook request to send either
  `X-Webhook-Secret: <secret>` or `Authorization: Bearer <secret>` to
  `/webhooks/whatsapp/evolution`.
- Coke API: set the same `COKE_WEBHOOK_INBOUND_SECRET` value on `coke-api`.

Do not enable the API secret until the connector and Evolution side are updated
with the same value.

## Clean Production Environment

The clean production backend must start with the public web origin configured:

```bash
COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com
COKE_EMAIL_AUTH_ENABLED=0
# Required only when COKE_EMAIL_AUTH_ENABLED is true.
RESEND_API_KEY=<resend-api-key>
EMAIL_FROM=noreply@keep4oforever.com
EMAIL_FROM_NAME=<optional-display-name>
```

Production backend startup fails without `COKE_PUBLIC_BASE_URL` because copied
friend links are user-visible public URLs and must not fall back to localhost.
`COKE_EMAIL_AUTH_ENABLED=0` is the current clean production setting: web
registration directly creates a logged-in, email-verified account; email
verification resend and password reset are disabled. When
`COKE_EMAIL_AUTH_ENABLED` is true, production startup also fails without
`RESEND_API_KEY` because email verification, password reset, and claim emails
are sent synchronously by `coke-api` through Resend.
`EMAIL_FROM` defaults to `noreply@keep4oforever.com`; set `EMAIL_FROM_NAME`
only when the sender display name should be formatted as `"Name" <address>`.
The canonical compose deployment writes this value alongside
`NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_COKE_WEB_URL`.

The canonical clean deploy keeps `interaction` on Z.AI GLM while routing the
safe stateless text roles through DeepSeek V4: `planner` uses
`deepseek-v4-pro`, and `detector` plus `express` use `deepseek-v4-flash`.
`scripts/deploy-compose-to-gcp.sh` writes `COKE_PLANNER_PROVIDER`,
`COKE_PLANNER_MODEL`, `COKE_DETECTOR_PROVIDER`, `COKE_DETECTOR_MODEL`,
`COKE_EXPRESS_PROVIDER`, and `COKE_EXPRESS_MODEL` into the clean runtime `.env`.
The script requires `DEEPSEEK_API_KEY` because those roles are production
traffic.

`scripts/deploy-compose-to-gcp.sh` preserves `COKE_EMAIL_AUTH_ENABLED`,
`RESEND_API_KEY`, `EMAIL_FROM`, and `EMAIL_FROM_NAME` from the existing clean
`.env` on every deploy. If `COKE_EMAIL_AUTH_ENABLED` is absent, the script
writes `0`. It aborts for a missing `RESEND_API_KEY` only when email auth is
enabled. Before re-enabling email delivery, seed `RESEND_API_KEY` (the active
Resend key) into the remote clean `.env` (`<remote-root>/.env`).

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
