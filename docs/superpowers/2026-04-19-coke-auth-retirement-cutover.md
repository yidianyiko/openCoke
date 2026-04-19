# Coke Auth Retirement Cutover Runbook

## Scope

This runbook covers the final maintenance-window cutover for retiring legacy Coke auth storage in plan 3 task 6.

The destructive step is Prisma migration `20260419010000_drop_legacy_coke_auth_tables`, which:

- drops `verify_tokens`
- drops `coke_accounts`
- drops the legacy `subscriptions.coke_account_id` column if it still exists
- rewires `clawscale_users.coke_account_id` to `customers.id`

## Preconditions

- Gateway build includes `fix(auth): retire coke auth legacy storage`, `fix(payment): remove coke account compat lookups`, `refactor(api): retire coke account runtime helpers`, `fix(auth): tighten compatibility cutover`, and `fix(api): retire legacy coke auth tables`.
- Deprecated registration / verification / reset endpoints already return `503 temporarily_paused` before the migration begins.
- Operator has shell access to the checked-out worktree at `.worktrees/coke-auth-retirement`.

## Maintenance Window Timing

Use a 10-minute window. Treat the timestamps below as offsets from the announced start.

- `T-10m`: Announce maintenance start and confirm `/api/coke/register`, `/api/coke/verify-email*`, `/api/coke/forgot-password`, and `/api/coke/reset-password` are paused.
- `T-08m`: Export rollback artifacts from legacy Postgres auth tables.
- `T-06m`: Run the customer-id parity audit.
- `T-04m`: Run the Mongo legacy-user migration.
- `T-02m`: Apply Prisma migration `20260419010000_drop_legacy_coke_auth_tables`.
- `T-01m`: Run auth-retirement verification.
- `T+00m`: Re-open traffic if every command is green.

## Commands

Run these from `/data/projects/coke/.worktrees/coke-auth-retirement`.

```bash
pnpm --dir gateway/packages/api exec tsx src/scripts/export-legacy-coke-auth.ts
pnpm --dir gateway/packages/api exec tsx src/scripts/audit-customer-id-parity.ts
python connector/scripts/migrate-legacy-users.py
pnpm --dir gateway/packages/api exec prisma migrate deploy
python connector/scripts/verify-auth-retirement.py
```

Optional: override the export location if `/tmp` is not durable enough for the window.

```bash
LEGACY_COKE_AUTH_EXPORT_PATH=/secure/path/legacy-coke-auth-export.json \
  pnpm --dir gateway/packages/api exec tsx src/scripts/export-legacy-coke-auth.ts
```

## Rollback Artifacts

The rollback artifacts for this cutover are:

- Legacy auth export JSON from `src/scripts/export-legacy-coke-auth.ts`.
  Default location: `/tmp/coke-auth-retirement/<ISO timestamp>/legacy-coke-auth-export.json`
  The script creates the parent directory with mode `0700` and the export file with mode `0600` because the payload contains password hashes and live verify tokens.
  Treat the file as a sensitive secret-bearing artifact and move it to durable secure storage before the window closes if `/tmp` is ephemeral on the operator host.
  Override with `LEGACY_COKE_AUTH_EXPORT_PATH` or `--output <path>`.
- The pre-drop migration history already present in `gateway/packages/api/prisma/migrations/20260416000000_legacy_schema_baseline` through `20260418010000_parked_inbound_runtime_support`.
- The worktree branch itself: `/data/projects/coke/.worktrees/coke-auth-retirement` on branch `feat/coke-auth-retirement`.

No in-place database rollback is supported after `prisma migrate deploy` completes. Recovery means restoring from the exported legacy auth artifact plus the database backup/snapshot taken before the window.

## Success Criteria

- Existing sessions still resolve through `Customer.id`.
- Stripe/Coke payment flows resolve through `customer_id`.
- No gateway runtime source still depends on `db.cokeAccount` or `db.verifyToken`.
- No runtime path still queries Mongo `users` for auth.

If any verification command fails, hold the window open and restore from the pre-window database backup plus the exported legacy auth artifact before reopening traffic.
