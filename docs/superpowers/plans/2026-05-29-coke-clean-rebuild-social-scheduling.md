# SocialScheduling And Product Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement clean SocialScheduling friendship, shared-reminder, availability, and product-notification facts on the existing `coke/schema.py` tables.

**Architecture:** The domain owns friend links, direct active friendships, group shared reminders, participant projections, privacy-safe availability, and structured notification facts. Cross-domain inputs are narrow ports for participant channel reachability and personal-reminder busy intervals; no Reminder or ChannelReachability implementation imports are introduced here. Flask routes are thin adapters over the domain service.

**Tech Stack:** Python 3.12, dataclasses, Protocol ports, in-memory repositories for focused unit tests, Flask blueprints, pytest.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Blocker:** Task 9 implementation and SocialScheduling tests pass, and
`clean-rebuild-backend` passes as part of
`zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`; however
`repo-os-docs` fails on pre-existing ownership-registry/missing-file entries
outside the Task 9 allowed edit scope. Do not mark this plan complete until that
repo-OS ownership gap is resolved by the owning slice.
**Freshness Check:** Read `AGENTS.md`, `docs/design-docs/index.md`, `docs/design-docs/human-ai-working-contract.md`, master plan Task 9 and architecture-watch sections, requirements §§5.6/5.7/5.9, target architecture §§3.5/4/8/9/14/15, `coke/schema.py`, existing `identity_access`, `channel_reachability`, `coke/api/*_routes.py`, and `coke/app.py`.

**Files:**
- Create: `coke/domains/social_scheduling/__init__.py`
- Create: `coke/domains/social_scheduling/models.py`
- Create: `coke/domains/social_scheduling/repository.py`
- Create: `coke/domains/social_scheduling/service.py`
- Create: `coke/domains/social_scheduling/availability.py`
- Create: `coke/domains/social_scheduling/notifications.py`
- Create: `coke/api/friend_routes.py`
- Create: `coke/api/shared_reminder_routes.py`
- Modify: `coke/app.py`
- Create: `tests/unit/coke/social_scheduling/`

### Task 1: Red Tests For SocialScheduling

**Files:**
- Create: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Create: `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`
- Create: `tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py`

- [x] **Step 1: Write failing service tests**

Cover direct active friendship, no pending-request model, deferred self-completion, active uniqueness with removed re-establishment, remove-friend lifecycle, group shared reminder creation, participant-scoped view/cancel, conflict/reachability breakdown, idempotent cancellation, privacy-safe availability, structured notification facts with no prose, and per-recipient partial-failure state.

- [x] **Step 2: Write failing route tests**

Cover route wiring for friend links/friendship/list/remove and shared-reminder create/list/view/cancel/availability through `create_app(..., social_scheduling_service=service)`.

- [x] **Step 3: Write failing schema contract tests**

Assert SocialScheduling uses the existing `friend_link`, `friendship`, `shared_reminder`, `reminder_projection`, `notification_fact`, and `notification_recipient` tables and the active partial unique indexes already defined in `coke/schema.py`.

- [x] **Step 4: Run red tests**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling -v`

Expected: tests fail because `coke.domains.social_scheduling` and the new routes do not exist yet.

### Task 2: Domain Models And In-Memory Repository

**Files:**
- Create: `coke/domains/social_scheduling/models.py`
- Create: `coke/domains/social_scheduling/repository.py`
- Create: `coke/domains/social_scheduling/__init__.py`

- [x] **Step 1: Define dataclasses and errors**

Implement `FriendLink`, `Friendship`, `SharedReminder`, `ReminderProjection`, `NotificationFact`, `NotificationRecipient`, command/result dataclasses, `BusyInterval`, `AvailabilityQuery`, and `SocialSchedulingError`.

- [x] **Step 2: Define repository Protocol**

Include methods for storing links, friendships, shared reminders, projections, notification facts, and recipients. Include lookups by token/code hash, active unordered pair, participant-scoped shared-reminder access, duplicate shared-reminder key, active friend resolution, and busy shared-reminder intervals.

- [x] **Step 3: Implement in-memory repository**

Mirror schema constraints in memory: one active friendship per unordered pair, removed pairs can re-establish, one active duplicate shared reminder by creator/participant-set/title/local-time/timezone/duration, one projection per shared reminder participant, one notification recipient per fact/account.

- [x] **Step 4: Run focused tests**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py -v`

Expected: failures move from import errors to missing service behavior.

### Task 3: Notifications And Availability Ports

**Files:**
- Create: `coke/domains/social_scheduling/notifications.py`
- Create: `coke/domains/social_scheduling/availability.py`

- [x] **Step 1: Define narrow ports**

In `availability.py`, define `ReminderAvailabilityPort.personal_busy_intervals(account_id, start, end, requester_timezone)`, `ParticipantReachabilityPort.has_usable_channel(account_id)`, and bounded availability query helpers. Do not import Reminder or ChannelReachability domains.

- [x] **Step 2: Implement privacy-safe availability**

Resolve active friends, combine personal busy intervals from the port with SocialScheduling-owned shared-reminder intervals, and return only `{friend_account_id, windows: [{start, end, state: busy|free}]}` without titles, reminder ids, provider details, or Google Calendar data.

- [x] **Step 3: Implement notification fact builder**

Create immutable structured facts for friendship creation and shared-reminder creation/cancellation/error cases. Hash canonical structured facts including `status`; reject/avoid any `payload.text`, `text`, or final prose field.

- [x] **Step 4: Implement recipient state helpers**

Fan one fact out to many `notification_recipient` rows and allow per-recipient `pending | delivered | undelivered | failed` with user-safe `error_facts`.

### Task 4: SocialScheduling Service

**Files:**
- Create: `coke/domains/social_scheduling/service.py`

- [x] **Step 1: Implement friend links**

Generate/get/reset/disable owner links only when the owner has a usable channel. Store token hash and link-code hash, return public token/code/QR facts, and ensure reset rotates future tokens without affecting existing friendships.

- [x] **Step 2: Implement direct friendship**

Establish through token or link code. Forbid self-friendship. Require joiner authentication/claim and usable channel; if joiner lacks a usable channel, return `deferred_channel_required` with continuation carrying `friend_link_id` and mutate no friendship. On channel completion, `complete_deferred_friend_link` establishes the same direct active friendship. Existing active friendship returns idempotent `already_active`; removed pairs can create a new active row.

- [x] **Step 3: Implement remove/list**

List only active friends for each side. Remove flips active friendship to `removed`, removes it from both active lists, blocks new shared-reminder creation for that pair, and does not cancel existing shared reminders.

- [x] **Step 4: Implement shared-reminder create**

Validate missing participants/title/time/context first and mutate nothing, returning `needs_participants | needs_title | needs_time | needs_context`. Resolve each receiver to a unique active friend. Then enforce receiver conflict and participant channel checks with no partial creation and a three-way `conflicting_participants`, `unreachable_participants`, `available_participants` breakdown. Do not check the creator's own conflict. On success, create one active group reminder plus one projection for the creator and each receiver.

- [x] **Step 5: Implement participant-scoped shared-reminder operations**

List/view require requester participation. Cancel checks participation before status handling. `active -> cancelled` stops all projections and emits cancellation facts; `cancelled -> cancelled` returns an already-cancelled result and emits no duplicate cancellation. Completion only marks the requester's projection.

### Task 5: Flask Routes And App Registration

**Files:**
- Create: `coke/api/friend_routes.py`
- Create: `coke/api/shared_reminder_routes.py`
- Modify: `coke/app.py`

- [x] **Step 1: Add friend routes**

Expose `/api/friends/link`, `/api/friends/link/reset`, `/api/friends/link/disable`, `/api/friends/join`, `/api/friends/complete-deferred`, `/api/friends`, and `/api/friends/<friend_account_id>/remove`. Routes validate JSON/query/path fields and return error bodies using `SocialSchedulingError.code` and optional `fact`.

- [x] **Step 2: Add shared-reminder routes**

Expose `/api/shared-reminders`, `/api/shared-reminders/<shared_reminder_id>`, `/api/shared-reminders/<shared_reminder_id>/cancel`, `/api/shared-reminders/<shared_reminder_id>/complete-own-projection`, and `/api/shared-reminders/availability`.

- [x] **Step 3: Register app blueprints**

Add an optional `social_scheduling_service` kwarg in `coke/app.py` and register both new blueprints when it is supplied. Do not alter existing blueprint blocks.

### Task 6: Verification, Plan Closeout, And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md`

- [x] **Step 1: Run SocialScheduling unit tests**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling -v`

Expected: all tests in `tests/unit/coke/social_scheduling` pass.

- [x] **Step 2: Run diff-aware verification routing**

Run: `zsh scripts/suggest-verification --base HEAD~1`

Expected: command completes and identifies relevant verification surfaces.

- [x] **Step 3: Run non-blocking risk report**

Run: `zsh scripts/review-trigger --base HEAD~1`

Expected: command completes; record any non-blocking findings in handoff if present.

- [ ] **Step 4: Mark this plan complete**

Set `Plan Status` to `complete` only after verification passes.

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md coke/domains/social_scheduling coke/api/friend_routes.py coke/api/shared_reminder_routes.py coke/app.py tests/unit/coke/social_scheduling
git commit -m "feat: implement clean social scheduling"
```
