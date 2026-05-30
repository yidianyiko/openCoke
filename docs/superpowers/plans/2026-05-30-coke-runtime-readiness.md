# Coke Runtime-Readiness + gcp-coke Cutover Plan

**Plan Status:** complete (deployed + real-account E2E verified on gcp-coke)
**Status Date:** 2026-05-30
**Source specs:** `2026-05-28-coke-clean-rebuild-target-architecture-design.md` (§2 system shape, §5 bus/outbox, §6 access gate, §7 channels, §8 scheduler, §11 Agno), `2026-05-28-coke-requirements-user-journey-matrix-design.md`.

**Goal:** Make the implementation-complete `coke/` rebuild actually RUN against real
infra, then deploy it to `gcp-coke` (replacing the old stack) and prove it with a
real-account WhatsApp test using **olivers** and **李梓豪**.

**Context:** `coke/` is 318-test verified but uses in-memory repos, stub providers,
fake LLM/Redis, and placeholder service entrypoints. Local Postgres 18.1 is live;
Docker is available; `gcp-coke` runs Evolution WhatsApp (instance `coke`) + has the
real `.env` (SiliconFlow LLM key, Evolution creds, domain coke.keep4oforever.com).
See [[project-coke-gcp-deploy-target]].

## Waves

### RR-A — runnable core (local-testable, no external creds)
- **RR1 Postgres repositories** — SQLAlchemy-backed implementations of every domain
  Repository protocol over `coke/schema.py` + `coke/infra/postgres.py`. Contract tests
  run BOTH the in-memory and the Postgres-backed impl against the LOCAL postgres
  (skip-gate on `COKE_TEST_DATABASE_URL`). Alembic `upgrade head` must build the schema.
- **RR2 Real Redis + outbox runtime** — real Redis adapter for the conversation lock
  (SET NX PX + token), the work-wake Stream consumer group, and reply pub/sub; the
  outbox relay loop (Postgres outbox → Redis Stream, processed-on-ack, idempotent
  replay). Tests via fakeredis or a docker redis.
- **RR3 Service entrypoints** — `coke-api` WSGI (gunicorn) serving /api,/webhooks,
  /internal,/healthz with the Postgres-backed composed runtime; `coke-worker` stream
  loop running The Turn; `coke-scheduler` APScheduler (Postgres jobstore) for
  reminder/nightly/proactive fires; `coke-outbox-relay` loop. Real `command:` entries
  in `docker-compose.prod.yml`; Dockerfile for the Python image.

### RR-B — external adapters (built now, live-proven at deploy)
- **RR4 Provider adapters** — real Evolution WhatsApp send + inbound webhook
  normalization (primary, messaging-first); wechat_personal/wechat_ecloud/linq behind
  the same contract. Unit-tested against recorded payloads/mocked HTTP.
- **RR5 Agno + LLM binding** — bind the Turn InteractionAgent, SemanticInterpreter, and
  the encapsulated reminder_detect to SiliconFlow models (GLM-5.1 thinking-off, see
  [[project_reminder_detect_model_lock]] / [[feedback_chinese_models_on_siliconflow]]);
  Agno session/memory on Postgres + pgvector.
- **RR6 Google Calendar client** — real client for calendar_import behind its port.

### RR-C — deploy + cutover tooling
- **RR7 Deploy script rewrite** — `scripts/deploy-compose-to-gcp.sh` for the clean
  stack (no gateway submodule/bridge; sync `coke/`+`web/`+`migrations/`+compose; bring
  up compose; alembic migrate on boot; health-check coke-api `/healthz`; repoint the
  Evolution webhook to the clean coke-api `/webhooks/whatsapp/evolution`).
- **RR8 Clean-arch real-account smoke harness** — replace `.claude/skills/coke-agent-smoke`:
  drive two real users through inbound→reply, friend-link, shared-reminder, reminder-fire
  against the live clean stack, verifying the CLEAN Postgres schema (account /
  channel_identity / conversation / message / turn / reminder / reminder_fire /
  friendship / shared_reminder / reminder_projection / notification_fact). DB is the verdict.

### RR-D — bring-up + cutover (leader-driven)
- Local synthetic E2E (compose up with local PG+redis; simulated Evolution webhook →
  worker turn → DB write → outbound) proving wiring.
- Deploy to gcp-coke, apply migrations, repoint Evolution webhook, run RR8 smoke with
  olivers + 李梓豪. DB ground-truth verification每 phase.
