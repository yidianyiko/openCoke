# Reminder Timezone Inference Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the clean runtime so natural-language "tomorrow 9 AM" reminders for non-UTC accounts preserve 09:00 in the account timezone and persist the correct UTC `next_fire_at`.

**Architecture:** The Reminder detector remains trusted-or-invalid and stays inside the Reminder tool boundary. The service must convert detector-returned local wall-clock datetimes using `captured_timezone` before persistence, without regex repair, Tokyo special cases, fallback prose, or schema changes. The live verification uses the primary `coke-clean` stack and verifies stored Postgres rows, not only webhook responses.

**Tech Stack:** Python 3.11, pytest, `zoneinfo`, SQLAlchemy schema metadata, SiliconFlow/Agno detector boundary, Docker Compose `coke-clean` on `gcp-coke`, Postgres.

**Parent Plan:** `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`, Task 8 Reminder Domain, plus the runtime-readiness/live cutover plans.

**Plan Status:** in_progress

---

### Task 1: Diagnose The Live Failure Layer

**Files:**
- Read: `coke/llm/reminder_detector.py`
- Read: `coke/domains/reminder/service.py`
- Read: `coke/composition.py`
- Read: live `ai.agno_sessions` and `reminder` rows on `gcp-coke`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-reminder-timezone-inference.md`

- [x] **Step 1: Inspect live detector/tool evidence**

Run a focused query against `coke-clean-postgres-1` to find the failing personal-WeChat run and inspect the Agno tool call/result:

```bash
ssh gcp-coke 'docker exec coke-clean-postgres-1 psql -U coke -d coke -x -c "select id, created_at, runs from ai.agno_sessions order by created_at desc limit 8"'
```

Expected: identify whether the detector/tool result contained `2026-05-31T09:00...`, `2026-05-31T00:00...`, or a date-only/midnight value.

Evidence: clean Postgres has no persisted `ai.agno_sessions` table because Agno session upsert currently logs a metadata conflict, so the exact historical tool result was not available from DB. The live reminder row for account `6bfe382d-f981-491e-9af4-c1c821b76020` stored `next_fire_at=2026-05-30 15:00:00+00`, which displays as `2026-05-31 00:00:00` in `Asia/Tokyo`, while the outbound confirmation said `明天早上9:00 跑步`.

- [x] **Step 2: Inspect local mapping and assembly**

Confirm whether `SiliconFlowReminderDetector.extract`, `ReminderToolAdapter`, and `ReminderService._detect_item/_create` preserve, reject, or convert detector datetimes.

Evidence: a live Interaction Agent diagnostic with a fake reminder tool called `operation=detect_and_create`, `raw_text=提醒我明天早上9点跑步`, and `captured_timezone=Asia/Tokyo`. A direct live `SiliconFlowReminderDetector` call returned `trigger_time=2026-05-31 09:00:00+09:00`. `ReminderService._detect_item` passed detector `trigger_time` through unchanged and `_create` persisted it directly.

- [x] **Step 3: Record root-cause classification**

Add evidence to this plan: detector extraction, detector-to-`ReminderBatchItem` mapping, or service timezone assembly.

Root-cause classification: detector boundary/prompt contract was too weak for explicit local time-of-day. The service path would persist an aware `09:00+09:00` correctly, but it had no domain-level local wall-clock assembly for detector output and the detector prompt did not explicitly require preserving the stated hour/minute in `captured_timezone`. The live bad row is consistent with the detector/tool result having already collapsed the local time to midnight.

### Task 2: Write Failing Regression Tests

**Files:**
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify if detector prompt/parse is root cause: `tests/unit/coke/llm/test_reminder_detector.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-reminder-timezone-inference.md`

- [x] **Step 1: Add deterministic non-UTC service regression**

Add a fake-detector test that returns a naive local wall-clock time for "tomorrow 9 AM" and expects persisted UTC to represent 09:00 local for both Asia/Tokyo and America/New_York:

```python
def test_detected_local_wall_clock_times_are_persisted_as_account_timezone_instants(repository):
    detector = FakeDetector([
        DetectedReminderFields(
            content="run",
            trigger_time=datetime(2026, 5, 31, 9, 0),
            recurrence_rule={},
            duration_minutes=None,
        ),
        DetectedReminderFields(
            content="run",
            trigger_time=datetime(2026, 5, 31, 9, 0),
            recurrence_rule={},
            duration_minutes=None,
        ),
    ])
    service = ReminderService(
        repository=repository,
        detector=detector,
        now=lambda: datetime(2026, 5, 30, 10, 10, tzinfo=UTC),
        id_factory=sequence_factory("tz"),
    )

    for owner, timezone in [
        ("tokyo", "Asia/Tokyo"),
        ("new_york", "America/New_York"),
    ]:
        service.execute_batch(
            owner_account_id=owner,
            items=[
                ReminderBatchItem(
                    operation="detect_and_create",
                    raw_text="remind me tomorrow at 9",
                    captured_timezone=timezone,
                )
            ],
        )

    tokyo = repository.list_active_reminders("tokyo")[0]
    new_york = repository.list_active_reminders("new_york")[0]
    assert tokyo.next_fire_at == datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    assert new_york.next_fire_at == datetime(2026, 5, 31, 13, 0, tzinfo=UTC)
    assert tokyo.captured_timezone == "Asia/Tokyo"
    assert new_york.captured_timezone == "America/New_York"
```

- [x] **Step 2: Run the focused red test**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py::test_detected_local_wall_clock_times_are_persisted_as_account_timezone_instants -q
```

Expected: FAIL before implementation because the service currently rejects or persists the naive detector datetime without converting it to the captured timezone UTC instant.

Red evidence: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py::test_detected_local_wall_clock_times_are_persisted_as_account_timezone_instants -q` failed with `AssertionError: assert 'failed' == 'succeeded'`.

- [x] **Step 3: Add detector-level red test if live evidence shows detector dropped the hour**

Only if Task 1 shows the detector prompt/result caused the hour loss, add a prompt/parse contract test asserting that the request tells the model to return the full local wall-clock time in `captured_timezone`, including hour and minute.

Red evidence: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_reminder_detector.py::test_extract_prompt_requires_full_local_wall_clock_time_in_captured_timezone -q` failed because the prompt did not contain `Preserve explicit hour and minute`.

### Task 3: Implement The Minimal Root-Cause Fix

**Files:**
- Modify: `coke/domains/reminder/service.py`
- Modify if needed: `coke/llm/reminder_detector.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-reminder-timezone-inference.md`

- [x] **Step 1: Convert detector local wall-clock output at the domain boundary**

Add one helper in `ReminderService` that treats detector output as local wall-clock time in `captured_timezone`, converts it to UTC for persistence, and rejects invalid timezone names through the existing validation path:

```python
def _detected_trigger_time(self, fields: DetectedReminderFields, captured_timezone: str) -> datetime | None:
    if fields.trigger_time is None:
        return None
    zone = ZoneInfo(captured_timezone)
    local_trigger = fields.trigger_time.replace(tzinfo=zone)
    return local_trigger.astimezone(UTC)
```

Use this helper when mapping `DetectedReminderFields` to `ReminderBatchItem`.

Evidence: implemented in `ReminderService._detect_item` via
`_detected_trigger_time`. Detector datetimes are treated as local wall-clock
components in `captured_timezone` and then converted to UTC, so an offset on the
detector transport value cannot silently move the understood local hour.

- [x] **Step 2: Keep direct API/create behavior unchanged**

Do not convert direct `operation="create"` inputs in this fix. Direct API/adapter callers already provide absolute aware datetimes; this incident is the detector local-time mapping path.

- [x] **Step 3: Update detector prompt only if Task 1 requires it**

If detector evidence shows the model produced midnight/date-only output, minimally clarify the schema/prompt to require full ISO-8601 local wall-clock datetime in `captured_timezone` and preserve explicit hour/minute.

Evidence: `SiliconFlowReminderDetector` now instructs the model to interpret
dates/times in `captured_timezone`, preserve explicit hour/minute, and return a
full ISO-8601 local wall-clock datetime.

### Task 4: Verify, Commit, Deploy, And Smoke

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-reminder-timezone-inference.md`

- [x] **Step 1: Run focused green tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_reminder_detector.py -q
```

Expected: all focused reminder/detector tests pass.

Evidence: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_reminder_detector.py -q` passed with `14 passed in 1.63s`.

- [x] **Step 2: Run required full local suites**

Run from the repository root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: both suites pass. If either fails, classify the failure before editing further.

Evidence: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`
passed with `382 passed in 9.16s`. The first integration attempt failed because
local database `coke_rr_test` did not exist; after creating it and applying
`DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql
/data/projects/coke/.venv/bin/python -m alembic upgrade head`,
`COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql
/data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q`
passed with `42 passed in 4.49s`.

Diff-aware verification evidence: `git diff --check` passed.
`zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed with
`382 passed in 9.13s` and `check passed`.

- [ ] **Step 3: Commit the tested fix**

Run:

```bash
git add coke/domains/reminder/service.py coke/llm/reminder_detector.py tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_reminder_detector.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-reminder-timezone-inference.md
git commit -m "fix: preserve reminder detector local times"
```

Only add files that actually changed.

- [ ] **Step 4: Redeploy primary `coke-clean`**

Run:

```bash
REMOTE_HOST=gcp-coke REMOTE_ROOT=/home/whoami/coke-clean PROJECT_NAME=coke-clean COKE_CLEAN_API_PORT=8000 COKE_CLEAN_POSTGRES_PORT=55432 COKE_CLEAN_REDIS_PORT=56379 scripts/deploy-compose-to-gcp.sh
```

Then run:

```bash
ssh gcp-coke 'curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz'
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml ps'
```

Expected: `/healthz` is `200`; clean services show restart count `0`.

- [ ] **Step 5: Re-run live personal-WeChat and UTC WhatsApp reminders**

Create a fresh marked Asia/Tokyo web-first `wechat_personal` reminder with `提醒我明天早上9点跑步`, then a fresh UTC shared-WhatsApp reminder with the equivalent "tomorrow 9am" text. Query Postgres for both rows:

```sql
select
  a.default_timezone,
  r.content,
  r.next_fire_at,
  r.next_fire_at at time zone a.default_timezone as local_next_fire_at,
  r.captured_timezone
from reminder r
join account a on a.id = r.owner_account_id
where r.content ilike '%<marker>%'
order by r.created_at desc;
```

Expected: Tokyo row shows `local_next_fire_at` at 09:00 in `Asia/Tokyo`; UTC row shows 09:00 UTC; outbound WeChat may still show `provider_not_configured`.

- [ ] **Step 6: Close the plan**

After verification passes and live evidence is recorded, set `Plan Status: complete`, add verification evidence, and commit the plan closeout if it changed after the code commit.
