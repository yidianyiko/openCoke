# Coke Clean Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Coke around the settled requirements matrix and clean target architecture: one Python backend, one thin Next.js client, Postgres + Redis, The Turn as the runtime spine, and six product-domain modules with no legacy compatibility surface.

**Architecture:** This is a destructive rebuild, not a migration. The implementation starts by correcting repository documentation so every later code task is constrained by the new contract, then builds the Python backend from bounded domains outward: IdentityAccess, ChannelReachability, ConversationRuntime, Reminder, SocialScheduling, CalendarImport, and the Agno-backed Turn runtime. Legacy Gateway API, Bridge, Mongo, compatibility paths, pending workflows, and fallback prose are deleted after replacement paths are verified.

**Tech Stack:** Python 3.12, Flask HTTP entrypoints, SQLAlchemy 2.x + Alembic migrations, Postgres + pgvector, Redis Streams/pubsub/locks, APScheduler, Agno 2.5.x, Pydantic v2, Next.js 16, TypeScript, Vitest, pytest.

---

**Plan Status:** complete (deployed + live-verified on gcp-coke at SHA d5ef1d0f, 2026-05-31)
**Status Date:** 2026-05-31
**Freshness Check:** Verify against current `main`, `docs/ARCHITECTURE.md`, the requirements matrix, the target architecture spec, and touched code before execution.

**Deploy + live-verification closeout (2026-05-31):** Implementation, the
runtime-readiness cutover, the selective legacy-prompt migration, and the P1/P2
security/route-parity backlog are all merged to `main` and deployed to
`gcp-coke` (`coke-clean`) at SHA `d5ef1d0f`. Live leader re-verification:
`/healthz=200`, web `/auth/login=200`, alembic `No new upgrade operations`,
`olivers`/`lizihao` logins 200, `wechat_personal` + `whatsapp_evolution`
channels `connected`, connector `connected_session_count=2`, worker error
count 0, webhook in transition mode (`COKE_WEBHOOK_INBOUND_SECRET` unset),
real-account inbound → `replied` + `sent`. Differential deploy + rollback-snapshot
removal are live. See [[2026-05-29-coke-clean-rebuild-e2e-closeout]] and
[[2026-05-30-coke-runtime-readiness]] for evidence.

**Completion evidence (2026-05-30):** All 13 tasks implemented and merged to `main`. Six bounded-context domains (IdentityAccess, ChannelReachability, ConversationRuntime, Reminder, SocialScheduling, CalendarImport), the Turn orchestration, and an integration composition root are in `coke/`. All legacy surfaces deleted with zero leftover (old Python runtime, both submodules, Mongo/pymongo, ClawScale bridge, TypeScript Gateway API; web extracted to `web/` as `@coke/web`). Verification: `tests/unit/coke` + `tests/integration/coke` = 318 passed; `zsh scripts/check` green; no-legacy-import guard passing.

**NOT yet done (out of original plan scope — runtime-readiness):** The system is unit/integration-verified with in-memory repositories and fake LLM/Redis/provider/Agno adapters. It is NOT yet a deployable running service: no Postgres-backed repository implementations wired, no live provider/Redis/Agno adapters, migrations not applied to a live DB, and no per-service Docker entrypoints (`docker-compose.prod.yml` worker/scheduler/outbox commands are structural placeholders). Production deploy to `gcp-coke` and real-account end-to-end testing require this runtime-readiness layer first; the existing `coke-agent-smoke` skill and `scripts/deploy-compose-to-gcp.sh` target the now-deleted legacy stack and must be rebuilt for the clean architecture.

**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

**Hard Execution Rule:** Task 1 is documentation-only and must be completed, verified, and committed before any source-code implementation task starts. The repository documentation must describe the rebuild target first, so implementation agents do not optimize around stale Gateway/Bridge/Mongo assumptions.

**Plan Package Rule:** This file is the master rebuild sequence. Task 1 is executable directly from this plan because it is the documentation gate. Before executing any code task from Task 2 onward, first write or review a focused child plan in `docs/superpowers/plans/` for that bounded slice, using the same source specs and current `main`. The expected child plans are:

- `2026-05-29-coke-clean-rebuild-backend-foundation.md`
- `2026-05-29-coke-clean-rebuild-schema.md`
- `2026-05-29-coke-clean-rebuild-identity-access.md`
- `2026-05-29-coke-clean-rebuild-channel-reachability.md`
- `2026-05-29-coke-clean-rebuild-conversation-runtime.md`
- `2026-05-29-coke-clean-rebuild-turn-runtime.md`
- `2026-05-29-coke-clean-rebuild-reminder-domain.md`
- `2026-05-29-coke-clean-rebuild-social-scheduling.md`
- `2026-05-29-coke-clean-rebuild-calendar-import.md`
- `2026-05-29-coke-clean-rebuild-web.md`
- `2026-05-29-coke-clean-rebuild-legacy-deletion.md`
- `2026-05-29-coke-clean-rebuild-e2e-closeout.md`

## File Structure

### Documentation Gate

- Modify `docs/ARCHITECTURE.md`: replace current ClawScale-backed topology with the clean target topology, The Turn pipeline, bounded contexts, storage topology, deletion list, and verification implications.
- Modify `docs/product-specs/FEATURE_TREE.md`: remap product/API surfaces to the current requirements matrix and the future Python API ownership.
- Modify `docs/roadmap.md`: align product/platform direction with the clean rebuild and remove stale phase language that contradicts the settled requirements.
- Modify `docs/clawscale_bridge.md`: mark the standalone bridge as superseded by provider adapters inside the Python ingress/egress tier.
- Modify `docs/deploy.md`: describe the future two-tier Python backend + Next.js + Postgres + Redis deployment target.
- Modify `docs/design-docs/coke-working-contract.md`: add clean-rebuild planning surfaces and remove Bridge/Gateway as future ownership systems.
- Modify `docs/design-docs/interface-contract.md`: define the future route namespace for Python API, public web, provider webhooks, internal worker callbacks, and web-claim handoff.
- Modify `docs/design-docs/data-retention-policy.md`: align retention categories with Postgres-only product domains and generated evidence.
- Modify `docs/fitness/coke-verification-matrix.md` and `docs/fitness/surfaces.yaml`: add clean-rebuild surfaces and route verification to docs, backend, worker, web, and deploy gates.
- Create `scripts/e2e/clean-rebuild-canonical-doc-sync.sh`: guardrail that fails when canonical docs claim Mongo, standalone Bridge, TypeScript Gateway API ownership, pending approvals, or fallback prose as current rebuild targets.

### Python Backend Target

- Create package `coke/`.
- Create `coke/app.py`: HTTP application factory.
- Create `coke/config.py`: typed environment configuration.
- Create `coke/infra/postgres.py`: shared Postgres engine/session factory.
- Create `coke/infra/redis.py`: shared Redis client factory.
- Create `coke/infra/outbox.py`: transactional outbox repository and relay contract.
- Create `coke/infra/tracing.py`: W3C traceparent/OpenTelemetry propagation helpers.
- Create `coke/domains/identity_access/`: account, access gate, activation, credentials, sessions, channel identity, auth artifacts.
- Create `coke/domains/channel_reachability/`: channel, delivery route, delivery attempt, provider adapter contract.
- Create `coke/domains/conversation_runtime/`: conversation, message, inbound media, turn, output disposition, stale-safety state.
- Create `coke/domains/reminder/`: reminder, reminder fire, recurrence, scheduler, calendar read model.
- Create `coke/domains/social_scheduling/`: friend link, friendship, shared reminder, projections, notification facts and recipients.
- Create `coke/domains/calendar_import/`: Google authorization handoff, import runs, per-occurrence import items.
- Create `coke/turn/`: trigger intake, pre-LLM gate, context assembly, semantic interpreter, focus, reference resolver, freshness, memory manager, agent invocation, output validation, disposition recording.
- Create `coke/providers/`: `whatsapp_evolution`, `wechat_personal`, `wechat_ecloud`, and `linq` adapters behind one inbound/outbound provider interface.
- Create `coke/api/`: customer routes, public routes, provider webhook routes, internal runtime routes.
- Create `coke/worker/`: Redis Stream consumer, scheduler process, outbox relay, delivery worker.
- Create `migrations/`: Alembic environment and revisions for the clean Postgres schema.
- Create focused tests under `tests/unit/coke/`, `tests/e2e/coke/`, and route/eval smoke tests under existing `tests/evals/` where user-path evidence is required.

### Web Target

- Modify `gateway/packages/web`: keep it as the thin Next.js client initially, de-brand `@clawscale` package naming, and repoint API clients to the Python API.
- Delete `gateway/packages/api` after Python API route parity and web repointing are verified.
- Delete `gateway/packages/clawscale-cli-bridge` during legacy cleanup.

## Task 1: Canonical Documentation Rewrite Gate

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/clawscale_bridge.md`
- Modify: `docs/deploy.md`
- Modify: `docs/design-docs/coke-working-contract.md`
- Modify: `docs/design-docs/interface-contract.md`
- Modify: `docs/design-docs/data-retention-policy.md`
- Modify: `docs/fitness/coke-verification-matrix.md`
- Modify: `docs/fitness/surfaces.yaml`
- Create: `scripts/e2e/clean-rebuild-canonical-doc-sync.sh`

- [ ] **Step 1: Add the docs guardrail first**

Create `scripts/e2e/clean-rebuild-canonical-doc-sync.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

required_docs=(
  "docs/ARCHITECTURE.md"
  "docs/product-specs/FEATURE_TREE.md"
  "docs/roadmap.md"
  "docs/design-docs/coke-working-contract.md"
  "docs/design-docs/interface-contract.md"
  "docs/fitness/coke-verification-matrix.md"
)

for doc in "${required_docs[@]}"; do
  test -f "$doc"
done

rg -q "The Turn" docs/ARCHITECTURE.md
rg -q "IdentityAccess" docs/ARCHITECTURE.md
rg -q "ChannelReachability" docs/ARCHITECTURE.md
rg -q "ConversationRuntime" docs/ARCHITECTURE.md
rg -q "SocialScheduling" docs/ARCHITECTURE.md
rg -q "CalendarImport" docs/ARCHITECTURE.md
rg -q "Postgres.*Redis" docs/ARCHITECTURE.md
rg -q "MongoDB.*Removed entirely|Mongo.*Removed entirely" docs/ARCHITECTURE.md
rg -q "clean-rebuild" docs/fitness/surfaces.yaml docs/fitness/coke-verification-matrix.md

for forbidden in \
  "model-output repair" \
  "second model call" \
  "MongoDB remains the source of truth" \
  "Gateway API owns" \
  "ClawScale Bridge :8090"; do
  if rg -n "$forbidden" docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md docs/design-docs/interface-contract.md; then
    echo "Forbidden stale rebuild contract found: $forbidden" >&2
    exit 1
  fi
done

if rg -n "pending (friend request|shared reminder).*(current product|active requirement|supported|workflow)" docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md docs/design-docs/interface-contract.md; then
  echo "Pending approval workflows may be mentioned only as deleted or out of scope, never as current rebuild behavior." >&2
  exit 1
fi
```

- [ ] **Step 2: Run the guardrail and verify it fails on stale docs**

Run: `bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh`

Expected: FAIL before the docs rewrite because `docs/ARCHITECTURE.md` still describes the current Bridge/Gateway/Mongo topology.

- [ ] **Step 3: Rewrite `docs/ARCHITECTURE.md` to the clean target**

Replace the current topology with these sections:

```md
# Architecture Reference

This document describes the clean-rebuild target architecture for Coke. The
requirements source of truth is
`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`;
the technical target is
`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`.

## Runtime Topology

Coke is a Python backend split into an ingress/egress tier and a worker tier,
with a thin Next.js client. Durable product state lives in Postgres. Redis is
coordination only: stream wake-up, locks, and reply pub/sub. MongoDB is removed
entirely.

## The Turn

All chat/channel-visible product prose flows through The Turn. Turn triggers are
InboundTurn, ReminderFireTurn, ProactiveFireTurn, NightlySummaryTurn,
NotificationTurn, AccessDeniedTurn, and UndeliveredResendTurn. The only normal
prose producer is the Interaction Agent. The runtime-owned waiting text is the
sole typed signal exception.

## Bounded Contexts

IdentityAccess owns account identity, access gate, activation, sessions,
credentials, channel identity, and auth artifacts. ChannelReachability owns the
single reachable channel, delivery route, and delivery attempts.
ConversationRuntime owns conversation order, messages, media references, turns,
and output disposition. Reminder owns reminders, fires, recurrence, scheduler,
and calendar read models. SocialScheduling owns friend links, friendships,
shared reminders, projections, and product notifications. CalendarImport owns
Google authorization, import runs, and per-occurrence import items.
```

- [ ] **Step 4: Rewrite route and feature discovery docs**

Update `docs/product-specs/FEATURE_TREE.md` and `docs/design-docs/interface-contract.md` so the discoverable surfaces are:

```md
- Public web: `/`, `/faqs`, `/demos`, `/privacy`, `/terms`, `/u/:code`
- Customer web: `/account/*`, `/channels`, `/reminders`, `/friends`,
  `/shared-reminders`, `/settings`, `/calendar-import`, `/subscription`,
  `/claim`
- Python public API: `/api/auth/*`, `/api/account/*`, `/api/channels/*`,
  `/api/reminders/*`, `/api/friends/*`, `/api/shared-reminders/*`,
  `/api/settings/*`, `/api/calendar-import/*`, `/api/subscription/*`,
  `/api/claim/*`
- Provider webhooks: `/webhooks/whatsapp/evolution`,
  `/webhooks/wechat/personal`, `/webhooks/wechat/ecloud`, `/webhooks/linq`
- Internal runtime: `/internal/outbound/delivery-callback`,
  `/internal/reply-wait/:causal_inbound_event_id`
```

Remove future-route ownership claims that assign product behavior to `gateway/packages/api` or `connector/clawscale_bridge`.

- [ ] **Step 5: Rewrite deployment and work-surface docs**

Update `docs/deploy.md`, `docs/clawscale_bridge.md`, and `docs/design-docs/coke-working-contract.md`:

```md
Future clean-rebuild services:

- `coke-api`: Python ingress/egress HTTP tier.
- `coke-worker`: Python Redis Stream turn workers.
- `coke-scheduler`: singleton Python reminder scheduler.
- `coke-outbox-relay`: Postgres outbox to Redis Stream relay.
- `coke-web`: Next.js thin client.
- `postgres`: product state, Agno session/history/memory/knowledge, pgvector.
- `redis`: wake-up stream, locks, reply pub/sub.

The standalone ClawScale bridge is superseded. ClawScale remains only as the
`wechat_personal` provider adapter behind Coke's canonical provider contract.
```

- [ ] **Step 6: Rewrite verification routing**

Add clean-rebuild surfaces to `docs/fitness/surfaces.yaml` and `docs/fitness/coke-verification-matrix.md`:

```yaml
clean-rebuild-docs:
  description: Canonical docs agree on the clean target architecture.
  commands:
    - bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
    - zsh scripts/check

clean-rebuild-backend:
  description: Python domain/API/worker rebuild contracts.
  commands:
    - .venv/bin/python -m pytest tests/unit/coke -v

clean-rebuild-web:
  description: Thin Next.js client over the Python API.
  commands:
    - cd gateway && pnpm --filter @coke/web test
    - cd gateway && pnpm --filter @coke/web build
```

- [ ] **Step 7: Verify docs gate**

Run:

```bash
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Expected: all commands pass. If `review-trigger` reports human-review risk because docs are broad, record the risk in the handoff and continue; human review is not a completion gate.

- [ ] **Step 8: Commit the docs gate**

```bash
git add docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md docs/roadmap.md docs/clawscale_bridge.md docs/deploy.md docs/design-docs/coke-working-contract.md docs/design-docs/interface-contract.md docs/design-docs/data-retention-policy.md docs/fitness/coke-verification-matrix.md docs/fitness/surfaces.yaml scripts/e2e/clean-rebuild-canonical-doc-sync.sh
git commit -m "docs: align repo docs to coke clean rebuild"
```

## Task 2: Backend Package And Infrastructure Foundation

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Create: `coke/__init__.py`
- Create: `coke/app.py`
- Create: `coke/config.py`
- Create: `coke/infra/postgres.py`
- Create: `coke/infra/redis.py`
- Create: `coke/infra/outbox.py`
- Create: `coke/infra/tracing.py`
- Create: `tests/unit/coke/test_backend_foundation.py`

- [ ] **Step 1: Write failing foundation tests**

Create `tests/unit/coke/test_backend_foundation.py`:

```python
from coke.app import create_app
from coke.config import Settings
from coke.infra.outbox import OutboxEvent


def test_settings_parse_postgres_and_redis_urls(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://coke:pass@localhost:5432/coke")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings.from_env()

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url == "redis://localhost:6379/0"


def test_app_factory_exposes_health_route(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://coke:pass@localhost:5432/coke")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    app = create_app(Settings.from_env())
    client = app.test_client()

    assert client.get("/healthz").json == {"ok": True}


def test_outbox_event_requires_stable_idempotency_key():
    event = OutboxEvent(
        id="evt_1",
        topic="turn.inbound",
        idempotency_key="inbound:provider-message-1",
        payload={"trigger_id": "inbound:provider-message-1"},
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00",
    )

    assert event.idempotency_key == "inbound:provider-message-1"
```

- [ ] **Step 2: Run the foundation tests and verify failure**

Run: `.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v`

Expected: FAIL because the `coke` package does not exist.

- [ ] **Step 3: Add backend dependencies**

Add these dependencies to `requirements.txt`:

```txt
SQLAlchemy>=2.0.0
alembic>=1.13.0
psycopg[binary]>=3.2.0
opentelemetry-api>=1.28.0
opentelemetry-sdk>=1.28.0
```

Remove `pymongo` only in the legacy-deletion task after all replacement paths no longer import Mongo.

- [ ] **Step 4: Implement the minimal app/config/infra foundation**

Create the package and pass the tests with typed settings, Flask app factory, shared Postgres/Redis factories, an immutable `OutboxEvent`, and traceparent helpers. The foundation must not import any legacy `dao`, `connector`, or `gateway` module.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v
```

Expected: PASS.

Commit:

```bash
git add requirements.txt pyproject.toml coke tests/unit/coke/test_backend_foundation.py
git commit -m "feat: add clean coke backend foundation"
```

## Task 3: Clean Postgres Schema And Migration Contract

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/20260529_0001_clean_rebuild_schema.py`
- Create: `coke/schema.py`
- Create: `tests/unit/coke/test_clean_schema_contract.py`

- [ ] **Step 1: Write schema contract tests**

Create tests that assert the clean schema contains the target tables and excludes legacy storage:

```python
from coke.schema import metadata


def test_clean_schema_has_required_product_tables():
    required = {
        "account",
        "agent_settings",
        "user_profile",
        "account_activation",
        "account_access",
        "credential",
        "session",
        "channel_identity",
        "auth_artifact",
        "channel",
        "delivery_route",
        "delivery_attempt",
        "conversation",
        "message",
        "inbound_media",
        "turn",
        "output_disposition",
        "outbox",
        "reminder",
        "reminder_fire",
        "friend_link",
        "friendship",
        "shared_reminder",
        "reminder_projection",
        "notification_fact",
        "notification_recipient",
        "calendar_import_run",
        "calendar_import_item",
    }

    assert required.issubset(set(metadata.tables))


def test_clean_schema_excludes_legacy_runtime_tables():
    forbidden = {"inputmessages", "outputmessages", "scheduled_actions", "friend_requests", "shared_reminder_requests"}

    assert forbidden.isdisjoint(set(metadata.tables))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest tests/unit/coke/test_clean_schema_contract.py -v`

Expected: FAIL because `coke.schema` does not exist.

- [ ] **Step 3: Implement SQLAlchemy metadata**

Define one declarative metadata module for the clean schema. Include unique constraints for:

```python
("channel_identity.provider_type", "channel_identity.provider_subject")
Index("uq_channel_one_active_per_account", channel.c.account_id, unique=True, postgresql_where=channel.c.lifecycle == "active")
Index("uq_friendship_one_active_pair", friendship.c.account_low_id, friendship.c.account_high_id, unique=True, postgresql_where=friendship.c.lifecycle == "active")
Index("uq_shared_reminder_active_duplicate", shared_reminder.c.creator_account_id, shared_reminder.c.participant_set_hash, shared_reminder.c.title_hash, shared_reminder.c.local_trigger_at, shared_reminder.c.captured_timezone, shared_reminder.c.duration_minutes, unique=True, postgresql_where=shared_reminder.c.status == "active")
("turn.trigger_id",)
("outbox.idempotency_key",)
("message.turn_id", "message.segment_index")
("reminder_fire.reminder_id", "reminder_fire.occurrence_key")
("calendar_import_item.provider_calendar_id", "calendar_import_item.source_event_id", "calendar_import_item.recurrence_instance_key")
```

- [ ] **Step 4: Generate the Alembic revision**

Run: `alembic revision --autogenerate -m "clean rebuild schema"`

Expected: generated revision matches the metadata. Replace generated names with the deterministic file `migrations/versions/20260529_0001_clean_rebuild_schema.py`.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_clean_schema_contract.py -v
alembic upgrade head --sql >/tmp/coke-clean-schema.sql
rg -q "CREATE TABLE account" /tmp/coke-clean-schema.sql
```

Expected: tests pass and offline SQL creates the clean schema.

Commit:

```bash
git add alembic.ini migrations coke/schema.py tests/unit/coke/test_clean_schema_contract.py
git commit -m "feat: define clean rebuild postgres schema"
```

## Task 4: IdentityAccess, Access Gate, Activation, And Web Claim

**Files:**
- Create: `coke/domains/identity_access/models.py`
- Create: `coke/domains/identity_access/repository.py`
- Create: `coke/domains/identity_access/service.py`
- Create: `coke/api/auth_routes.py`
- Create: `coke/api/claim_routes.py`
- Create: `tests/unit/coke/identity_access/test_identity_access_service.py`
- Create: `tests/unit/coke/identity_access/test_access_gate.py`

- [ ] **Step 1: Write failing access-gate and claim tests**

Test these cases:

```python
def test_denied_access_returns_access_denied_turn_fact(identity_service):
    decision = identity_service.check_access_for_inbound(account_id="acct_1")

    assert decision.allowed is False
    assert decision.turn_trigger == "AccessDeniedTurn"
    assert decision.fact["denial_reason"] in {"email_verification_required", "subscription_inactive", "suspended"}


def test_shared_whatsapp_first_seen_auto_provisions_messaging_account(identity_service):
    result = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert result.account.origin == "messaging_first"
    assert result.channel_identity.is_anchor is True


def test_web_claim_code_resolves_target_account_at_redemption(identity_service):
    claim = identity_service.issue_web_claim_code(browser_session="browser_1", continuation={"friend_link_id": "fl_1"})

    redeemed = identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert redeemed.account_id == "acct_from_sender_identity"
    assert redeemed.continuation == {"friend_link_id": "fl_1"}
```

- [ ] **Step 2: Implement IdentityAccess domain service**

Implement account origin, account access gate, activation projection, credential/session operations, channel identity creation, anchor protection checks, and `auth_artifact` issuing/redeeming. Do not create merge/unlink behavior.

- [ ] **Step 3: Add API routes**

Expose registration/login/email verification/password reset/current user/access status, login URL landing, claim-code issue/poll/redeem, and pairing-code issue/redeem through Python API routes. Route handlers must call domain services only.

- [ ] **Step 4: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/identity_access -v
```

Expected: all IdentityAccess tests pass.

Commit:

```bash
git add coke/domains/identity_access coke/api/auth_routes.py coke/api/claim_routes.py tests/unit/coke/identity_access
git commit -m "feat: implement clean identity access domain"
```

## Task 5: ChannelReachability And Provider Adapter Contract

**Files:**
- Create: `coke/domains/channel_reachability/models.py`
- Create: `coke/domains/channel_reachability/service.py`
- Create: `coke/providers/base.py`
- Create: `coke/providers/whatsapp_evolution.py`
- Create: `coke/providers/wechat_personal.py`
- Create: `coke/providers/wechat_ecloud.py`
- Create: `coke/providers/linq.py`
- Create: `coke/api/channel_routes.py`
- Create: `coke/api/provider_webhooks.py`
- Create: `tests/unit/coke/channel_reachability/`

- [ ] **Step 1: Write failing channel tests**

Cover single active channel, non-removable messaging anchor, removable web-first channel, `reconnection_required`, route resolution at send time, and provider-edge idempotency key behavior.

- [ ] **Step 2: Implement one canonical provider interface**

Use this contract:

```python
class ProviderAdapter(Protocol):
    provider_type: str

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        ...

    def send_text(self, route: DeliveryRoute, text: str, idempotency_key: str) -> DeliveryAttemptResult:
        ...
```

- [ ] **Step 3: Implement reachability service**

The service owns `channel`, `delivery_route`, and `delivery_attempt`. It consults IdentityAccess for channel-identity anchor rules and never writes `channel_identity`.

- [ ] **Step 4: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/channel_reachability -v
```

Expected: all channel tests pass.

Commit:

```bash
git add coke/domains/channel_reachability coke/providers coke/api/channel_routes.py coke/api/provider_webhooks.py tests/unit/coke/channel_reachability
git commit -m "feat: implement clean channel reachability"
```

## Task 6: ConversationRuntime, Outbox, Locks, And Turn Ledger

**Files:**
- Create: `coke/domains/conversation_runtime/models.py`
- Create: `coke/domains/conversation_runtime/service.py`
- Create: `coke/worker/outbox_relay.py`
- Create: `coke/worker/stream_consumer.py`
- Create: `coke/turn/locks.py`
- Create: `tests/unit/coke/conversation_runtime/`

- [ ] **Step 1: Write failing runtime ordering tests**

Cover durable `latest_inbound_seq`, `based_on_inbound_seq`, stale commit rejection, distinct `superseded` disposition, trigger replay idempotency, and outbound uniqueness by `turn_id + segment_index`.

- [ ] **Step 2: Implement message and turn ledger**

Store inbound messages, inbound media references, turns, output dispositions, and outbound segments. The service must never treat `no_reply` as failure or supersession.

- [ ] **Step 3: Implement outbox relay and Redis wake-up**

The relay reads unprocessed Postgres outbox rows, publishes to Redis Stream, and marks processed only after durable worker ack. Redis is a wake signal, not source of truth.

- [ ] **Step 4: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime -v
```

Expected: all conversation runtime tests pass.

Commit:

```bash
git add coke/domains/conversation_runtime coke/worker/outbox_relay.py coke/worker/stream_consumer.py coke/turn/locks.py tests/unit/coke/conversation_runtime
git commit -m "feat: implement turn ledger and outbox runtime"
```

## Task 7: The Turn Orchestration And Agno Binding

**Files:**
- Create: `coke/turn/pre_llm_gate.py`
- Create: `coke/turn/context.py`
- Create: `coke/turn/semantic_interpreter.py`
- Create: `coke/turn/focus.py`
- Create: `coke/turn/reference_resolver.py`
- Create: `coke/turn/freshness.py`
- Create: `coke/turn/memory.py`
- Create: `coke/turn/agent.py`
- Create: `coke/turn/output_protocol.py`
- Create: `coke/turn/runner.py`
- Create: `tests/unit/coke/turn/`

- [ ] **Step 1: Write failing orchestration tests**

Cover these contracts:

```python
def test_intentional_no_reply_skips_interaction_agent(turn_runner, semantic_interpreter):
    semantic_interpreter.next_decision = {"reply_necessity": "intentional_no_reply"}

    result = turn_runner.run_inbound_turn(trigger_id="inbound:1")

    assert result.disposition == "no_reply"
    assert turn_runner.agent_invocations == 0


def test_malformed_agent_output_fails_closed_without_rewrite(turn_runner, interaction_agent):
    interaction_agent.next_output = {"invalid": "shape"}

    result = turn_runner.run_inbound_turn(trigger_id="inbound:2")

    assert result.disposition == "failed"
    assert result.reason == "invalid_output_protocol"
    assert turn_runner.rewrite_invocations == 0
    assert result.visible_text is None
```

- [ ] **Step 2: Implement the orchestration contract**

Implement `pre-LLM gate → context builder → reference resolver → domain executor → response decision → output model` with Agno filling only the agent-loop/storage substrate. Keep SemanticInterpreter and detector roles separate; detector calls live inside Reminder and SocialScheduling tools.

- [ ] **Step 3: Implement output protocol**

Validate the first returned answer once. Do not ask the model to rewrite, do not synthesize template fallback prose, and do not replace model prose with domain summaries.

- [ ] **Step 4: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn -v
```

Expected: all turn orchestration tests pass.

Commit:

```bash
git add coke/turn tests/unit/coke/turn
git commit -m "feat: implement clean turn orchestration"
```

## Task 8: Reminder Domain, Scheduler, And Calendar Read Model

**Files:**
- Create: `coke/domains/reminder/models.py`
- Create: `coke/domains/reminder/service.py`
- Create: `coke/domains/reminder/recurrence.py`
- Create: `coke/domains/reminder/scheduler.py`
- Create: `coke/domains/reminder/calendar_read_model.py`
- Create: `coke/api/reminder_routes.py`
- Create: `tests/unit/coke/reminder/`

- [ ] **Step 1: Write failing reminder contract tests**

Cover timed reminders, no-trigger-time reminders, duplicate prevention, recurrence timezone pinning, same-owner same-time grouped fire, `reminder_fire` occurrence lifecycle, undelivered resend, proactive discard, past-time confirmation states, trigger-time/no-trigger-time conversion, and calendar action handles.

- [ ] **Step 2: Implement Reminder service and commands**

Implement owner-scoped CRUD, batch command results, recurrence, no-trigger-time summary state, and per-occurrence fire lifecycle. Reminder delivery targets the owner account and resolves the route at fire/resend time.

- [ ] **Step 3: Implement scheduler**

Use one pinned APScheduler process with Postgres-backed jobs and compare-and-set fire creation. Missed personal/shared triggers catch up on restart; missed proactive follow-ups discard.

- [ ] **Step 4: Implement calendar read model and API**

Return typed entries for one-time reminders, recurring occurrences, shared projections, unscheduled reminders, undelivered reminders, and merged groups. Expose only type-specific action handles.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/reminder -v
```

Expected: all reminder domain tests pass.

Commit:

```bash
git add coke/domains/reminder coke/api/reminder_routes.py tests/unit/coke/reminder
git commit -m "feat: implement clean reminder domain"
```

## Task 9: SocialScheduling And Product Notifications

**Files:**
- Create: `coke/domains/social_scheduling/models.py`
- Create: `coke/domains/social_scheduling/service.py`
- Create: `coke/domains/social_scheduling/availability.py`
- Create: `coke/domains/social_scheduling/notifications.py`
- Create: `coke/api/friend_routes.py`
- Create: `coke/api/shared_reminder_routes.py`
- Create: `tests/unit/coke/social_scheduling/`

- [ ] **Step 1: Write failing social scheduling tests**

Cover direct active friendship, no pending friend request, deferred self-completion when a friend-link joiner lacks a usable channel, active-relationship uniqueness, remove-friend lifecycle, group shared reminders, participant-scoped view/cancel, hard pre-creation receiver conflict and channel availability checks, idempotent cancellation, privacy-safe availability, notification facts without prose, and per-recipient notification state.

- [ ] **Step 2: Implement friendship and friend links**

Friend links and link codes require owner reachability. Establishment requires authenticated/claimed joiner reachability, unless continuation defers until channel connection. Removal changes friendship lifecycle only.

- [ ] **Step 3: Implement shared reminders**

Create one group shared reminder with per-participant projections. Enforce required-field follow-up states, receiver conflict checks, participant channel checks, duplicate prevention, participant-scoped view/cancel, and cancellation of all projections.

- [ ] **Step 4: Implement notification facts**

Persist structured facts only. Final visible notification text must be produced by a `NotificationTurn` render-mode Interaction Agent invocation.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling -v
```

Expected: all SocialScheduling tests pass.

Commit:

```bash
git add coke/domains/social_scheduling coke/api/friend_routes.py coke/api/shared_reminder_routes.py tests/unit/coke/social_scheduling
git commit -m "feat: implement clean social scheduling"
```

## Task 10: CalendarImport Domain

**Files:**
- Create: `coke/domains/calendar_import/models.py`
- Create: `coke/domains/calendar_import/google.py`
- Create: `coke/domains/calendar_import/service.py`
- Create: `coke/api/calendar_import_routes.py`
- Create: `tests/unit/coke/calendar_import/`

- [ ] **Step 1: Write failing import tests**

Cover one-time import, future-only conversion, all-day 00:00 mapping, default 15-minute duration, recurrence preservation when expressible, downgraded one-time occurrences when not expressible, occurrence-grain dedupe, result counts, downgraded/failed item listing, and revoke/stop without deleting imported reminders.

- [ ] **Step 2: Implement CalendarImport service**

CalendarImport records `calendar_import_run` and one `calendar_import_item` for every considered occurrence. Imported items create Coke-owned Reminder rows through the Reminder domain.

- [ ] **Step 3: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/calendar_import -v
```

Expected: all CalendarImport tests pass.

Commit:

```bash
git add coke/domains/calendar_import coke/api/calendar_import_routes.py tests/unit/coke/calendar_import
git commit -m "feat: implement clean calendar import"
```

## Task 11: Thin Next.js Web Repoint And De-Branding

**Files:**
- Modify: `gateway/package.json`
- Modify: `gateway/packages/web/package.json`
- Modify: `gateway/packages/web/lib/*`
- Modify: `gateway/packages/web/app/(customer)/**`
- Modify: `gateway/packages/web/app/u/[code]/page.tsx`
- Modify: `gateway/packages/web/app/faqs/page.tsx`
- Modify: `gateway/packages/web/app/demos/page.tsx`
- Modify: `gateway/packages/web/app/privacy/page.tsx`
- Modify: `gateway/packages/web/app/terms/page.tsx`
- Modify or create: `gateway/packages/web/**/*.test.tsx`

- [ ] **Step 1: Write failing web route/client tests**

Assert the web client calls the Python API route families from Task 1 and keeps every required product page: auth, access status, subscription, claim, channels, reminders, friends, shared reminders, settings, calendar import, public pages, and friend-link page.

- [ ] **Step 2: Repoint API clients**

Replace `@clawscale/api` assumptions with a single Python API base URL and typed client modules for each product surface. Do not port business rules into the client.

- [ ] **Step 3: De-brand package naming**

Rename user-visible and package-level ClawScale labels that describe Coke product ownership. Rename the web package from `@clawscale/web` to `@coke/web` so verification commands and future workspace imports use Coke ownership language. Keep provider names only where they identify a provider adapter.

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd gateway
pnpm --filter @coke/web test
pnpm --filter @coke/web build
```

Expected: web tests and build pass.

Commit:

```bash
git add gateway/package.json gateway/packages/web
git commit -m "feat: repoint web client to clean coke api"
```

## Task 12: Legacy Deletion And Anti-Regression Guardrails

**Files:**
- Delete: `connector/clawscale_bridge/`
- Delete: `gateway/packages/api/`
- Delete: `gateway/packages/clawscale-cli-bridge/`
- Delete: `memo-runtime/`
- Delete: `dao/mongo.py`
- Delete: obsolete Mongo DAOs and fallback-prose tests after replacement tests pass.
- Modify: `requirements.txt`
- Modify: `scripts/check`
- Modify: `scripts/e2e/clean-rebuild-canonical-doc-sync.sh`
- Create: `tests/unit/coke/test_clean_rebuild_no_legacy_imports.py`

- [ ] **Step 1: Write no-legacy-import tests**

Create a test that scans active Python source and fails on imports from `pymongo`, `dao.mongo`, `connector.clawscale_bridge`, `memo_runtime`, fallback-prose repair modules, or old Gateway callback clients.

- [ ] **Step 2: Delete legacy code after replacements pass**

Delete only after Tasks 2-11 have replacement tests passing. Remove old dependencies (`pymongo`, dead media-generation vendor modules, old bridge-only packages) when imports are gone.

- [ ] **Step 3: Run broad source checks**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke -v
zsh scripts/check
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
```

Expected: all pass and no legacy import remains in active source.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy coke runtime surfaces"
```

## Task 13: End-To-End Verification And Closeout

**Files:**
- Create or modify: `tests/e2e/coke/test_clean_rebuild_user_journeys.py`
- Create or modify: `tests/evals/test_clean_turn_runtime.py`
- Modify: `docs/RELEASE_CHECKLIST.md`
- Modify: `docs/release-guide.md`
- Update: this plan status to `verified` after all gates pass.

- [ ] **Step 1: Add user-journey smoke tests**

Cover these flows end to end against the clean Python backend:

```text
1. Shared WhatsApp first contact auto-provisions messaging-first account and receives text reply.
2. Web-first registration connects a personal channel via pairing code.
3. Messaging-first web claim opens an authenticated friend-link continuation.
4. Personal reminder create, fire, grouped same-time delivery, done reply, and calendar state.
5. No-trigger-time reminder nightly summary and batch scheduling.
6. Direct friendship through link and link code.
7. Shared reminder creation with conflict/unreachable failure and successful group creation.
8. Shared reminder due-time per-participant projection and participant-scoped cancel.
9. Calendar import one-time future import, repeat skip, downgraded recurrence, revoke.
10. Access denied inbound produces constrained AccessDeniedTurn and no normal intent execution.
```

- [ ] **Step 2: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: suggestions include clean-rebuild backend/web/docs/deploy surfaces. `review-trigger` may report high risk because the rebuild is broad; capture the risk and continue if tests pass.

- [ ] **Step 3: Run full selected verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke -v
.venv/bin/python -m pytest tests/e2e/coke -v
.venv/bin/python -m pytest tests/evals/test_clean_turn_runtime.py -v
cd gateway && pnpm --filter @coke/web test
cd gateway && pnpm --filter @coke/web build
zsh scripts/check
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
```

Expected: all pass. If a command fails, classify the failure as product/runtime bug, test/eval bug, environment instability, or plan gap before editing.

- [ ] **Step 4: Update release docs and plan status**

Update `docs/release-guide.md`, `docs/RELEASE_CHECKLIST.md`, and this plan's status block with final verification evidence and any intentionally unverified surfaces.

- [ ] **Step 5: Final commit**

```bash
git add docs/release-guide.md docs/RELEASE_CHECKLIST.md docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md tests/e2e/coke tests/evals/test_clean_turn_runtime.py
git commit -m "test: verify coke clean rebuild user journeys"
```

## Architecture Issues To Watch During Execution

- **The biggest risk is pretending this is a refactor.** It is not. The docs and tests must reject compatibility shims, Mongo fallback paths, bridge callbacks, and old Gateway ownership.
- **The second risk is collapsing turn disposition and delivery state.** A turn can produce a reply while a specific recipient delivery fails; reminder undelivered, proactive discard, shared projection delivery, and notification-recipient delivery are different states.
- **The third risk is letting domains leak into adapters.** Provider adapters normalize and send; they do not own identity, channel cardinality, reminder lifecycle, friendship, or notification facts.
- **The fourth risk is bypassing the Interaction Agent for product prose.** Notifications, reminders, access-denied recovery, and system-recovery text must be render-mode Turn invocations, except for the typed waiting text.
- **The fifth risk is under-testing stale intent.** `based_on_inbound_seq` must guard both outbound delivery and state-changing domain commits; otherwise a stale async turn can mutate data even if its reply is suppressed.
