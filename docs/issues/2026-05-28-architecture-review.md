---
kind: progress_note
status: complete
surface:
  - worker-runtime
  - bridge
  - gateway-api
  - gateway-web
  - product-reminder
  - product-scheduling
  - deploy
  - repo-os
created_at: 2026-05-28
updated_at: 2026-05-28
---

# 2026-05-28 Coke Whole-System Architecture Review

## Meta

- **Method:** static review of `docs/ARCHITECTURE.md` + actual code, plus a
  read-only live probe of the production `gcp-coke` server. No load testing
  (out of scope per request).
- **Reviewer lens:** wshobson/agents `architect-review` agent definition
  (installed at `.claude/agents/architect-review.md`), applied by one
  foreground pass over the runtime core and seven parallel sub-agents over the
  remaining surfaces.
- **Coverage intent:** every code surface listed in `AGENTS.md` was inspected.
  See [§11 Coverage Map](#11-coverage-map) for the explicit scope and the
  residual blind spots.
- **Status:** this is a point-in-time snapshot, not an active issue tracker.
  Individual findings that warrant fixes should be promoted to their own
  `active_issue` records.

---

## 1. Executive Summary

Coke is a structurally sound, well-governed multi-process runtime. The Reminder
domain, the bridge trust boundary, and the repo-OS governance layer are genuine
strengths. The production server is healthy and idle-stable (zero container
restarts, zero errors in logs at probe time).

Three themes dominate the findings:

1. **Mongo is doing two jobs (state store + message bus) and the live metrics
   show the cost.** 26.6M requests / 17.75M queries / 1.47M connections created
   in ~5 days, with the worker's pymongo client setting no `appName`. This is
   the architecture's central scaling constraint (see [C1](#c1)).

2. **A large amount of "spec-present, integration-absent" code is being
   carried.** Seven independent surfaces have fully-built subsystems that are
   never wired into a live path: OrderDAO billing, quota enforcement, the Agno
   media tools, the memo-runtime adapter, Focus `multi_candidate`
   disambiguation, the `clawscale-cli-bridge` package, and several `UserDAO`
   stubs. This directly contradicts the working-contract rule that "code must
   carry only the current product and architecture contract" (see
   [§7](#7-cross-cutting-spec-present-integration-absent)).

3. **`docs/ARCHITECTURE.md` understates Postgres.** Live state shows Postgres is
   the multi-tenant control plane (tenants, customers, subscriptions,
   identities, delivery_routes, agent_bindings, ai_backends), not the
   "gateway state" the doc implies (see [§9 Drift](#9-doc--code-drift)).

The codebase is more mature than its risks suggest; most Critical/High items are
about scale headroom and carrying-cost, not active breakage.

---

## 2. System Overview

Coke is a ClawScale-backed personal-assistant supervision runtime. Three
top-level processes, three datastores:

- **Worker runtime** (`agent/runner/agent_runner.py`): N asyncio workers
  (10 in production) poll MongoDB `inputmessages`, take a per-conversation lock,
  build a Focus + trusted-blocks context, and run a single Agno `Agent` per turn
  (`agent/agno_agent/runtime/agent_runtime.py`). The same process boots one
  in-process Reminder Runtime (APScheduler) and a background handler loop.
- **ClawScale Bridge** (`connector/clawscale_bridge/app.py`, Flask + gunicorn,
  single `gthread` worker, `127.0.0.1:8090`): validates `/bridge/internal/*`
  requests, normalizes inbound payloads into Mongo `inputmessages`, waits
  synchronously for replies via Mongo polling (`reply_waiter`), promotes late
  replies, and dispatches `outputmessages` back to Gateway `/api/outbound`.
- **Gateway** (`gateway/packages/api`, Hono/TS `:4041`; `gateway/packages/web`,
  Next.js 16 `:4040`): customer/admin auth, channel management, the
  shared-reminder / friend-link scheduling domain, provider webhook
  normalization, and the multi-tenant control plane.

Datastores (confirmed live):

- **MongoDB 7.0** (`mymongo`) — Coke runtime state **and** the message bus.
- **Postgres 17** (`clawscale`) — the multi-tenant control plane (ClawScale
  tenancy, subscriptions, delivery routes) and scheduling-domain state.
- **Redis 7.2** — present but `dbsize=0`; effectively unused dead weight.

---

## 3. Live Production State (gcp-coke, probed 2026-05-28 02:27 UTC)

Read-only probe over SSH; no state mutated.

- **Host:** `coke-server`, GCP e2-standard-2 (2 vCPU / 7.8 GiB), up 89 days.
  Compose root `/home/whoami/coke/docker-compose.prod.yml`.
- **Two compose projects share the host:** `coke` (6 containers) and
  `evolution` (WhatsApp Evolution API + its own pg15/redis), stitched together
  only through host `127.0.0.1` ports, not a shared docker network.
- **coke containers:** `coke-agent` (worker, no published ports, restarts 0),
  `coke-bridge` (single gthread gunicorn, healthy), `coke-gateway` (Hono+Next),
  `mongo:7.0`, `postgres:17-alpine`, `redis:7.2-alpine`. App tier redeployed
  cleanly ~55 min before probe; data tier stable ~5 days.
- **Resources:** load 1.09 / 0.82 / 0.76 on 2 vCPU; 2.0 GiB used / 4.4 GiB free;
  **no swap configured**; disk `/` at **77% (12 GiB free)**. Per-container RSS
  tiny (gateway 121 MiB, agent 120 MiB, mongo 383 MiB, bridge 65 MiB).
- **Mongo metrics:** `connections.current=183` / `available=226`;
  `totalCreated=1,470,812` in ~5 days; 26.6M requests, 17.75M queries, 536K
  updates, 815 inserts; `globalLock.activeClients=0` (no contention);
  **`asserts.user=3,528,127`** since 05-23; the pymongo driver sets **no
  `appName`** (≈201 unnamed connections in `currentOp`).
- **Mongo collection sizes (`mymongo`, 30 MB total):** largest are
  `embedding_cache` 1101, `outputmessages` 1010, `usage_records` 800,
  `embeddings` 773, `inputmessages` 416, `reminders` 123. Nothing near 1M;
  `locks`, `agent_instances`, `user_profiles`, `pending_workflows` all 0.
- **Postgres (`clawscale`, 12 MB):** `messages` 493, `outbound_deliveries` 256,
  `subscriptions` 76, `customers` 73, `tenants` 68, `ai_backends` 68,
  `identities` 67, `delivery_routes` 32, etc. Runs solely as role `clawscale`
  (no `postgres` superuser role — benign but non-standard).
- **Redis:** `PING`=PONG, `dbsize=0`, `connected_clients=1`. Confirms unused.
- **Logs:** agent, bridge, gateway, nginx error log all clean — zero
  ERROR/WARN over the sampled window; stack is idle-healthy. nginx access log
  is dominated by internet scanner noise (`.env`/cred probes, `/shell?...`),
  not real product load.

---

## 4. Architecture Strengths

1. **Reminder domain is a real port.** `agent/reminder/runtime_contract.py` is a
   genuine contract boundary; Agno tools, bridge HTTP routes, PostAnalyze
   follow-ups, and Calendar Import all call it instead of touching
   `ReminderDAO`. Honors `docs/design-docs/agent-capability-contract.md`.
2. **Reminder lifecycle is atomic + idempotent.** `dao/reminder_dao.py:221-248`
   compare-and-sets on `(_id, next_fire_at, lifecycle_state)`;
   `ReminderScheduler._execute_job` (`reminder_scheduler.py:91`) revalidates
   `expected_next_fire_at`; `ReminderFireEventHandler.handle`
   (`reminder_event_handler.py:69-83`) skips replays that already produced
   output.
3. **Scheduling domain (Gateway) has disciplined consistency.** `$transaction`
   for multi-row create (`shared-reminder-service.ts:951-993`) and cancel
   (`:1085-1106`); compare-and-swap via conditional `updateMany`; idempotency
   via unique constraints (`SharedReminder @@unique([creatorAccountId,
   idempotencyKey])` at `schema.prisma:730`) plus deterministic SHA-256 ids
   (`shared-reminder-service.ts:445-447`).
4. **Bridge inbound trust boundary.** `_trusted_coke_account_id`
   (`app.py:408`) requires a coherent identity tuple before any enqueue;
   `_normalize_inbound` collapses 6+ alias shapes into one trusted form — a
   textbook anti-corruption layer.
5. **Lock safety primitives.** `dao/lock.py:118-159` (`release_lock_safe`) and
   `runtime_lock.verify_lock_ownership` (`runtime_lock.py:77`) make the
   dual-worker race explicit and refuse to release another worker's lock.
6. **Repo-OS governance is unusually strong.** `AGENTS.md` +
   `docs/design-docs/index.md` + `docs/fitness/surfaces.yaml` +
   `scripts/guardrails.py` make boundary decisions auditable. Eval tooling is
   cleanly decoupled — product code never imports `scripts/`, `tests/`, or
   `tools/`.
7. **Network posture is tight.** Every service binds `127.0.0.1`; only nginx
   80/443 is public; Mongo/Postgres/Redis are not host-published. Secrets are
   `${ENV_VAR}` placeholders — nothing credential-bearing is committed.

---

## 5. Production Topology Note: Postgres Is First-Class

The static model (and `ARCHITECTURE.md`) frames storage as "Mongo = bus +
state, Redis optional, Postgres = gateway state." The live probe corrects this:

- **Postgres is the multi-tenant control plane.** Tables `tenants`, `customers`,
  `subscriptions`, `identities`, `agent_bindings`, `ai_backends`,
  `memberships`, `delivery_routes`, `end_users` are the system of record for
  *who can use Coke and how messages are delivered* — load-bearing for every
  inbound/outbound turn, not a side surface.
- **Mongo is the runtime/bus**; **Redis is dead weight** (`dbsize=0`).

Any future capacity or DR planning must treat Postgres as a tier-1 dependency.

---

## 5.1 Addendum: ClawScale, Data Ownership, And Chat Output Ownership

This note captures a follow-up architecture discussion after the shared-reminder
receiver notification incident.

The short version: **ClawScale and the Postgres/Mongo split are real sources of
architecture debt, but the immediate product-notification bug is caused more
directly by dual chat-output ownership than by dual databases.**

### ClawScale Debt Assessment

ClawScale was integrated to save early development effort. That was a rational
trade at the time: it avoided building channel identity, inbound/outbound
protocols, delivery-route binding, and provider-specific webhook handling from
scratch.

The debt now shows up because Coke has grown its own product and channel
surface around the same concepts:

- account identity exists in Coke customer/platform state and in bridge-facing
  ClawScale identity fields
- conversation identity exists as runtime conversation ids, business
  conversation keys, and provider conversation/end-user ids
- outbound delivery state exists in Gateway delivery records, Mongo
  `outputmessages`, and product notification records
- product-triggered chat messages can currently be produced by Gateway prose or
  by the Interaction Agent

That does not make ClawScale an immediate negative asset. It still carries live
channel routing and delivery. But it should be treated as **strategic debt to
shrink into an adapter**, not as the center of Coke's product architecture.

The desired direction is:

```text
Coke canonical message contract
  -> ClawScale / provider adapters
```

not:

```text
ClawScale semantics
  -> product/runtime behavior scattered across Coke
```

New product behavior should depend on Coke-owned contracts first. ClawScale
fields should be adapter inputs/outputs, not product truth.

### Why Not One Database Immediately?

The dual-store architecture is uncomfortable, but the current evidence does not
support a rushed "move everything into one database" fix.

Moving all runtime state to Postgres would simplify relationships among
customers, delivery routes, shared reminders, product notifications, generated
outputs, and delivery attempts. It would also make notification threading and
delivery status easier to query transactionally.

But Mongo currently carries more than cache data:

- `inputmessages` and `outputmessages`
- conversation locks
- Agno session/history state
- reminder runtime wake-up and fire evidence
- worker polling and replay evidence

Moving those into Postgres would be a worker-runtime, bridge, reminder,
scheduler, test, and operations migration. That is a separate architecture
program, not the right immediate fix for chat notification wording.

Moving Gateway product/platform state into Mongo is less attractive. Customer,
channel, delivery route, friendship, shared reminder, subscription, and product
notification state benefit from relational constraints, unique indexes,
migrations, and queryability. Moving that state to Mongo would remove one
physical datastore but push integrity rules into application code.

The better near-term rule is **logical single ownership, not physical single
storage**:

- Postgres owns product facts and notification ledger state.
- Mongo owns runtime transcript and execution evidence.
- Interaction Agent text is derived expression, never product truth.

### Immediate Root Cause: Dual Chat-Visible Message Owners

The product-notification issue exists because Coke has two paths that can create
final text visible in user chat:

1. Interaction Agent path:

   ```text
   agent runtime -> Mongo outputmessages -> bridge output dispatcher -> Gateway /api/outbound
   ```

2. Gateway product-notification direct push path:

   ```text
   Gateway product_notifications.payload.text -> Gateway /api/outbound
   ```

The second path bypasses the Interaction Agent. That is why the shared-reminder
receiver saw fixed phrasing instead of receiver-agent generated text.

The immediate fix should remove Gateway as a final chat-prose owner for
chat-visible product notifications. Gateway may create immutable notification
facts and own lifecycle state, but it should not write the final text users see
in chat.

### Context Consistency Rule

When a user replies after receiving a product notification, trusted context
should come from structured product-notification facts, not from the previous
LLM text.

The authoritative chain should be:

```text
Postgres product_notifications facts
  -> system turn payload
  -> Interaction Agent generated text
  -> Mongo outputmessages evidence with notification_id
  -> outbound delivery
  -> idempotent Gateway delivered callback
```

One `notification_id` should connect all records. Mongo may store
`notification_id`, `facts_hash`, and output references for replay and audit, but
Postgres remains the source of product facts. If LLM wording omits or changes a
detail, later trusted context must still use the Postgres facts.

### Debt Split

Immediate fix:

- unify chat-visible message generation through the Interaction Agent
- stop Gateway from sending final product-notification prose directly
- keep Postgres as product notification ledger owner
- keep Mongo as runtime output evidence owner
- add idempotent delivery-state reconciliation instead of direct worker writes
  to Postgres

Medium-term debt:

- formalize a Postgres-to-runtime system event/outbox pattern
- replace `product_notifications.payload.text` with structured facts and a
  facts hash for migrated chat notifications
- make product notification delivery status explicit enough to distinguish
  generation, outbound delivery, and callback/reconciliation failures

Long-term debt:

- evaluate whether Coke should become Postgres-first for runtime messages,
  locks, generated outputs, and reminder wake-up state
- shrink ClawScale into a replaceable adapter behind Coke-owned message and
  delivery contracts
- retire duplicate channel/conversation identity concepts that remain only for
  historical integration compatibility

---

## 6. Risks by Severity

### CRITICAL

<a id="c1"></a>
**C1. MongoDB is both message bus and state store, polled by every process —
and the live metrics show the cost.**
`entity/message.py:22-36` (`read_top_inputmessages`), `dao/lock.py:32-90`
(poll-and-insert lock + `delete_many` of expired locks on every attempt at
`:64-66`), `connector/clawscale_bridge/reply_waiter.py` (Mongo polling for
synchronous replies), and `output_dispatcher.py:54-59` (`find_one_and_update`
claim) all use Mongo as a queue. Live evidence: 17.75M queries and 1.47M
connections created in 5 days on an idle-traffic system; `/bridge/inbound` tail
latency is polling-bound, not LLM-bound (`app.py:480-489`). Redis is wired
(`util/redis_stream.py`) but `dbsize=0`.
**Direction:** promote Redis Streams to the primary work-wake signal; keep Mongo
as state of record only; convert `reply_waiter` to pub/sub keyed by
`causal_inbound_event_id`. This is the single highest-leverage change.

**C2. Bridge is single-process / single-worker by deployment.**
`docker-compose.prod.yml:99-101` runs gunicorn `--workers 1 --threads 8` (live:
single `gthread` worker confirmed). The bridge holds in-memory `ReplyWaiter`
callbacks, a per-request `LateReplyFallbackPromoter` thread (`app.py:91`), and
the background `_start_output_dispatcher` thread (`app.py:655-667`) in the same
process. Horizontal scale-out is currently impossible without externalizing
those structures.
**Direction:** make `ReplyWaiter` poll-driven/stateless; run the output
dispatcher as the standalone process it already supports (`python -m
connector.clawscale_bridge.output_dispatcher`); document `coke-bridge` as a
1-replica service until then.

### HIGH

**H1. Per-DAO `MongoClient` instances; no shared pool — confirmed live.**
`dao/mongo.py:34`, `dao/lock.py:25`, `dao/conversation_dao.py:97`,
`dao/agent_instance_dao.py:57`, `dao/reminder_dao.py:26`, `dao/user_dao.py:150`,
`dao/usage_dao.py:25`, `dao/order_dao.py:24`, plus module-level singletons in
`entity/message.py:8` and `agent/runner/agent_handler.py:93` each build their
own client. Live symptom: 183 connections with **no `appName`** and 1.47M
lifetime connections. Fragmented pools, no shared timeout/retry/write-concern,
and zero per-component observability in Mongo.
**Direction:** single injected `MongoClientFactory` with a shared pool, standard
timeouts, and a per-component `appName`.

**H2. The Interaction Agent runtime is a 2,472-line module.**
`agent/agno_agent/runtime/agent_runtime.py` carries ~50 module-level helpers
(intent normalization, focus binding, scheduling arg splitting, envelope
parsing, lenient JSON recovery at `:1167`, guardrails, trace emission). It is
the file most affected by every product change.
**Direction:** extract intent normalization, focus resolution, envelope
parsing/guardrails, and scheduling dispatch into sibling modules; keep
`agent_runtime.py` as orchestration.

**H3. `handle_message` orchestration is a long pipeline with repeated rollback
exits, and compensation is reminder-only.**
`agent/runner/agent_handler.py:262-559` repeats the
`verify_lock_ownership → _compensate_rolled_back_domain_writes → return` triplet
at five exits (`:397-419`, `:428-437`, `:489-516`). Note `ARCHITECTURE.md:268-275`
*correctly* says the implementation concerns are split into
`rollback_detection.py`, `runtime_lock.py`, `message_history.py`, and
`output_delivery.py` — but the orchestrator body itself still inlines the
multi-exit rollback logic, and compensation only cancels reminders created in
the rolled-back turn (`_rolled_back_visible_reminder_create_ids` at `:211`). It
does **not** undo shared-reminder, friendship, or agent_instance writes. The
Gateway scheduling domain has the symmetric hazard: `createSharedReminder`
creates runtime projections over the network *before* the DB transaction with
hand-rolled best-effort compensation that swallows errors
(`shared-reminder-service.ts:919-1038`, `:516-518`) — a distributed write
reconciled by best-effort cleanup, not a true saga.
**Direction:** a per-turn compensation outbox that any domain registers into, on
both sides of the bridge.

**H4. Lock timeout vs LLM walltime is brittle.**
`runtime_lock.LOCK_TIMEOUT = 180s`, heartbeat default 60s
(`runtime_lock.py:15-21`), Agno runtime default 100s (`agent_runtime.py:64`). A
stalled heartbeat can expire the lock mid-write; recovery then runs the
reminder-only compensation (see H3). No admission control throttles new workers
when heartbeats fall behind.
**Direction:** derive heartbeat interval from `LOCK_TIMEOUT`; instrument
lock-loss; gate worker concurrency on heartbeat success rate.

**H5. Two asymmetric scheduling domains, one undocumented latency surface.**
The Agent calls the Gateway scheduling domain over HTTP
(`agent/agno_agent/capabilities/scheduling.py:60-78`; `requests.Session`, 10s
timeout, **no retry / no circuit-breaker** at `:67-72`), while the Reminder
domain is in-process Python. The runtime must reason about two failure models
(timeout/5xx vs exception). Intentional (Gateway owns Postgres) but
undocumented.
**Direction:** document the dual-domain model in `ARCHITECTURE.md §4`; add a
circuit-breaker around `SchedulingGatewayClient`.

**H6. No server-side auth on the web frontend; tokens in `localStorage`.**
`gateway/packages/web` has no `middleware.ts` and no server session. Bearer
tokens live in `localStorage` (`lib/customer-auth.ts:4-6`, `lib/admin-auth.ts:11-12`);
route protection is a client `useEffect` redirect (`admin/layout.tsx:38-42`).
Every protected page's HTML ships before any auth check, and tokens are
XSS-exposed. Admin and customer share one bundle/port with two diverged API
clients (admin auto-logs-out on 401 at `lib/admin-api.ts:157-167`; customer does
not).
**Direction:** enforce auth at the edge (middleware or RSC) for admin routes at
minimum; move tokens to httpOnly cookies; consider splitting the admin surface.

### MEDIUM

**M1. `entity/message.py` is a single file masquerading as a domain.** 179 lines
of functions over a `_mongo = MongoDBBase()` module singleton; neither entity
nor DAO. Callers across the worker import it directly.
**Direction:** fold into a real `InputMessageDAO` under `dao/` with DI.

**M2. Dead vector code in `dao/mongo.py`.** `VectorDB`/`VectorUtils` and a
brute-force Python `vector_search` (`:267-315`, `:372-602`) have no production
caller; the embedding cache the runtime *does* use lives in collections
(`embedding_cache` 1101, `embeddings` 773), not this class. Carrying-cost code.

**M3. Bridge + scheduling auth are single shared static keys.**
`connector/clawscale_bridge/auth.py` checks one `COKE_BRIDGE_API_KEY` for all
`/bridge/internal/*`; Gateway internal scheduling checks one
`CLAWSCALE_IDENTITY_API_KEY` for all `/api/internal/scheduling/*`
(`internal-scheduling-routes.ts:27-30`); outbound uses a third
`CLAWSCALE_OUTBOUND_API_KEY`. No per-caller scoping, rotation story, or replay
protection. Localhost binding is the only mitigation.
**Direction:** per-caller identities/keys; document the trust boundary in
`docs/clawscale_bridge.md`.

**M4. Friend-name resolution uses regex token boundaries.**
`friend-target-resolver.ts:59-92` resolves a user-supplied `friend_name` to an
account via normalized exact match then `\b`-boundary regex (`:63`). Given the
"no keyword/regex routing" contract, regex-based identity resolution inside the
trusted internal layer is risk-adjacent, and ambiguity collapses to HTTP 400.

**M5. Synchronous network I/O entangled with DB writes (Gateway).**
`enqueueProductNotification` performs the `/api/outbound` `fetch` and status
update inline with the write path (`notification-service.ts:240-270`). A slow or
down delivery target stalls the scheduling write.

**M6. Unbounded trace/evidence growth.** `emit_agent_turn_trace_jsonl`
(`agent/agno_agent/runtime/trace.py:344-345`) appends JSONL with no rotation,
retention, or size cap. `artifacts/evidence/` is already **525 MB** locally
(522 MB in `shared-reminder-agent-smoke/`, single 92 MB dumps). Gitignored, so
no repo bloat, but local disk grows without bound — relevant given the live box
is at 77% disk.

**M7. No structured cross-process tracing.** `AgentTurnTrace`
(`trace.py:178-195`) is solid within the worker, but the bridge logs via ad-hoc
f-strings and correlation relies on `causal_inbound_event_id` plumbed through
Mongo docs. No W3C traceparent / OpenTelemetry across the bridge→worker→reminder
edges.

**M8. No worker liveness probe + no swap.** `coke-agent` has no healthcheck
(`docker-compose.prod.yml:41-64`) — a hung-but-not-crashed worker is neither
detected nor restarted. The host has **no swap** on 8 GiB, so a single spike
OOM-kills with no cushion. Together these are the top operational fragility.

### LOW

- **L1. Three start mechanisms.** systemd (prod), pm2 (dev-only per
  `deploy.md:8`), and `start.sh` (tri-mode) all exist. The systemd unit
  hardcodes `User=whoami` / `/home/whoami/coke` (`coke-compose.service:10-13`) —
  `whoami` is a literal username, consistent with the deploy script but fragile.
- **L2. Edge has no auth/rate-limit/WAF.** nginx proxies `/api/`, `/bridge/`,
  `/user/`, `/bind/` straight to backends and blindly sets `X-Forwarded-For`
  (`deploy/nginx/coke.conf:19-21`). All access control is in the apps; scanner
  traffic already hits the box continuously.
- **L3. Mutable `:latest` provider image.** `deploy/evolution/docker-compose.yml:3`
  pins `evoapicloud/evolution-api:latest` — rebuilds can silently change the
  WhatsApp provider behavior.
- **L4. Chinese inline comments/logs** in `agent/runner/*.py`, `dao/lock.py`
  (e.g. `agent_handler.py:402,484`), and `connector/terminal/*` conflict with
  the English-specs preference and hamper non-Chinese trace reading.
- **L5. `handler = create_handler(0)` compat singleton** at
  `agent/runner/agent_handler.py:679` — working contract forbids shims.
- **L6. 61 tracked files under gitignored `artifacts/evidence/`** (41 zero-byte
  `_state-*.json` placeholders) — committed before `.gitignore:190` landed; they
  contradict the "evidence is generated, not committed" intent and confuse
  `review-trigger`'s `evidence_gap` logic.
- **L7. Bake-off mutates global `CONF`.** `compare_reminder_detect_models.py:135-143`
  save/restores `CONF["llm"]["roles"]["reminder_detect"]`, which
  `model_factory.create_llm_model` (`:37`) reads as a mutable global — no
  immutable per-call model override exists.
- **L8. Mongo `asserts.user=3.5M`** since 05-23 — not surfacing in logs, likely
  non-fatal command/auth asserts, but high enough to warrant a deeper Mongo
  audit.

---

## 7. Cross-Cutting: Spec-Present, Integration-Absent

The most important *systemic* finding. Seven independent subsystems are fully
built (often well-tested in isolation) but never reach a live code path. The
working contract states code must carry only the current product/architecture
contract, so each is either a deletion candidate or a documented-as-dormant
exception.

| Subsystem | Built | Live wiring | Evidence |
|---|---|---|---|
| **memo-runtime** | Full contract + PG/pgvector schema + 7 test files | **None** — sole adapter `agent/agno_agent/capabilities/memo.py:71` injects `storage=None` → `MemoStorageUnavailable` at `contract.py:723`; not in `capabilities/__init__.py`; not in `requirements.txt` | a80f |
| **Agno media tools** | `voice_tools.py` / `image_tools.py` `@tool` wrappers over `framework/tool/*` | **None** — live agent builds `final_tools = domain_tools + utility_tools` (`agent_runtime.py:977,985`); media tools never registered | aace |
| **OrderDAO billing / access-gate** | `dao/order_dao.py`, `UserDAO.update_access/revoke_access` | **None** — only test callers | aace |
| **Quota enforcement** | `UsageDAO` records usage | **None** — no `check_quota`/gate anywhere; usage recorded, never enforced | aace |
| **Focus `multi_candidate`** | Prisma `SchedulingFocusBinding`/`Candidate`, runtime contract path | **Stub** — `focus-binding-service.ts:63-69` hardcodes `none_actionable`; `bindAgentFocusSelection` always `ok:false` | a69f |
| **clawscale-cli-bridge** | `dist/` build artifact | **Dead** — no `src`/`package.json`, not a workspace member, zero refs | a69f |
| **UserDAO stubs** | `update_user`, `delete_user`, `change_status`, `get_user_by_phone/email` | **No-op** — return `False`/`None`, callers can't tell "unimplemented" from "failed" (`user_dao.py:281-294`) | aace |

The memo-runtime and Focus cases are the most consequential because
`ARCHITECTURE.md` describes them as if they were live (see Drift). Recommend a
single decision per row: **wire, delete, or mark dormant in the doc.**

---

## 8. Layer Notes

### 8.1 Gateway API + Prisma (scheduling domain)
Flat, DI'd, Hono-free service functions dispatched by
`scheduling/domain-contract.ts`. Domain model: `UserLink`, `LinkSession`,
`Friendship`, `SharedReminder`, `SharedReminderEvent`, `ReminderProjection`,
`ProductNotification`, `SchedulingFocusBinding/Candidate`. The 10 tool names at
`ARCHITECTURE.md:256-259` match `domain-contract.ts:99-235` exactly (accept/reject
and block/unblock confirmed retired — no drift). Main weakness: all validation
errors collapse to HTTP 400 (`domain-contract.ts:93`), so distinct conditions
(`friend_name_ambiguous`, `idempotency_conflict`, `receiver_time_conflict`) are
indistinguishable by status. `route-message.ts` (907 lines) exists and matches
its `:124` doc description.

### 8.2 Gateway Web
Next.js 16.2.1 App Router + React 19.2.4, Tailwind v4. No NextAuth, no
SWR/react-query, no state store, no form lib — React hooks + two hand-rolled
fetch clients. Deploy target is `next start` server mode
(`gateway/Dockerfile:26`); `out/` is a stale static-export leftover. The
2026-05-22 navigation incident traced to `LocaleProvider` mutating a
server-rendered `#locale-splash` node (`layout.tsx:40-46`); that SSR/hydration
seam is still load-bearing. See H6 for the auth concern.

### 8.3 memo-runtime
Contract-first PG/pgvector bounded context; internally well-tested. Embeddings
are vestigial — `vector(1536)` column and `memo_embeddings` table exist but
nothing writes them and `search_cards` is pure keyword match (`search.py:37-44`).
Introduces a second datastore technology for zero live benefit today. See §7.

### 8.4 Billing / User DAOs
All pure Mongo, canonical (not shadow) state; no Mongo↔Postgres sync. `UserDAO`
splits across `user_profiles` + `coke_settings`. Timezone/usage writes come from
the worker, not the bridge. Dead billing/quota paths covered in §7.

### 8.5 connector/terminal/
Dev/test seam: `terminal_test_client.py` (E2E) and `terminal_chat.py` (REPL)
write **directly** to Mongo `inputmessages` + Redis stream, bypassing the bridge
trust model entirely (`terminal_chat.py:96-104`). Hardcoded user/character
ObjectIds (`:32-34`) and a swallow-all `except Exception: pass` in the poll loop
(`:157-158`). Not imported by any runtime module, so risk is confined to whoever
runs it against a live DB.

### 8.6 framework/tool/
Not a registry/plugin/adapter — zero `__init__.py`, four flat vendor-call
modules (MiniMax TTS, Aliyun ASR, LibLib t2i, Ark i2t) with hardcoded model IDs
and import-time client construction (`ark.py:11-16`). **No timeouts/retries** on
any vendor `requests.post` (`minimax.py:51`, `liblib.py:61,75`) and unguarded
response parsing (`minimax.py:67`). Adapter layer (`agent/agno_agent/tools/`)
exists but is dead wiring (§7). A `liblib.py:174-177` `__main__` block ships an
explicit NSFW demo prompt — should be removed.

### 8.7 Eval / Trace
`AgentTurnTrace` v1 hashes input text (no raw content), carries a `durable_write`
flag, and is redaction-profiled by env (`server`→metadata+hashed,
`trace.py:210-211`). Harnesses: `scripts/reminder_eval/` (e2e),
`compare_reminder_detect_models.py` (the GLM-5.1 bake-off),
`agent_turn_trace_analyzer.py`, `tools/agent_smoke/` (two-user live smoke).
Corpus `reminder_test_cases.json` = 1892 cases; runs use a 30-50 subset.
Verification routing is two-layer: `surfaces.yaml` (path→surface) +
`verify-surface` (surface→pytest). Eval↔product coupling is clean. Concerns:
M6 (growth), L6 (tracked evidence), L7 (global CONF mutation).

### 8.8 Deploy
Production = `docker-compose.prod.yml` via `deploy/systemd/coke-compose.service`
(oneshot wrapper). nginx terminates TLS for `coke.keep4oforever.com` /
`coke.ydyk123.top`, routes to localhost upstreams. `scripts/deploy-compose-to-gcp.sh`
verifies the gateway submodule commit matches, rsyncs (excluding `.env`), and
**rebuilds only with `--restart`** — a bare run syncs files without restarting.
Concerns: M8 (no worker healthcheck / no swap), L1-L3.

---

## 9. Doc ↔ Code Drift

Reconciled against a full read of `docs/ARCHITECTURE.md`. The doc is broadly
accurate on topology; the real drifts:

1. **Postgres understated (significant).** `ARCHITECTURE.md:49` ("Postgres for
   gateway state") and `:349` ("Postgres audit state for import runs") undersell
   it. Live state shows it is the multi-tenant control plane (tenants,
   customers, subscriptions, identities, delivery_routes, agent_bindings). Fix:
   elevate Postgres to a tier-1 store in §1 and §8.
2. **Focus `multi_candidate` reads as live but is a stub.** `:223-230` describes
   ordinal/summary candidate selection; `focus-binding-service.ts:63-69` only
   ever returns `none_actionable` and `bindAgentFocusSelection` always fails.
   The "if a future…" hedge is there but the prose implies a working mechanism.
3. **memo-runtime reads as wired but isn't.** `:281-288` says adapters "must call
   the Memo Runtime Contract"; the only adapter is storage-less and
   unregistered. Mark as "spec present, integration absent."
4. **Redis is dead, not just optional.** `:48` lists it as "stream wake-up /
   trigger events"; `:131` softens to "only a wake-up path." Live `dbsize=0`
   means it carries nothing. Either wire it (C1) or note it as currently unused.
5. **Output dispatcher in-process vs separate process is ambiguous.** `:36-41`
   /§5 describe bridge outbound dispatch; code runs it as a daemon thread
   (`app.py:655`) *and* supports a standalone process
   (`docs/clawscale_bridge.md:72-78`). Doc should name the production choice.
6. **Drift by omission:** none of the §7 dead subsystems are acknowledged in the
   doc. Per the working contract this is both a doc gap and a code-hygiene
   issue.

Claims that are **accurate** (checked, no drift): `agent_runner.py` three
responsibilities (`:21-24`, `:144`); `agent_handler.py` split into four modules
(`:268-275`); the 10 scheduling tool names; accept/reject + block/unblock
retirement; `route-message.ts` description.

---

## 10. Evolution Path / Top Recommendations

1. **Decouple bus from store (C1).** Promote Redis Streams to the primary
   work-wake; convert `reply_waiter` to pub/sub. *Payoff: removes the polling
   tax that the live metrics quantify. Effort: L. Risk if skipped: latency floor
   and Mongo connection churn grow with worker count.*
2. **Resolve the dead-code inventory (§7).** One decision per row — wire,
   delete, or document-as-dormant. *Payoff: restores working-contract
   compliance, cuts onboarding confusion. Effort: M. Risk if skipped: continued
   drift and reviewer mistrust of the codebase.*
3. **Single `MongoClientFactory` with shared pool + `appName` (H1).** *Payoff:
   connection-budget control + per-component Mongo observability. Effort: S.*
4. **Generalize rollback compensation into a per-turn outbox (H3), both sides of
   the bridge.** *Payoff: closes the silent-leak hazard for non-reminder domain
   writes. Effort: M.*
5. **Operational hardening (M8): add a `coke-agent` healthcheck and configure
   swap on gcp-coke; add disk-usage alerting at 77%.** *Payoff: removes the top
   production fragility. Effort: S.*
6. **Edge + token hardening (H6, L2): server-side auth for admin routes,
   httpOnly cookies, basic rate-limiting at nginx.** *Payoff: closes the
   client-only-auth gap. Effort: M.*
7. **Reconcile docs (§9): elevate Postgres, mark Focus/memo as
   integration-absent, name the output-dispatcher production mode.** *Payoff:
   working-contract compliance. Effort: S.*

C1, §7, and M8 are the recommended first three.

---

## 11. Coverage Map

Every surface in `AGENTS.md`'s repository map was inspected this round.

**Covered (with file/line evidence):**
- Worker runtime — `agent/runner/*`, `agent/agno_agent/runtime/*`,
  `agent/reminder/*`, `agent/agno_agent/capabilities/*`
- Bridge — `connector/clawscale_bridge/*`, `connector/terminal/*`
- Gateway API + Prisma — `gateway/packages/api/src/scheduling/*`,
  `src/lib/route-message.ts`, `prisma/schema.prisma`,
  `gateway/packages/clawscale-cli-bridge`
- Gateway Web — `gateway/packages/web/*`, `gateway/packages/shared/*`
- Persistence — `dao/*`, `entity/message.py`
- Tooling framework — `framework/tool/*`
- memo-runtime — `memo-runtime/memo_runtime/*`, schema, tests
- Eval/trace — `scripts/*eval*`, `tests/eval*`, `tools/agent_smoke`,
  `agent/agno_agent/runtime/trace.py`, `docs/fitness/*`
- Deploy — `deploy/*`, `Dockerfile`, `docker-compose.prod.yml`,
  `ecosystem.config.json`, `scripts/deploy-compose-to-gcp.sh`
- Live runtime — gcp-coke (containers, resources, Mongo/PG/Redis metrics, logs)

**Residual blind spots (honest):**
- `gateway/packages/api/src/scheduling/shared-reminder-service.ts` internals
  read at the contract/transaction level, not every branch of its 1180 lines.
- Gateway Postgres **Prisma migration history** sampled (count + recent names),
  not each migration read.
- `gateway/packages/web` component-level UX correctness not verified in a
  browser (no UI run this round).
- `scripts/reset-gcp-coke.sh` not reviewed (referenced in `deploy.md:90`).
- **No load/perf testing** (out of scope per request); all scaling claims are
  inferred from code + idle-state live metrics, not measured under load.
- Mongo `asserts.user=3.5M` flagged but not root-caused (would need a deeper
  Mongo log/audit pass).

---

## Appendix: Method

Foreground pass (runtime core) + 7 parallel opus sub-agents over Gateway
API/Prisma, Gateway Web, memo-runtime, billing/terminal/framework Python,
eval/trace tooling, deploy artifacts, and a read-only gcp-coke probe. Reviewer
definition: `wshobson/agents` `architect-review` (installed at
`.claude/agents/architect-review.md`).
