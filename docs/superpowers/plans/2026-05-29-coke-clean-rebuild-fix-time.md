# Coke Fix-Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix reminder relative-time grounding and enforce past-time confirmation before personal or shared reminder creation can persist past due times.

**Architecture:** Keep the detector behind the Reminder boundary and make its `now` input an explicit account-timezone local grounding fact. Reuse the Reminder domain time-validation contract for SocialScheduling shared reminder creation before any durable shared reminder, projection, or notification write.

**Tech Stack:** Python 3.12, pytest, dataclasses, ZoneInfo, in-memory domain repositories, SQLAlchemy schema metadata.

**Plan Status:** complete

---

### Task 1: Ground Detector Relative Time In Account Timezone

**Files:**
- Modify: `coke/llm/reminder_detector.py`
- Modify: `coke/domains/reminder/service.py`
- Test: `tests/unit/coke/llm/test_reminder_detector.py`
- Test: `tests/unit/coke/reminder/test_reminder_service.py`

- [x] **Step 1: Read relevant plan/spec/code context**

Read the master clean-rebuild plan sections for Reminder, SocialScheduling, and architecture risks; requirements §5.7 and §5.8; target architecture §3.4, §3.5, §4 detector placement, §8, and §9; `coke/schema.py`; and existing Reminder/SocialScheduling service and repository patterns.

- [x] **Step 2: Write failing detector grounding tests**

Add tests that use a fake JSON completion client and fixed `now=datetime(2026, 5, 31, 11, 44, tzinfo=ZoneInfo("Asia/Shanghai"))`. Assert the detector prompt and payload identify this as authoritative local current time, local date, and local timezone grounding for relative expressions like `明天中午` and `明天早上9点`.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_reminder_detector.py -q
```

Expected before implementation: fails because the detector payload/prompt does not include explicit local-current-date grounding strong enough to prevent model guessing.

- [x] **Step 3: Write failing ReminderService detector-now test**

Add a service test whose fixed clock is `2026-05-31 03:44 UTC`, captured timezone is `Asia/Shanghai`, and fake detector records the `now` argument. Execute `detect_and_create` for `明天中午`, return `2026-06-01T12:00:00`, and assert the detector received `2026-05-31 11:44 +08:00` while the persisted reminder stores `2026-06-01 04:00 UTC`.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py -q
```

Expected before implementation: fails because `ReminderService` passes its raw UTC clock into the detector instead of account-local current time.

- [x] **Step 4: Implement detector grounding fix**

In `ReminderService._detect_item`, convert `self._now()` into `ZoneInfo(item.captured_timezone)` before calling the detector. In `SiliconFlowReminderDetector.extract`, strengthen the system/user contract with explicit fields: authoritative current datetime in captured timezone, current local date, current local time, and instruction that all relative expressions must be computed from that value.

- [x] **Step 5: Verify detector-focused tests pass**

Run both targeted suites:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_reminder_detector.py tests/unit/coke/reminder/test_reminder_service.py -q
```

Expected after implementation: all tests in those files pass.

### Task 2: Enforce Past-Time Guard For Shared Reminders

**Files:**
- Modify: `coke/domains/social_scheduling/models.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Test: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Test: `tests/unit/coke/reminder/test_reminder_service.py`

- [x] **Step 1: Write failing shared-reminder past-time test**

Add a test with fixed service time `2026-05-31 11:44 Asia/Shanghai`, active friendship and reachable participants. Call `create_shared_reminder` with `local_trigger_at=datetime(2025, 7, 11, 12, 0)` and `captured_timezone="Asia/Shanghai"`. Assert result status is `needs_past_time_confirmation`, follow-up facts include the time state, and the repository has no shared reminders, projections, or notification facts.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py -q
```

Expected before implementation: fails because the shared reminder is silently created.

- [x] **Step 2: Strengthen personal-reminder create-path guard test**

Extend the existing personal past-time test to assert that no reminder and no outbox row are created when a past `trigger_time` returns `needs_past_time_confirmation`.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py -q
```

Expected before implementation may already pass for personal reminders; keep it as regression evidence for the create path.

- [x] **Step 3: Implement shared-reminder validation**

Add shared-reminder result statuses for `needs_past_time_confirmation`, `needs_incomplete_date_clarification`, and `invalid`. Before duplicate/conflict/reachability checks and before any atomic write, classify the local trigger time using the same states as Reminder: invalid timezone or invalid trigger -> `invalid`; trigger instant earlier than `now` -> `needs_past_time_confirmation`. Return follow-up facts and mutate nothing.

- [x] **Step 4: Verify shared-reminder targeted tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/reminder/test_reminder_service.py -q
```

Expected after implementation: all tests in those files pass.

### Task 3: Full Required Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-fix-time.md`

- [x] **Step 1: Run unit test suite**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 2: Run requested integration command**

Run from the worktree root:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: all integration tests pass or report an environment blocker with exact output.

- [x] **Step 3: Run diff-aware routing checks**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete; review-trigger is a non-blocking risk report.

- [x] **Step 4: Mark this plan complete**

After verification passes, update `Plan Status` to `complete` and mark all checkboxes done.

- [x] **Step 5: Commit coherent fix**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-fix-time.md coke/llm/reminder_detector.py coke/domains/reminder/service.py coke/domains/social_scheduling/models.py coke/domains/social_scheduling/service.py tests/unit/coke/llm/test_reminder_detector.py tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py
git commit -m "fix: ground reminder times and block past shared reminders"
```

Expected: one commit on `fix/fix-time` containing plan, tests, and implementation.
