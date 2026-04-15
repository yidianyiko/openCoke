# Clawscale User Orphan Repair

Use this runbook when Gateway startup fails during:

```sh
npx prisma db push --skip-generate
```

with:

```text
insert or update on table "clawscale_users" violates foreign key constraint "clawscale_users_coke_account_id_fkey"
```

## Root Cause

Older `clawscale_users` rows could exist without a matching `coke_accounts.id`.
That was possible before the gateway started checking `coke_accounts`
existence before provisioning a `ClawscaleUser`.

Current code already guards new writes. The production failure is caused by
legacy data becoming incompatible with the newer Prisma-enforced FK.

## Why Not Delete The Orphans

Some orphan `clawscale_users` rows can still own:

- `channels.owner_clawscale_user_id`
- `end_users.clawscale_user_id`
- `conversations.clawscale_user_id`
- `delivery_routes.coke_account_id`

Deleting the orphan row is therefore destructive and not the safe default.

## Safe Minimal Repair

Backfill inert parent rows in `coke_accounts` for the missing IDs. The repair
script creates placeholder accounts with these properties:

- `email = <coke_account_id>@recovered.coke.invalid`
- `status = suspended`
- `email_verified = false`

This restores referential integrity without changing the existing
`clawscale_users` identifiers or dependent records.

## Commands

Inspect the current orphan set from the deployment host:

```sh
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U clawscale -d clawscale <<'SQL'
SELECT
  cu.id AS clawscale_user_id,
  cu.tenant_id,
  cu.coke_account_id,
  (
    SELECT COUNT(*)
    FROM channels ch
    WHERE ch.owner_clawscale_user_id = cu.id
  ) AS channel_count,
  (
    SELECT COUNT(*)
    FROM end_users eu
    WHERE eu.clawscale_user_id = cu.id
  ) AS end_user_count,
  (
    SELECT COUNT(*)
    FROM conversations conv
    WHERE conv.clawscale_user_id = cu.id
  ) AS conversation_count,
  (
    SELECT COUNT(*)
    FROM delivery_routes dr
    WHERE dr.coke_account_id = cu.coke_account_id
  ) AS delivery_route_count
FROM clawscale_users cu
LEFT JOIN coke_accounts ca
  ON ca.id = cu.coke_account_id
WHERE ca.id IS NULL
ORDER BY cu.created_at, cu.id;
SQL
```

Run the repair:

```sh
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U clawscale -d clawscale \
  < gateway/packages/api/prisma/repairs/2026-04-15-backfill-orphan-coke-accounts.sql
```

Confirm no orphans remain:

```sh
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U clawscale -d clawscale <<'SQL'
SELECT cu.id, cu.coke_account_id
FROM clawscale_users cu
LEFT JOIN coke_accounts ca
  ON ca.id = cu.coke_account_id
WHERE ca.id IS NULL;
SQL
```

Retry the Prisma schema apply:

```sh
docker compose -f docker-compose.prod.yml up -d gateway
```

## Aftercare

List the placeholder accounts created by this repair:

```sh
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U clawscale -d clawscale <<'SQL'
SELECT id, email, display_name, status, email_verified, created_at
FROM coke_accounts
WHERE email LIKE '%@recovered.coke.invalid'
ORDER BY created_at DESC;
SQL
```

These accounts are intentionally suspended. Keep them until you have a separate,
case-by-case reconciliation plan for the affected users and their dependent
conversation state.
