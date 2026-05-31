# SocialScheduling And Product Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement clean SocialScheduling friendship, shared-reminder, availability, and product-notification facts on the existing `coke/schema.py` tables.

**Architecture:** The domain owns friend links, direct active friendships, group shared reminders, participant projections, privacy-safe availability, and structured notification facts. Cross-domain inputs are narrow ports for participant channel reachability and personal-reminder busy intervals; no Reminder or ChannelReachability implementation imports are introduced here. Flask routes are thin adapters over the domain service.

**Tech Stack:** Python 3.12, dataclasses, Protocol ports, in-memory repositories for focused unit tests, Flask blueprints, pytest.

---

**Plan Status:** in_progress
**Status Date:** 2026-05-31
**Blocker:** None. Bug A/B/C/D regression work, full unit tests, Postgres
integration tests, clean-stack redeploy, and mocked Phase 4-6 live resume have
fresh evidence. Bug E is open for the live shared-reminder time grounding
regression where the agent supplied an ungrounded absolute `local_trigger_at`.
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

- [x] **Step 4: Mark this plan complete**

Set `Plan Status` to `complete` only after verification passes.

- [x] **Step 5: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md coke/domains/social_scheduling coke/api/friend_routes.py coke/api/shared_reminder_routes.py coke/app.py tests/unit/coke/social_scheduling
git commit -m "feat: implement clean social scheduling"
```

### Task 7: Agent Tool Friend-Link Wiring And Live Resume

**Files:**
- Modify: `coke/composition.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Test: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Test: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md`

- [x] **Step 1: Write failing adapter tests**

Add tests that instantiate `SocialSchedulingToolAdapter` with a fake
SocialScheduling service. Assert operations `get_friend_link`,
`reset_friend_link`, and `disable_friend_link` route to
`get_or_create_friend_link`, `reset_friend_link`, and `disable_friend_link`.
The result facts must include `friend_link_id`, `owner_account_id`,
`lifecycle`, `public_token`, `link_code`, `public_link_url`, and `qr_payload`.
Add a service error case that raises `SocialSchedulingError("owner_channel_required")`
and assert the tool returns `ok=False` and
`reason_code="owner_channel_required"` without exposing a raw exception.

- [x] **Step 2: Write failing instruction/tool-doc tests**

Extend `tests/unit/coke/llm/test_interaction_agent.py` so the agent instructions
and generated `social_scheduling_tool` doc mention the real friend-link
operations: `get_friend_link` for giving the current user their link/code,
`reset_friend_link`, `disable_friend_link`, and
`establish_friendship_from_token` for adding a friend from a code/token. The
test must not mention operations that the adapter does not implement.

- [x] **Step 3: Run red tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: fail because `SocialSchedulingToolAdapter` still returns
`unsupported_social_scheduling_operation` for friend-link operations and the
agent instructions/tool doc do not describe them.

- [x] **Step 4: Implement minimal adapter wiring**

In `coke/composition.py`, add a helper that converts `FriendLinkView` into tool
facts with the fields from Step 1. Wire operations:
`get_friend_link -> service.get_or_create_friend_link(owner_account_id)`,
`reset_friend_link -> service.reset_friend_link(owner_account_id)`, and
`disable_friend_link -> service.disable_friend_link(owner_account_id)`.
Catch `SocialSchedulingError` around social-scheduling operations and map it to
`ToolExecutionResult(ok=False, facts=error.fact or {}, reason_code=error.code)`.
Do not add legacy imports, fallback prose, keyword routing, or new schema.

- [x] **Step 5: Implement concise agent guidance**

In `coke/llm/agno_interaction_agent.py`, update `_instructions()` and
`_tool_doc("social_scheduling")` so the model knows to call
`social_scheduling_tool` with `operation="get_friend_link"` and
`owner_account_id=trusted_facts.account_id` when the user asks for their invite
link/code, and to call `establish_friendship_from_token` when the user provides
a friend code/token. Keep the guidance factual and short.

- [x] **Step 6: Run green unit tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: all selected tests pass.

- [x] **Step 7: Run full unit verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: the full unit suite is green.

- [x] **Step 8: Commit code fix**

Run:

```bash
git add coke/composition.py coke/llm/agno_interaction_agent.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md
git commit -m "fix: expose social scheduling friend links to agent"
```

- [x] **Step 9: Redeploy clean stack**

Run:

```bash
REMOTE_HOST=gcp-coke REMOTE_ROOT=/home/whoami/coke-clean PROJECT_NAME=coke-clean COKE_CLEAN_API_PORT=8000 COKE_CLEAN_POSTGRES_PORT=55432 COKE_CLEAN_REDIS_PORT=56379 scripts/deploy-compose-to-gcp.sh
```

Then confirm the clean API health endpoint returns HTTP 200 and the old stack
containers are still running.

- [x] **Step 10: Resume mocked live E2E**

Against `http://127.0.0.1:8000/webhooks/whatsapp/evolution` on `gcp-coke`,
send Evolution `messages.upsert` payloads for two mocked WhatsApp senders.
After each phase, query the clean Postgres database (`coke-clean-postgres-1`,
database `coke`, user `coke`, host port `127.0.0.1:55432`) and capture rows for:
messaging-first account/channel/anchor/reply, personal reminder, friend link and
reply code, second account plus active friendship, shared reminder projections
and notification facts, and reminder fire plus outbound delivery attempt.

- [x] **Step 11: Mark this task and plan complete**

Only after Steps 6, 7, 9, and 10 have passing evidence, set this Task 7
checkboxes complete and set `Plan Status` to `complete`.

### Task 8: Bug A - Postgres Notification Fact And Outbox Atomicity

**Files:**
- Modify: `coke/domains/social_scheduling/repository.py`
- Test: `tests/integration/coke/repositories/test_social_scheduling_repository_contract.py`
- Test: `tests/integration/coke/test_social_scheduling_notification_outbox_contract.py`

- [x] **Step 1: Trace the current Postgres write order**

Read `PostgresSocialSchedulingRepository.add_notification_fact`,
`SocialSchedulingService.establish_friendship_from_*`, and
`SocialSchedulingService.create_shared_reminder`. Confirm whether
`notification_fact.outbox_id` can reference a missing `outbox.id`, and whether
Postgres integrity errors are being mapped to
`duplicate_notification_fact_idempotency` when the actual constraint is
`fk_notification_fact_outbox_id_outbox`.

- [x] **Step 2: Write the failing Postgres integration test**

Add a Postgres-gated test that uses
`COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql`
and real `PostgresSocialSchedulingRepository`. It must create account/channel
fixtures, establish friendship, create a shared reminder, then assert each
`notification_fact` row has a matching `outbox` row and the row ids reference
each other.

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_social_scheduling_notification_outbox_contract.py -q
```

Expected red result: failure showing the missing outbox row, FK error, or
incorrect duplicate error mapping.

- [x] **Step 3: Implement atomic outbox-first notification writes**

Change the Postgres repository method that persists notification facts so it
inserts the `outbox` row in the same SQLAlchemy transaction before inserting
`notification_fact`, using the fact's stable outbox id and idempotency key. If a
unique idempotency conflict occurs, return/map only the matching unique
constraint as duplicate; do not collapse FK/integrity failures into duplicate
idempotency.

- [x] **Step 4: Run the focused green integration test**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_social_scheduling_notification_outbox_contract.py -q
```

Expected: the notification/outbox contract test passes.

### Task 9: Bug B - Shared Reminder Persistence And Honest Tool Results

**Files:**
- Modify: `coke/composition.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/app.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Test: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Test: `tests/unit/coke/test_backend_foundation.py`
- Test: `tests/unit/coke/llm/test_interaction_agent.py`
- Test: `tests/integration/coke/test_social_scheduling_notification_outbox_contract.py`

- [x] **Step 1: Trace the create_shared_reminder tool path**

Read `SocialSchedulingToolAdapter.execute`,
`SocialSchedulingService.create_shared_reminder`, and the repository calls it
uses. Confirm whether success is reported when no shared reminder, projection,
or notification fact was persisted, and identify where exceptions are swallowed
or returned as ambiguous results.

- [x] **Step 2: Write failing persistence and tool-result tests**

Extend the Postgres integration test so shared-reminder creation asserts one
`shared_reminder` with `status='active'`, one `reminder_projection` per
participant, and at least one `notification_fact` with
`object_type='shared_reminder'`.

Extend the tool adapter unit test so a repository/service failure returns
`ok=False` with a concrete `reason_code`, and does not expose a raw exception or
claim success.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py -q
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_social_scheduling_notification_outbox_contract.py -q
```

Expected red result: the current path either fails to persist rows or reports
success for a failed operation.

- [x] **Step 3: Implement real persistence and explicit failure mapping**

Make `create_shared_reminder` persist the shared reminder, participant
projections, and shared-reminder notification fact as one successful domain
operation. If the domain or repository cannot persist, return a
`ToolExecutionResult(ok=False, reason_code=<specific code>)` from the adapter
instead of success. Keep no template prose or fallback success path.

- [x] **Step 4: Strengthen agent success-reporting instructions**

In `coke/llm/agno_interaction_agent.py`, state that state-changing tools
(`reminder`, `social_scheduling`, `settings`, `calendar`) may be reported as
successful only when the returned tool result has `ok=true`. If a result has
`ok=false`, `needs_*`, or a follow-up reason, the reply must honestly report the
failure/follow-up and must not claim the action happened.

- [x] **Step 5: Add the agent-contract unit test**

Extend `tests/unit/coke/llm/test_interaction_agent.py` to assert instructions
contain the `ok=true` success gate and that failed/needs-follow-up tool-result
guidance excludes success-claiming wording.

- [x] **Step 6: Run focused green tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/test_social_scheduling_notification_outbox_contract.py -q
```

Expected: all focused tests pass.

- [x] **Step 7: Commit API route mutations from the composed runtime**

The live setup exposed that non-webhook API routes could return success while
leaving the composed Postgres session uncommitted. Add a request lifecycle test
and app-level session commit/rollback hook so friend-link, friendship,
shared-reminder, and reminder route mutations are durable across clean API
workers.

### Task 10: Bug C - Picklable Scheduler Jobs

**Files:**
- Modify: `coke/scheduler/__main__.py`
- Test: `tests/unit/coke/test_scheduler_entrypoint.py`

- [x] **Step 1: Trace scheduler job registration**

Read `coke/scheduler/__main__.py` and identify every callable passed to
APScheduler `add_job`. Confirm lambdas, closures, or local functions are not
serializable with a Postgres jobstore.

- [x] **Step 2: Write failing picklability test**

Add a unit test that builds scheduler jobs without starting the long-running
loop and asserts every scheduled callable is importable/picklable, not a lambda
or closure.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_scheduler_entrypoint.py -q
```

Expected red result: the current lambda/closure callable fails the picklability
assertion.

- [x] **Step 3: Replace lambdas with module-level callables**

Move the scheduled job function(s) to module level and pass importable callable
references to APScheduler. Keep runtime behavior unchanged.

- [x] **Step 4: Verify local scheduler startup**

Run:

```bash
DATABASE_URL=postgresql+psycopg://ydyk@/coke_local?host=/var/run/postgresql REDIS_URL=redis://localhost:16379/0 COKE_LLM_FAKE=1 timeout 20s /data/projects/coke/.venv/bin/python -m coke.scheduler
```

Expected: no serialization crash during job registration; timeout is acceptable
only after startup stays alive.

### Task 11: Full Verification, Commit, Deploy, And Live Resume

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md`

- [x] **Step 1: Run required unit verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: full unit suite passes.

- [x] **Step 2: Run required Postgres integration verification**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: full integration suite passes.

- [x] **Step 3: Commit coherent fix**

Run:

```bash
git add coke/domains/social_scheduling/repository.py coke/domains/social_scheduling/service.py coke/composition.py coke/llm/agno_interaction_agent.py coke/scheduler/__main__.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/test_scheduler_entrypoint.py tests/integration/coke/test_social_scheduling_notification_outbox_contract.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md
git commit -m "fix: harden live social scheduling persistence"
```

- [x] **Step 4: Redeploy coke-clean**

Run:

```bash
REMOTE_HOST=gcp-coke REMOTE_ROOT=/home/whoami/coke-clean PROJECT_NAME=coke-clean COKE_CLEAN_API_PORT=8000 COKE_CLEAN_POSTGRES_PORT=55432 COKE_CLEAN_REDIS_PORT=56379 scripts/deploy-compose-to-gcp.sh
```

Then verify:

```bash
ssh gcp-coke 'curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz'
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean ps'
```

Expected: healthz returns `200`; `coke-clean-coke-scheduler-1` is `Up` and not
restarting; the old stack containers are still running.

- [x] **Step 5: Resume mocked Phase 4-6 live test**

On `gcp-coke`, send mocked Evolution messages to
`http://127.0.0.1:8000/webhooks/whatsapp/evolution` for fresh olivers and
李梓豪 subjects. Re-run quick setup for provisioning and friendship. Query clean
Postgres through `coke-clean-postgres-1` / host port `127.0.0.1:55432` and
capture rows proving:

- Phase 4: friendship `notification_fact` exists and references an existing
  `outbox` row.
- Phase 5: shared reminder is `active`, each participant has one projection,
  `notification_fact(object_type='shared_reminder')` exists, and the agent reply
  matches persisted reality. A forced failure case must produce an honest
  non-success reply.
- Phase 6: setting `next_fire_at` to the recent past lets the scheduler create a
  `reminder_fire` row and render-turn outbound message. Evolution mock delivery
  may fail; database rows are the verdict.

- [x] **Step 6: Close the plan**

Only after Steps 1-5 have evidence, update `Plan Status` to `complete`, set
`Status Date` to the completion date, check off the remaining boxes, and commit
the plan closeout if it changed after the fix commit.

### Task 12: Bug D - Agno Tool Argument Normalization

**Files:**
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `coke/composition.py`
- Test: `tests/unit/coke/llm/test_interaction_agent.py`
- Test: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md`

- [x] **Step 1: Inspect raw Agno tool-call arguments**

Run on the clean deployment host:

```bash
ssh gcp-coke 'docker exec coke-clean-postgres-1 psql -U coke -d coke -tAc "SELECT runs FROM ai.agno_sessions ORDER BY created_at DESC LIMIT 1"'
```

Read `messages[].tool_calls[].function.arguments` for the
`create_shared_reminder` call and record whether the envelope is a JSON string,
a nested `{"command": ...}` object/string, flat kwargs, or malformed list/string
fields such as `participants`, `participant_account_ids`, or receiver names.

Evidence: clean Agno stored `function.arguments` as a JSON string with top-level
`kwargs`; the nested kwargs contained `operation="create_shared_reminder"`,
`receiver_account_ids` as a list, and `context` as a plain string:
`"gcp clean live phase 5 verification"`. The failing adapter path attempted
`dict(context_string)`, producing
`dictionary update sequence element #0 has length 1; 2 is required`.

- [x] **Step 2: Write the failing regression test**

Add a unit test that reproduces the real argument shape from Step 1. The test
must fail before implementation with the live signature
`dictionary update sequence element #0 has length 1; 2 is required`, or with a
wrong command shape that prevents shared-reminder creation. The expected green
behavior is that the shared-reminder adapter receives a normalized command and
returns `ok=True` only when the domain operation actually succeeds.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected red result: the regression test fails because a string or nested
command envelope is still handled with unsafe `dict(...)` conversion or list
fields remain strings.

Red evidence:
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q`
failed with 3 regression failures, including the live
`dictionary update sequence element #0 has length 1; 2 is required` signature.

- [x] **Step 3: Implement shared tool-argument normalization**

Add one reusable normalizer in the Agno tool boundary and route every
`reminder`, `social_scheduling`, `calendar`, and `identity` tool through it. It
must accept JSON-string envelopes, nested `{"command": {...}}` or
`{"command": "{...}"}` payloads, and flat kwargs. It must never call `dict()` on
a string. It must coerce known list-typed fields
(`participants`, `participant_account_ids`, `receiver_names`, `receivers`,
`friend_account_ids`) from JSON strings or comma-separated strings into lists.
If normalization cannot produce a mapping, return an `ok=False` tool result with
a clear reason code instead of guessing business values or raising a raw Python
exception.

- [x] **Step 4: Run focused green tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: the new regression test and existing tool tests pass.

Evidence:
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -q`
passed with `22 passed in 2.05s`.

- [x] **Step 5: Run required full verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: both suites pass. If either fails, classify the failure before
editing further.

Evidence:
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed with
`380 passed in 9.16s`.
`COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q`
passed with `42 passed in 4.50s`.

- [x] **Step 6: Commit the fix**

Run:

```bash
git add coke/llm/agno_interaction_agent.py coke/composition.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/test_social_scheduling_tool_adapter.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-social-scheduling.md
git commit -m "fix: normalize agno tool arguments"
```

- [x] **Step 7: Redeploy coke-clean**

Run:

```bash
REMOTE_HOST=gcp-coke REMOTE_ROOT=/home/whoami/coke-clean PROJECT_NAME=coke-clean COKE_CLEAN_API_PORT=8000 COKE_CLEAN_POSTGRES_PORT=55432 COKE_CLEAN_REDIS_PORT=56379 scripts/deploy-compose-to-gcp.sh
```

Then verify:

```bash
ssh gcp-coke 'curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz'
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean ps'
ssh gcp-coke 'cd /home/whoami/coke && docker compose ps'
```

Expected: clean API healthz returns `200`, `coke-clean-coke-scheduler-1` is up
with restart count `0`, and the old stack is still running.

- [x] **Step 8: Resume mocked Phase 5 and Phase 6**

Against `http://127.0.0.1:8000/webhooks/whatsapp/evolution` on `gcp-coke`, use
fresh olivers and 李梓豪 mock senders. Quickly redo setup: provision both
messaging-first subjects, establish friendship through friend link and invite
code, create a shared reminder, and then force one projection reminder's
`next_fire_at` to the recent past. Query clean Postgres rows for
`shared_reminder`, `reminder_projection`, `notification_fact`, `outbox`, and
`reminder_fire`. Evolution mock-number delivery may fail; database rows are the
verdict.

- [x] **Step 9: Close the plan**

Only after Steps 1-8 have evidence, update `Plan Status` to `complete`, set
`Status Date` to the completion date, check off Task 12, and commit any plan
closeout change.

Closeout evidence:
- Commit: `16a7b5d1 fix: normalize agno tool arguments`.
- Deploy: `scripts/deploy-compose-to-gcp.sh` completed with
  `[deploy-clean] clean deploy health check passed`; clean `/healthz` returned
  `200`.
- Process health: `coke-clean-coke-scheduler-1`,
  `coke-clean-coke-api-1`, `coke-clean-coke-worker-1`, and
  `coke-clean-coke-outbox-relay-1` had restart count `0`; old `coke-*` stack
  containers remained running.
- Live run: `phase56_20260530T093339Z` provisioned olivers and 李梓豪, created
  friendship notification fact `c391ac66-9e75-4987-b7b0-d5c5d4946445`
  referencing outbox `28cd857e-f080-4344-80d8-3098dabcc5cd`, created active
  shared reminder `3832c900-fc37-4c8b-a128-b8bdcdc3d777`, produced two active
  projections, persisted shared-reminder notification fact
  `4fd2d150-150c-4cb4-85ad-e4b856d7a83b` plus outbox
  `49e0d2e3-f812-415b-82d4-8d2d1fc1f439`, and returned an agent reply matching
  the persisted shared reminder.
- Scheduler resume: forced reminder `b12a6fc3-ae33-4401-9c12-70d2f64607a0`
  produced reminder fire `d0164945-9687-4a2e-a50e-67ddfab0d482` and
  render-turn outbound message `df3ac514-f3fc-4c9d-a859-b9ca209de00f`.

### Task 13: Bug E - Shared Reminder Relative-Time Grounding

**Files:**
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/composition.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`

- [x] **Step 1: Reproduce the shared-reminder time grounding defect**

Add failing unit tests with fixed now `2026-05-31 14:02 Asia/Shanghai` showing
that shared reminder phrases `今天晚上10:30` and `明天晚上十点半` must resolve through
an authoritative account-local detector now to `2026-05-31T22:30:00` and
`2026-06-01T22:30:00`, while a genuinely past detected time still returns
`needs_past_time_confirmation`. Reconfirm the personal reminder path still
resolves `今晚10:30` to the future time.

Red evidence:
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/reminder/test_reminder_service.py -q`
failed with 25 failures: the social service lacked a detector constructor
argument/method, the adapter returned `unsupported_social_scheduling_operation`
for `detect_and_create_shared_reminder`, and the Agno instructions/defaults
still requested or passed through agent-supplied `local_trigger_at`.

- [x] **Step 2: Route shared natural-language creation through the grounded detector**

Add a SocialScheduling detect-and-create path that calls the existing reminder
detector with `self._now().astimezone(ZoneInfo(captured_timezone))`, uses the
detector output as a local wall-clock time, and then delegates to the existing
shared-reminder creation and past-time guard. Do not add regex parsing,
fallback prose, schema changes, or legacy imports.

- [x] **Step 3: Update the interaction-agent tool contract**

Change the social-scheduling tool instructions/defaults so natural-language
shared-reminder creation calls `detect_and_create_shared_reminder` with exact
raw user text and trusted timezone instead of asking the model to emit an
unbounded absolute `local_trigger_at`.

- [x] **Step 4: Run focused green tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/reminder/test_reminder_service.py -q
```

Expected: the new regression tests and existing affected tool tests pass.

Evidence:
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/reminder/test_reminder_service.py -q`
passed with `89 passed in 2.23s` after formatting.

- [x] **Step 5: Run required full verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: both suites pass. Classify any failure before editing further.

Evidence:
`/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed with
`530 passed in 17.04s`.
`COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q`
passed with `46 passed in 4.55s`.
`git diff --check` passed.
`zsh scripts/suggest-verification --base HEAD~1` suggested
`zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`.
`zsh scripts/review-trigger --base HEAD~1` returned `human_review_required: no`
with non-blocking medium repo-OS/evidence-gap triggers.
`zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed with
`530 passed in 16.55s` and `scripts/check` `check passed`.

- [ ] **Step 6: Commit the fix**

Commit code, tests, and this plan update on the current `main` branch.

- [ ] **Step 7: Redeploy coke-clean non-disruptively**

Take a rollback snapshot first, preserve `/home/whoami/coke-clean/.env`, run
Alembic upgrade/check for the clean stack, deploy current `main`, and verify
clean API health, worker/scheduler/outbox-relay health, login endpoints, and
connector session preservation. Do not recreate accounts/channels and do not
touch evolution or connector stacks.

- [ ] **Step 8: Live verify shared-reminder future times**

Drive the connected WeChat/API path for `今天晚上10:30` and `明天晚上十点半`; confirm
`shared_reminder.status = active`, `local_trigger_at` equals the correct future
account-local 22:30 time, replies do not say the time has passed, logins still
return 200, both channels remain connected, and connector `session_count = 2`.

- [ ] **Step 9: Close the plan**

Only after Steps 1-8 have evidence, update `Plan Status` to `complete`, set
`Status Date` to the completion date, check off Task 13, and commit any plan
closeout change.
