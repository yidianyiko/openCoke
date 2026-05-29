# ClawScale Adapter Notes

This document is retained as a compatibility reading path for tasks that still
look for ClawScale or bridge operations. The clean-rebuild target supersedes the
standalone bridge runtime.

## Current Target

The standalone ClawScale bridge is superseded. ClawScale remains only as the
`wechat_personal` provider adapter behind Coke's canonical provider contract.

Future clean-rebuild services:

- `coke-api`: Python ingress/egress HTTP tier.
- `coke-worker`: Python Redis Stream turn workers.
- `coke-scheduler`: singleton Python reminder scheduler.
- `coke-outbox-relay`: Postgres outbox to Redis Stream relay.
- `coke-web`: Next.js thin client.
- `postgres`: product state, Agno session/history/memory/knowledge, pgvector.
- `redis`: wake-up stream, locks, reply pub/sub.

## Adapter Boundary

ClawScale is no longer a first-class runtime module. It contributes exactly one
provider adapter:

- inbound personal WeChat webhook normalization
- outbound personal WeChat send calls
- provider-specific connection/status mapping
- provider error mapping into user-safe channel states

Everything else belongs to Coke-owned contracts:

- account identity and channel identity: IdentityAccess
- connection state, delivery route, and delivery attempts: ChannelReachability
- conversation order, turns, and output disposition: ConversationRuntime
- reminders and fires: Reminder
- friendships, shared reminders, and notifications: SocialScheduling
- calendar import: CalendarImport

## Superseded Bridge Responsibilities

These responsibilities move into the Python backend or are deleted:

- bridge HTTP process and standalone port ownership
- bridge reply waiter
- bridge outbound dispatcher
- bridge callbacks into Gateway routes
- Gateway notification enqueue
- bridge-owned reminder or notification management
- Mongo-backed message/runtime state
- provider-specific business logic outside the adapter edge

The replacement path is provider webhook -> `coke-api` -> Postgres outbox ->
Redis wake-up -> `coke-worker` -> provider egress through `coke-api`.

## Operations

Do not add new runbooks that instruct future agents to operate a standalone
bridge process. Deployment and smoke checks should follow `docs/deploy.md` and
the clean-rebuild surfaces in `docs/fitness/coke-verification-matrix.md`.
