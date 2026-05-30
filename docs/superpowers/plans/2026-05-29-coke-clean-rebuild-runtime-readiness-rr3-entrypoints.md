# Coke Runtime Readiness RR3 Entrypoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Wire settings-based production composition, WSGI/worker/scheduler/outbox entrypoints, and production compose commands so the clean Coke runtime can start against Postgres and Redis.

**Architecture:** `Settings.from_env()` owns runtime configuration and `build_runtime_from_settings(settings)` is the production composition root. The API and worker entrypoints share that root, the outbox remains the durable bus source of truth, Redis remains wake/lock/pubsub only, and scheduler-generated reminder events enter the same outbox-to-worker render path.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, Redis Streams/pubsub/locks, APScheduler, Agno/SiliconFlow, Docker Compose, pytest.

---

## File Structure

- Modify `coke/config.py`: add provider, LLM, Google, lock, stream, scheduler, and fake-LLM settings read from env with fail-closed validation for required production values.
- Modify `coke/composition.py`: add `build_runtime_from_settings(settings)` plus thin adapters for Postgres session-backed repositories, Redis locking, real outbound delivery, provider registry, fake LLM seam, and real LLM defaults.
- Modify `coke/app.py`: when a composed runtime is supplied, expose its provider adapters to the provider webhook blueprint.
- Create `coke/api/wsgi.py`: construct the production Flask app for gunicorn without making any provider or LLM network calls at import time.
- Create `coke/worker/__main__.py`: consume Redis work-stream messages, rebuild durable turn triggers from Postgres state, take the conversation lock through `TurnRunner`, deliver via channel reachability, ack after durable success, and retry on transient errors.
- Modify `coke/worker/outbox_relay.py`: add a `python -m coke.worker.outbox_relay` loop that publishes unprocessed outbox rows to Redis.
- Create `coke/scheduler/__init__.py` and `coke/scheduler/__main__.py`: run a singleton APScheduler loop that scans due reminders, nightly summaries, and proactive fires and appends render events to the outbox.
- Modify `docker-compose.prod.yml`: replace placeholder commands with real entrypoints and add one-shot `coke-migrate` gating service.
- Modify `Dockerfile`: use the WSGI entrypoint by default and keep alembic migrations available in the image.
- Add `tests/integration/coke/test_runtime_wiring.py`: smoke-test settings composition against the local test DB with fakeredis and fake LLM enabled, app `/healthz`, webhook route registration, WSGI import, and entrypoint construction without live model calls.
- Add focused unit coverage where needed for Settings parsing and entrypoint helpers.

### Task 1: Settings Contract

**Files:**
- Modify: `coke/config.py`
- Test: `tests/unit/coke/test_backend_foundation.py`

- [x] **Step 1: Write failing settings tests**

Add tests that call `Settings.from_env()` with `DATABASE_URL`, `REDIS_URL`, `COKE_PROVIDER_EVOLUTION_BASE_URL`, `COKE_PROVIDER_EVOLUTION_API_KEY`, `COKE_PROVIDER_EVOLUTION_INSTANCE`, `SiliconFlow_API_KEY`, model overrides, `COKE_LLM_FAKE=1`, `COKE_LOCK_TTL_MS`, `COKE_WORK_STREAM`, `COKE_WORK_GROUP`, and `COKE_WORK_CONSUMER`, then assert typed attributes and fake-LLM validation behavior.

- [x] **Step 2: Run settings tests to verify failure**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -q`
Expected: FAIL because `Settings` does not yet expose RR3 runtime fields.

- [x] **Step 3: Implement Settings fields and env parsing**

Extend the frozen dataclass without changing existing `database_url`, `redis_url`, or `app_env`. Real LLM is default; `COKE_LLM_FAKE=1` permits missing `SiliconFlow_API_KEY`.

- [x] **Step 4: Run settings tests to verify green**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -q`
Expected: PASS.

### Task 2: Production Composition Root

**Files:**
- Modify: `coke/composition.py`
- Modify: `coke/app.py`
- Test: `tests/integration/coke/test_runtime_wiring.py`

- [x] **Step 1: Write failing composition smoke test**

Add an integration test that builds `Settings` for `COKE_TEST_DATABASE_URL`, `redis_url="fakeredis://"` style injection through a fakeredis client seam, and `llm_fake=True`, then asserts `build_runtime_from_settings(settings, redis_client=fake)` returns a runtime with `turn_runner`, Postgres-backed repositories, provider adapters, and an app exposing `/healthz` plus `/webhooks/whatsapp/evolution`.

- [x] **Step 2: Run composition smoke test to verify failure**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_runtime_wiring.py -q`
Expected: FAIL because `build_runtime_from_settings` does not exist.

- [x] **Step 3: Implement production composition**

Create one SQLAlchemy engine/session factory, build Postgres repositories per session-backed domain, use `RedisLockAdapter`, `RedisWorkStream`, and `RedisReplyPubSub`, build retained provider adapters from settings, use fake LLM components when `COKE_LLM_FAKE=1`, otherwise use Agno/SiliconFlow defaults, and inject a real outbound delivery adapter over `ChannelReachabilityService.send_text`.

- [x] **Step 4: Run composition smoke test to verify green**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_runtime_wiring.py -q`
Expected: PASS or SKIP only when the local test DB is unavailable.

### Task 3: Service Entrypoints

**Files:**
- Create: `coke/api/wsgi.py`
- Create: `coke/worker/__main__.py`
- Modify: `coke/worker/outbox_relay.py`
- Create: `coke/scheduler/__init__.py`
- Create: `coke/scheduler/__main__.py`
- Test: `tests/integration/coke/test_runtime_wiring.py`

- [x] **Step 1: Write failing entrypoint import/construction tests**

Add tests that import `coke.api.wsgi` with fake LLM/env settings, construct worker/outbox/scheduler loops with `run_forever=False` or one-iteration helpers, and assert no live LLM/provider calls occur at import.

- [x] **Step 2: Run entrypoint tests to verify failure**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_runtime_wiring.py -q`
Expected: FAIL because entrypoint modules are missing or placeholder-only.

- [x] **Step 3: Implement entrypoints**

WSGI constructs `create_app(Settings.from_env(), composed_runtime=runtime, provider_adapters=runtime.provider_adapters)`. Worker ensures the Redis group, handles `turn.inbound`, `reminder.fire`, `nightly.summary`, `proactive.fire`, and notification render topics by building `TurnTrigger` values from durable payloads, and acks only after `TurnRunner` completes. Outbox relay loops `publish_unprocessed`. Scheduler appends outbox render events from due-reminder scans.

- [x] **Step 4: Run entrypoint tests to verify green**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_runtime_wiring.py -q`
Expected: PASS.

### Task 4: Docker Runtime Commands

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `Dockerfile`
- Test: `tests/integration/coke/test_runtime_wiring.py`

- [x] **Step 1: Write failing compose/Dockerfile assertions**

Add tests that parse `docker-compose.prod.yml` and assert real commands for `coke-api`, `coke-worker`, `coke-scheduler`, and `coke-outbox-relay`, plus `coke-migrate` running `alembic upgrade head` and service dependencies on successful migration.

- [x] **Step 2: Run tests to verify failure**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_runtime_wiring.py -q`
Expected: FAIL because compose still contains placeholder commands.

- [x] **Step 3: Update Docker runtime definitions**

Set API command to `gunicorn coke.api.wsgi:app -b 0.0.0.0:8000 -w 2`, worker to `python -m coke.worker`, scheduler to `python -m coke.scheduler`, outbox relay to `python -m coke.worker.outbox_relay`, add `coke-migrate`, and set Dockerfile default command to gunicorn while keeping `COPY . .`.

- [x] **Step 4: Run tests to verify green**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_runtime_wiring.py -q`
Expected: PASS.

### Task 5: Verification And Commit

**Files:**
- Modify: this plan file

- [x] **Step 1: Run unit verification**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`
Expected: all unit tests pass.

- [x] **Step 2: Run integration verification**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q`
Expected: all integration tests pass.

- [x] **Step 3: Run import checks**

Run: `DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql REDIS_URL=redis://localhost:6379/0 COKE_LLM_FAKE=1 /data/projects/coke/.venv/bin/python -c "import coke.api.wsgi; import coke.worker.__main__; import coke.scheduler.__main__; import coke.worker.outbox_relay"`
Expected: exit 0.

- [x] **Step 4: Mark plan complete and commit**

Update `Plan Status: complete`, check `git diff --check`, commit coherent RR3 changes, then report verification evidence and commit SHAs.
