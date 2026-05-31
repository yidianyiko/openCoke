# Account Friend Naming And Scheduler Schema Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Ensure every account has a non-empty user-facing name and keep APScheduler-managed substrate tables from blocking the product Alembic schema check.

**Architecture:** IdentityAccess owns account creation, channel identity binding, and the `user_profile` row used as the user's display name. Provider adapters preserve sender display-name hints in `NormalizedInbound`; ChannelReachability passes that hint to IdentityAccess only when it auto-provisions a messaging-first account. SocialScheduling lists friend names by consulting an identity-owned profile lookup, while reminder calendar friend identifiers can use the same display resolver when wired.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy Core, Alembic, pytest, Next.js/React, Vitest.

---

## File Structure

- Modify: `coke/domains/identity_access/models.py` to add `UserProfile`, include it in registration results, and carry profile data in channel auto-provisioning.
- Modify: `coke/domains/identity_access/repository.py` to add in-memory and Postgres `user_profile` persistence and lookup helpers.
- Modify: `coke/domains/identity_access/service.py` to require display names for web registration, derive non-empty fallback names, and set profile names for messaging-first auto-provisioning.
- Modify: `coke/domains/channel_reachability/models.py`, provider adapters, and `coke/domains/channel_reachability/service.py` to preserve provider sender display names and pass them through the trust boundary.
- Modify: `coke/domains/social_scheduling/models.py`, `service.py`, and `coke/api/friend_routes.py` to include friend display names in list output.
- Modify: `coke/composition.py` only if the production wiring needs to inject IdentityAccess profile lookup into SocialScheduling and reminder friend identifiers.
- Modify: `web/lib/customer-auth.ts` so `display_name` is sent to `/api/auth/register`; keep the existing web form required field.
- Modify: `migrations/env.py` and scheduler configuration/tests so APScheduler substrate tables are excluded without weakening product schema drift checks.
- Add/modify tests under `tests/unit/coke/identity_access/`, `tests/unit/coke/channel_reachability/`, `tests/unit/coke/social_scheduling/`, `tests/unit/coke/test_scheduler_entrypoint.py`, and existing web register tests.

## Task 1: RED Tests For Required Account Names

- [x] **Step 1: Add failing IdentityAccess tests**

Add tests proving:

```python
with pytest.raises(IdentityAccessError, match="display_name_required"):
    identity_service.register_web_account("a@example.com", "password", display_name=" ")

registered = identity_service.register_web_account(
    "a@example.com", "password", display_name="Alice"
)
assert registered.user_profile.nickname == "Alice"

created = identity_service.resolve_or_create_channel_identity(
    "whatsapp_evolution", "15555550123", sender_display_name="Alice WA"
)
assert identity_service.get_display_name(created.account.id) == "Alice WA"

fallback = identity_service.resolve_or_create_channel_identity(
    "whatsapp_evolution", "wxid_lizihao", sender_display_name=" "
)
assert identity_service.get_display_name(fallback.account.id)
```

- [x] **Step 2: Run the targeted tests and confirm they fail**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_identity_access_service.py -q
```

Expected: failures because display-name parameters and profile lookup do not exist.

## Task 2: Implement IdentityAccess Profile Persistence

- [x] **Step 3: Add `UserProfile` model and repository methods**

Implement `add_user_profile`, `get_user_profile`, and `get_user_profiles` in both repository implementations against existing `coke.schema.user_profile`.

- [x] **Step 4: Require web display name and create profile rows**

Update `register_web_account(..., display_name: str, ...)`, normalize whitespace, reject blank values with `IdentityAccessError("display_name_required")`, and insert `user_profile.nickname`.

- [x] **Step 5: Auto-fill messaging-first profile names**

Update `resolve_or_create_channel_identity(..., sender_display_name: str | None = None)` so a newly-created messaging-first account gets `user_profile.nickname` from sender display name or a deterministic non-empty fallback derived from `provider_subject`.

- [x] **Step 6: Verify targeted IdentityAccess tests pass**

Run the same targeted pytest command from Task 1.

## Task 3: RED Tests For Provider Sender Names

- [x] **Step 7: Add failing provider normalization tests**

Assert `WhatsAppEvolutionAdapter.normalize_inbound()` maps `data.pushName` to `NormalizedInbound.sender_display_name`, and `WeChatPersonalAdapter.normalize_inbound()` maps a sender-name field such as `sender_name` to the same normalized field.

- [x] **Step 8: Add failing ChannelReachability first-contact test**

Assert `accept_provider_inbound()` passes `inbound.sender_display_name` to `resolve_or_create_channel_identity()`.

- [x] **Step 9: Run targeted channel tests and confirm they fail**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability -q
```

Expected: failures because `NormalizedInbound.sender_display_name` does not exist and sender names are dropped.

## Task 4: Implement Provider Sender-Name Propagation

- [x] **Step 10: Add `sender_display_name` to `NormalizedInbound`**

Add an optional field with default `None` so existing test fakes stay concise.

- [x] **Step 11: Capture provider display names**

Map Evolution `data.pushName` and iLink/wechat_personal `sender_name`, `senderName`, `nickname`, or `name` to `sender_display_name` without using it for identity matching.

- [x] **Step 12: Pass sender name to IdentityAccess during auto-provisioning**

Forward `sender_display_name` when ChannelReachability calls `resolve_or_create_channel_identity()`.

- [x] **Step 13: Verify targeted channel tests pass**

Run the targeted channel pytest command from Task 3.

## Task 5: RED Tests For Friend Names And Web Register Payload

- [x] **Step 14: Add failing social scheduling friend-list test**

Construct SocialSchedulingService with a profile-name resolver and assert `list_friends("owner")[0].display_name == "Alice"`.

- [x] **Step 15: Add failing friend route test**

Assert `GET /api/friends` returns each friend object with `display_name`.

- [x] **Step 16: Add failing web auth API test**

Assert `registerCustomer({ displayName: "Alice", ... })` posts `display_name: "Alice"` to `/api/auth/register`.

- [x] **Step 17: Run targeted backend and web tests and confirm they fail**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling tests/unit/coke/identity_access/test_auth_routes.py -q
cd web && pnpm test -- auth/register customer-auth
```

Expected: failures because friend entries and register payloads do not include display names end to end.

## Task 6: Implement Friend Display Names And API/Web Registration

- [x] **Step 18: Add display names to FriendListEntry and route output**

Extend `FriendListEntry` with `display_name`, inject a resolver into SocialSchedulingService, and include `display_name` in `/api/friends`.

- [x] **Step 19: Wire display resolver in composition**

Pass `identity_access_service.get_display_name` into SocialSchedulingService and reminder friend identifier read-model wiring if the runtime composition owns those constructors.

- [x] **Step 20: Send and validate web register display name**

Send `display_name` from `web/lib/customer-auth.ts`; update Flask auth route to require that body field and pass it to `register_web_account`.

- [x] **Step 21: Verify targeted friend/register tests pass**

Run the targeted backend and web commands from Task 5.

## Task 7: RED Tests For APScheduler Schema Drift

- [x] **Step 22: Add failing schema-filter test**

Add a unit test proving Alembic autogenerate include filtering excludes `apscheduler_jobs` and `ix_apscheduler_jobs_next_run_time` while still including ordinary product tables.

- [x] **Step 23: Run the targeted scheduler/schema test and confirm it fails**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_scheduler_entrypoint.py -q
```

Expected: failure because no APScheduler exclusion hook exists.

## Task 8: Isolate APScheduler Substrate From Product Alembic Check

- [x] **Step 24: Add Alembic include filter**

Define a small `include_name` or `include_object` hook in `migrations/env.py` that excludes only APScheduler-managed table/index names from autogenerate/check, without excluding product tables.

- [x] **Step 25: Document/check the local DB proof path**

Add a documented command or test note that the proof is: `alembic upgrade head`, create scheduler jobstore tables, then `alembic check`.

- [x] **Step 26: Verify Alembic upgrade/check with jobstore tables present**

Run on the local test DB:

```bash
DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql alembic upgrade head
DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python - <<'PY'
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
store = SQLAlchemyJobStore(url="postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql")
store.start(None, "default")
store.shutdown()
PY
DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql alembic check
```

Expected: upgrade succeeds and check reports no new upgrade operations.

## Task 9: Full Verification And Commits

- [x] **Step 27: Run required backend unit suite**

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

- [x] **Step 28: Run required integration suite**

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

- [x] **Step 29: Run web tests and build**

```bash
cd web && pnpm test
cd web && pnpm build
```

- [x] **Step 30: Mark this plan complete after all verification passes**

Change `Plan Status` to `complete`, check all completed boxes, and commit coherent changes.
