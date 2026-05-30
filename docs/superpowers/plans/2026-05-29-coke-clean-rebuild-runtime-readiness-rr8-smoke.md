# RR8 Clean Smoke Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean-architecture smoke harness that drives two WhatsApp senders against a running Coke stack and treats the clean Postgres schema as the verdict.

**Architecture:** The harness lives outside runtime code under `scripts/smoke/`. It posts Evolution-shaped inbound payloads or waits for real WhatsApp inbound rows, drives deterministic clean API operations where a plaintext token is required, then polls the clean tables in `coke/schema.py` for account, channel identity, conversation, turn, reminder, friendship, shared-reminder, notification, and reminder-fire facts. It writes JSON evidence to `artifacts/evidence/clean-smoke/` and hard-stops on any mismatch.

**Tech Stack:** Python 3.12, SQLAlchemy Core over `coke.schema`, urllib stdlib HTTP, pytest for self-contained harness tests, JSON transcript evidence.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Source Specs:** `docs/superpowers/plans/2026-05-30-coke-runtime-readiness.md`; `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md` §5.8/§5.9/§5.13; `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md` §3.1-§3.5/§4/§8/§9.

## File Structure

- Create `scripts/smoke/__init__.py`: package marker for the smoke helpers.
- Create `scripts/smoke/clean_smoke.py`: CLI, config/env parsing, webhook/real drivers, clean-schema query assertions, JSON evidence writer, and dry-run schema query compilation.
- Create `tests/unit/coke/smoke/test_clean_smoke.py`: self-contained tests for Evolution payload generation, sender/env parsing, SQL compilation against `coke.schema`, verdict failure behavior, and dry-run evidence.
- Modify `.claude/skills/coke-agent-smoke/SKILL.md`: replace legacy bridge/Mongo instructions with the clean RR8 harness contract.
- Modify this plan as work advances; set `Plan Status: complete` only after verification passes.

## Task 1: Child Plan Gate

**Files:**
- Create: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr8-smoke.md`

- [x] **Step 1: Read only the RR8 source slices**

Read the RR8 runtime-readiness wave, requirements rows for first activation, personal reminders, friendship, shared reminders, Product notification, and messaging-first identity, plus target architecture sections for identity/channel/conversation/reminder/social scheduling and turn-vs-delivery state.

- [x] **Step 2: Write this child plan**

Save this file with checkbox steps and `Plan Status: in-progress`.

## Task 2: Failing Harness Tests

**Files:**
- Create: `tests/unit/coke/smoke/test_clean_smoke.py`

- [x] **Step 1: Write tests for the public harness contract**

Tests to add:

```python
def test_sender_env_accepts_plain_jid_and_json_identity(monkeypatch):
    ...

def test_evolution_payload_matches_clean_provider_shape():
    ...

def test_dry_run_compiles_all_verdict_queries_against_schema(tmp_path):
    ...

def test_verdict_failure_is_recorded_and_stops(tmp_path):
    ...
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/smoke/test_clean_smoke.py -q
```

Expected: fail because `scripts.smoke.clean_smoke` does not exist.

## Task 3: Implement Clean Smoke Harness

**Files:**
- Create: `scripts/smoke/__init__.py`
- Create: `scripts/smoke/clean_smoke.py`

- [x] **Step 1: Add configuration and transcript primitives**

Implement `SmokeConfig.from_env()`, sender parsing for `COKE_SMOKE_SENDER_A` / `_B`, `SmokeTranscript`, and `SmokeVerdictError`.

- [x] **Step 2: Add Evolution webhook driver and real-mode wait driver**

Implement `--mode webhook` POSTs to `/webhooks/whatsapp/evolution`; implement `--mode real` as DB polling for real inbound rows already delivered by Evolution.

- [x] **Step 3: Add clean-schema verdict queries**

Implement assertion methods for:

- first contact: `account`, `channel_identity`, `conversation`, inbound `message`, `turn`, `output_disposition`, outbound `message` when the disposition is reply-like;
- personal reminder: exactly one active owner-scoped reminder matching the smoke title;
- friendship: exactly one active unordered `friendship`;
- shared reminder: active `shared_reminder`, one projection per participant, and at least one `notification_fact` with `facts_hash` and no text payload;
- fire path: due `reminder_fire` with delivered result and an outbound message containing the reminder title.

- [x] **Step 4: Add live flow orchestration**

The sequence is: first-contact A/B, natural-language personal reminder from A, friend link issue via clean `/api/friends/link`, B joins via clean `/api/friends/join`, shared reminder creation via clean `/api/shared-reminders`, due reminder creation via clean `/api/reminders/batch`, wait for scheduler fire, then write evidence.

- [x] **Step 5: Add dry-run**

Implement `--dry-run` so it imports the harness, compiles every SQLAlchemy Core verdict query against the Postgres dialect, writes dry-run evidence, and does not require `COKE_SMOKE_API_BASE` or `COKE_SMOKE_DB_URL`.

- [x] **Step 6: Run targeted tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/smoke/test_clean_smoke.py -q
```

Expected: all tests pass.

## Task 4: Update Smoke Skill

**Files:**
- Modify: `.claude/skills/coke-agent-smoke/SKILL.md`

- [x] **Step 1: Replace legacy stack instructions**

Document `scripts/smoke/clean_smoke.py`, clean schema, `/webhooks/whatsapp/evolution`, no Mongo, no bridge, no old `coke-agent-smoke`, and the hard-stop rule when `/healthz` or Postgres is unavailable.

- [x] **Step 2: Include live commands**

Document env vars and commands:

```bash
COKE_SMOKE_API_BASE=...
COKE_SMOKE_DB_URL=...
COKE_SMOKE_SENDER_A=...
COKE_SMOKE_SENDER_B=...
/data/projects/coke/.venv/bin/python -m scripts.smoke.clean_smoke --mode webhook
/data/projects/coke/.venv/bin/python -m scripts.smoke.clean_smoke --mode real
```

## Task 5: Verification And Commit

**Files:**
- Modify: this plan status and checkboxes
- Generated: `artifacts/evidence/clean-smoke/*.json`

- [x] **Step 1: Run dry-run self-check**

Run:

```bash
/data/projects/coke/.venv/bin/python -m scripts.smoke.clean_smoke --dry-run
```

Expected: JSON output with `status: passed` and evidence path under `artifacts/evidence/clean-smoke/`.

- [x] **Step 2: Run targeted smoke harness tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/smoke/test_clean_smoke.py -q
```

Expected: all tests pass.

- [x] **Step 3: Run full Coke unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 4: Set plan complete after verification**

Change `Plan Status: complete` and mark remaining boxes complete only after the commands above pass.

- [x] **Step 5: Commit coherently**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-runtime-readiness-rr8-smoke.md scripts/smoke tests/unit/coke/smoke .claude/skills/coke-agent-smoke artifacts/evidence/clean-smoke
git commit -m "test: add clean runtime smoke harness"
```
