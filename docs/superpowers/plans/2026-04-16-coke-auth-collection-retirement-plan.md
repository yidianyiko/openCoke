# Coke Auth-Collection Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire Coke-owned auth storage (`Mongo users`, Postgres `coke_accounts`, and the old auth-token tables) after neutral auth is live, while preserving byte-identical `account_id` / `customer_id` references in all remaining Coke business records.

**Architecture:** Treat the cutover as a short maintenance-window migration, not a dual-write phase. First audit all surviving Mongo documents for `account_id` parity, move any non-auth fields still stranded on the legacy auth stores into clearly named Coke business documents, then drop the legacy auth tables/collections and update the remaining runtime code to rely exclusively on `customer_id`.

**Tech Stack:** TypeScript, Prisma, PostgreSQL, tsx, Python 3.12, PyMongo, pytest, pnpm, ripgrep

---

## Scope Check

This plan is **follow-up plan 3** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- auditing `account_id` parity across Coke Mongo collections
- moving surviving non-auth fields off Mongo `users` and Postgres `coke_accounts`
- retiring `coke_accounts`, old verify-token tables, and the legacy Mongo auth collection
- cutting ClawScale <-> Coke contracts over to `customer_id`-first semantics

This plan does **not** cover:

- neutral customer auth routes themselves
- frontend relocation
- shared-channel claim flow

## File Structure

### New audit / migration files

- `gateway/packages/api/src/scripts/audit-customer-id-parity.ts`
  Audits every Mongo `account_id` touchpoint and prints drift if any value no longer matches `Customer.id`.
- `gateway/packages/api/src/scripts/export-legacy-coke-auth.ts`
  Exports legacy `coke_accounts` / `verify_tokens` rows before destructive retirement.
- `connector/scripts/migrate-legacy-users.py`
  Moves surviving non-auth fields from Mongo `users` into `user_profiles`, `coke_settings`, or `characters`.
- `connector/scripts/verify-auth-retirement.py`
  Confirms the legacy auth collection is gone and the remaining business collections still resolve by `account_id`.

### Modified Gateway files

- `gateway/packages/api/prisma/schema.prisma`
  Remove `CokeAccount`, `VerifyToken`, and any remaining legacy auth FKs after the neutral tables are authoritative.
- `gateway/packages/api/prisma/migrations/20260417020000_retire_coke_auth_storage/migration.sql`
  Preserves legacy tables during the transition-safe phase while subscription foreign keys move to `customer_id`.
- `gateway/packages/api/prisma/migrations/20260419010000_drop_legacy_coke_auth_tables/migration.sql`
  Drops `verify_tokens` and `coke_accounts` only after every runtime dependency has been removed.
- `gateway/packages/api/src/lib/coke-subscription.ts`
  Rename `cokeAccountId` handling to `customerId` while keeping Coke payment semantics intact.
- `gateway/packages/api/src/routes/coke-payment-routes.ts`
  Read subscription state by `customer_id`.
- `gateway/packages/api/src/routes/coke-auth-routes.ts`
  Remove live `db.cokeAccount` / `db.verifyToken` dependencies while preserving the deprecated Coke-compatible HTTP contract.
- `gateway/packages/api/src/lib/clawscale-user.ts`
  Stop creating or requiring compatibility `coke_accounts` rows during user provisioning.
- `gateway/packages/api/src/routes/customer-channel-routes.ts`
  Resolve compatibility lookups from neutral membership / identity data instead of `coke_accounts`.
- `gateway/packages/api/src/routes/coke-wechat-routes.ts`
  Drop any remaining legacy auth-table reads from channel binding flows.
- `gateway/packages/api/src/routes/coke-user-provision.ts`
  Provision bridge identities without requiring compatibility auth rows.
- `gateway/packages/api/src/routes/user-wechat-channel.ts`
  Remove remaining `coke_accounts`-based lookups from user channel operations.
- `gateway/packages/api/src/lib/route-message.ts`
  Resolve bridge routing metadata without legacy auth-table joins.
- `gateway/packages/api/src/lib/platformization-backfill.ts`
  Stop backfill / verification code from depending on `coke_accounts` once cutover is complete.

### Modified Coke-side files

- `dao/user_dao.py`
  Stop serving as an auth DAO; retain only business-profile access if still needed.
- `agent/runner/identity.py`
  Resolve users by `customer_id` / `account_id` parity without depending on the retired auth collection.
- `connector/clawscale_bridge/app.py`
  Remove any requirement that Mongo `users` exist for inbound auth lookups.

## Task 1: Audit every surviving `account_id` reference

**Files:**
- Create: `gateway/packages/api/src/scripts/audit-customer-id-parity.ts`
- Modify: `dao/user_dao.py` (read-only audit helpers only)

- [x] Add an audit script that scans the known Mongo touchpoints from:
  - `agent/util/message_util.py`
  - `agent/runner/identity.py`
  - `connector/clawscale_bridge/*.py`
  - `dao/*.py`
- [ ] The script must print both counts and drift examples:

```json
{
  "collectionsChecked": ["messages", "reminders", "memory"],
  "driftCount": 0,
  "examples": []
}
```

- [ ] Run:

```bash
rg -n "account_id" agent connector dao util -g '!tests/**'
pnpm --dir gateway/packages/api exec tsx src/scripts/audit-customer-id-parity.ts
```

- [ ] If drift is found, stop and update this plan before destructive work.

## Task 2: Move non-auth legacy fields into business documents

**Files:**
- Create: `connector/scripts/migrate-legacy-users.py`
- Modify: `dao/user_dao.py`
- Modify: any Coke DAO that still depends on auth-only fields in `users`

- [x] Use these destination contracts during classification:
  - `user_profiles` => one document per non-character customer, keyed by `account_id`, for `name`, `display_name`, non-character `platforms`, non-character `user_info`, and migration metadata
  - `coke_settings` => one document per non-character customer, keyed by `account_id`, for `timezone`, `access.*`, and migration metadata
  - `characters` => one document per legacy `is_character = true` record, preserving the existing `_id` and carrying `name`, `nickname`, `platforms`, `user_info`, and migration metadata
- [x] Write a migration script that classifies each field on Mongo `users` as:
  - auth-only => delete (`email`, `phone_number`, password / verification / session fields, top-level legacy auth `status`, and `is_character` after the split)
  - business-profile => move to `user_profiles` (`name`, `display_name`, non-character `platforms`, non-character `user_info`)
  - Coke setting => move to `coke_settings` (`timezone`, `access.*`)
  - character-owned => move the full `is_character = true` document into `characters`, preserving its existing `_id` and top-level `nickname`
- [x] Add a dry-run mode that prints:

```json
{
  "dry_run": true,
  "users_scanned": 0,
  "profiles_to_write": 0,
  "settings_to_write": 0,
  "characters_to_write": 0,
  "auth_only_fields_to_drop": []
}
```

- [x] If a legacy field does not fit one of those destinations, stop and update this plan before the real migration.
- [x] If a non-character legacy `users` document lacks `account_id`, dry-run must report `missing_account_id` and the real migration must stop instead of deriving `account_id` from Mongo `_id`.
- [x] Run:

```bash
python connector/scripts/migrate-legacy-users.py --dry-run
pytest tests/unit/ -k "user_dao or identity"
```

- [x] Only after dry-run review, run the real migration and save the report artifact.

## Task 3: Switch subscriptions to `customer_id` and stage auth-table retirement

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Modify: `gateway/packages/api/prisma/migrations/20260417020000_retire_coke_auth_storage/migration.sql`
- Modify: `gateway/packages/api/src/lib/coke-subscription.ts`
- Modify: `gateway/packages/api/src/routes/coke-payment-routes.ts`

- [x] Add failing tests that prove subscription and payment lookups now use `customerId` instead of `cokeAccountId`.
- [x] Run: `pnpm --dir gateway/packages/api test -- src/lib/coke-subscription.test.ts src/routes/coke-payment-routes.test.ts`
- [x] Update the transition-safe migration so it:
  - copies any remaining subscription FKs to `customer_id`
  - preserves `coke_accounts` and `verify_tokens` for remaining compatibility callers until the maintenance-window cutover
- [x] Update the payment/webhook path so it:
  - reads and writes subscription rows by `customerId`
  - accepts both Stripe `metadata.customerId` and legacy `metadata.cokeAccountId` during the transition window
- [x] Re-run:

```bash
pnpm --dir gateway/packages/api exec prisma migrate reset --force
pnpm --dir gateway/packages/api test -- src/lib/coke-subscription.test.ts src/routes/coke-payment-routes.test.ts
```

## Task 4: Remove the Mongo auth collection and finalize runtime lookups

**Files:**
- Modify: `dao/user_dao.py`
- Modify: `agent/runner/identity.py`
- Modify: `connector/clawscale_bridge/app.py`
- Create: `connector/scripts/verify-auth-retirement.py`

- [x] Remove login / password / verification responsibilities from the Mongo auth DAO.
- [x] Update runtime identity resolution so it no longer requires the retired `users` auth document to exist.
- [x] Add a verification script that checks:
  - `users` auth collection is absent or empty
  - business collections still resolve by `account_id`
  - no ClawScale route still emits Coke-auth-only payloads
- [x] Run:

```bash
python connector/scripts/verify-auth-retirement.py
pytest tests/unit/ -k "identity or message_util or user_dao"
```

## Task 5: Remove remaining gateway runtime dependencies on legacy auth tables

**Files:**
- `gateway/packages/api/src/routes/coke-auth-routes.ts`
- `gateway/packages/api/src/lib/clawscale-user.ts`
- `gateway/packages/api/src/routes/customer-channel-routes.ts`
- `gateway/packages/api/src/routes/coke-wechat-routes.ts`
- `gateway/packages/api/src/routes/coke-user-provision.ts`
- `gateway/packages/api/src/routes/user-wechat-channel.ts`
- `gateway/packages/api/src/lib/route-message.ts`
- `gateway/packages/api/src/lib/platformization-backfill.ts`
- related Gateway tests covering deprecated Coke auth compatibility and channel provisioning

- [x] Add failing tests that prove deprecated Coke auth / channel compatibility paths still work without reading or writing `db.cokeAccount` or `db.verifyToken`.
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/coke-auth-routes.test.ts src/routes/customer-channel-routes.test.ts
```

- [x] Remove every live `db.cokeAccount` / `db.verifyToken` read or write from runtime code, replacing them with neutral `Customer` / `Identity` / `Membership`-based lookups or explicit maintenance-mode responses where compatibility can no longer be honored safely.
- [x] Keep the external deprecated `/api/coke/*` contract stable enough for callers during the transition, but stop synthesizing new legacy auth rows as part of runtime provisioning.
- [x] Re-run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/coke-subscription.test.ts src/routes/coke-payment-routes.test.ts src/routes/coke-auth-routes.test.ts src/routes/customer-channel-routes.test.ts
rg -n "db\\.(cokeAccount|verifyToken)|FROM\\s+coke_accounts|FROM\\s+verify_tokens" gateway/packages/api/src
```

- [x] If any runtime dependency remains, stop and update this plan before the destructive drop.

## Task 6: Execute the maintenance-window drop migration and verify

**Files:**
- `gateway/packages/api/prisma/schema.prisma`
- `gateway/packages/api/prisma/migrations/20260419010000_drop_legacy_coke_auth_tables/migration.sql`
- cutover documentation artifact for maintenance timing / rollback locations

- [x] Put registration / reset endpoints into maintenance mode before destructive steps.
- [x] Create the final destructive migration that:
  - drops `verify_tokens`
  - drops `coke_accounts`
  - removes the corresponding Prisma models / relations
- [x] Run the cutover checklist in order:

```bash
pnpm --dir gateway/packages/api exec tsx src/scripts/export-legacy-coke-auth.ts
pnpm --dir gateway/packages/api exec tsx src/scripts/audit-customer-id-parity.ts
python connector/scripts/migrate-legacy-users.py
pnpm --dir gateway/packages/api exec prisma migrate deploy
python connector/scripts/verify-auth-retirement.py
```

- [x] Verify:
  - existing sessions still resolve through `Customer.id`
  - Stripe / Coke payment flows resolve through `customer_id`
  - no gateway runtime path still depends on `db.cokeAccount` or `db.verifyToken`
  - no runtime path still queries Mongo `users` for auth
- [x] Document the exact maintenance-window timing and rollback artifact locations.
