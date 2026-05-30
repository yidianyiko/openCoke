# Coke Clean Rebuild Live Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:systematic-debugging for live evidence gathering and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point the deployed clean stack at the real Evolution API, reroute the Evolution webhook reversibly, and actively drive a mocked two-user WhatsApp end-to-end smoke against clean Postgres.

**Architecture:** This is an operations-only live cutover over the already deployed `coke-clean` stack on `gcp-coke`. The old stack stays running as rollback; only the Evolution instance webhook and the clean stack's outbound Evolution environment are changed. Verification treats clean Postgres rows as the verdict for identity binding, inbound durability, turn disposition, domain side effects, outbound messages, reminder fire rows, and delivery attempts.

**Tech Stack:** SSH, Docker Compose, Evolution API, Postgres in `coke-clean-postgres-1`, Redis in `coke-clean-redis-1`, Flask clean API on `127.0.0.1:8000`, and `scripts/smoke/clean_smoke.py` or equivalent manual webhook posts.

---

**Plan Status:** blocked
**Status Date:** 2026-05-30

**Blocker:** Manual mocked real-account smoke stopped at phase 3. The clean
runtime accepted olivers' friend-link request, but the Interaction Agent called
unsupported tool operations and replied that friend links/invite codes are not
supported. No `friend_link` row was written for the tested account, so the
friendship, shared-reminder, and reminder-fire phases were not driven further.

### Task 1: Discover Evolution Runtime Truth

- [x] Capture old-stack Evolution API key without printing it.
- [x] Use `docker ps` on `gcp-coke` to identify the live Evolution container and host port.
- [x] Call `/instance/fetchInstances` on localhost candidate ports with the API key and identify the real instance name and connection state.

### Task 2: Reroute Evolution Webhook Reversibly

- [x] Capture `/webhook/find/<instance>` before changing it.
- [x] Save the prior webhook response to `/home/whoami/coke-clean/EVOLUTION_WEBHOOK_PRIOR.txt`.
- [x] Set the real instance webhook to `https://coke.keep4oforever.com/webhooks/whatsapp/evolution` for `MESSAGES_UPSERT`.
- [x] Verify `/webhook/find/<instance>` returns the new value.

### Task 3: Fix Clean Outbound Provider Config

- [x] Update `/home/whoami/coke-clean/.env` to use `http://host.docker.internal:<real_port>`, the real instance name, and the real API key.
- [x] Recreate clean API and worker services.
- [x] Verify clean `/healthz`.
- [x] Verify `coke-clean-coke-api-1` can reach Evolution through `host.docker.internal:<real_port>`.

### Task 4: Actively Drive Mocked Two-User Smoke

- [x] Run `scripts/smoke/clean_smoke.py --mode webhook` from the worktree root with clean API and DB access.
- [x] If the harness does not cover the requested Chinese-message phases, post Evolution-shaped `messages.upsert` payloads manually to the clean API.
- [x] After each phase, query clean Postgres and paste rows for the required evidence: account/channel/conversation/message/turn/outbound, reminder, friend link, friendship, shared reminder/projections/notification facts, reminder fire, render-turn outbound message, and delivery attempts.
- [x] If a product/integration bug blocks a phase, stop the smoke and capture the failing phase, agent/raw output evidence, tools called or missing, and missing DB write.

### Task 5: Final Verification, Plan Closeout, And Commit

- [x] Report the real Evolution instance name, port, and connection state.
- [x] Report prior and new webhook values plus rollback commands.
- [x] Report outbound config evidence and health/reachability checks.
- [x] Report every phase as PASS/FAIL with clean-DB evidence.
- [x] Run local repository verification for the plan-only change.
- [x] Leave `Plan Status` blocked because the mocked real-account smoke did not pass.
- [x] Commit the child plan on the current branch.
