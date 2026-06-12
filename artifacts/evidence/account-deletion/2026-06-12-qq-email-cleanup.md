# QQ Email Account Cleanup Evidence

Date: 2026-06-12
Host: `gcp-coke`
Compose root: `/home/whoami/coke-clean`
Postgres container: `coke-clean-postgres-1`
Database: `coke`

## Scope

Delete application data for users registered in the last 72 hours whose
credential email domain is exactly `qq.com`.

Selection predicate:

```sql
account.created_at >= now() - interval '3 days'
AND lower(split_part(credential.email, '@', 2)) = 'qq.com'
```

Candidate account:

| account_id | registered_at_utc | email |
| --- | --- | --- |
| `dd3ebef7-81c0-4246-b431-49b62e9acee7` | `2026-06-12 05:32:13.825579+00` | `79***@qq.com` |

No server logs, audit logs, or backups were deleted or modified.

## Dry Run

Command shape:

```bash
ssh gcp-coke 'docker exec -i coke-clean-postgres-1 psql -U coke -d coke -X -v ON_ERROR_STOP=1 -P pager=off' <<'SQL'
BEGIN;
-- create temporary cleanup_* candidate tables
-- select affected row counts
ROLLBACK;
SQL
```

Dry-run affected rows:

| table | rows |
| --- | ---: |
| `public.account` | 1 |
| `public.account_access` | 1 |
| `public.account_activation` | 1 |
| `public.auth_artifact` | 1 |
| `public.credential` | 1 |
| `public.session` | 3 |
| `public.user_profile` | 1 |

All checked runtime/user-path tables had zero affected rows, including
`conversation`, `turn`, `message`, `delivery_attempt`, `reminder`,
`reminder_fire`, `notification_fact`, `notification_recipient`, `outbox`,
`ai.agno_sessions`, and `ai.agno_memories`.

## Delete

Command shape:

```bash
ssh gcp-coke 'docker exec -i coke-clean-postgres-1 psql -U coke -d coke -X -v ON_ERROR_STOP=1 -P pager=off' <<'SQL'
BEGIN;
-- create the same temporary cleanup_* candidate tables
-- delete dependent rows first, then identity rows
COMMIT;
SQL
```

Committed delete counts:

| table | deleted_rows |
| --- | ---: |
| `public.session` | 3 |
| `public.credential` | 1 |
| `public.account_access` | 1 |
| `public.account_activation` | 1 |
| `public.user_profile` | 1 |
| `public.auth_artifact` | 1 |
| `public.account` | 1 |

Every other checked table deleted 0 rows.

## Post-Delete Verification

Verification command shape:

```bash
ssh gcp-coke 'docker exec -i coke-clean-postgres-1 psql -U coke -d coke -X -v ON_ERROR_STOP=1 -P pager=off' <<'SQL'
-- recent qq.com account count
-- direct account-id reverse lookup across identity/runtime/domain/Agno tables
SQL
ssh gcp-coke 'curl -fsS http://127.0.0.1:8000/healthz'
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean ps'
```

Results:

| check | result |
| --- | --- |
| Recent `qq.com` registrations remaining | 0 |
| Reverse lookup non-zero rows for deleted account id | 0 |
| API health | `{"ok":true}` |
| Compose services | `coke-api`, `coke-worker`, `coke-scheduler`, `coke-outbox-relay`, `coke-web`, `postgres`, and `redis` running |
