# 2026-06-12 Eva Open-Window Convergence Evidence

## Production Repair

Eva account:

- account: `94566791-4d39-4b28-9d9f-367c1ed0be2c`
- conversation: `50425626-97b2-4056-b493-99aa738ba171`

Before repair, production was stuck at `last_closed_inbound_seq=79`,
`latest_inbound_seq=82`. The open window `80..82` had terminal `failed` turns
with `needs_past_time_confirmation` and `duplicate_staged_command_idempotency`,
but no final delivery attempt.

Scoped reset:

```sql
UPDATE conversation
SET last_closed_inbound_seq = latest_inbound_seq,
    updated_at = now()
WHERE id = '50425626-97b2-4056-b493-99aa738ba171'
  AND account_id = '94566791-4d39-4b28-9d9f-367c1ed0be2c'
  AND last_closed_inbound_seq = 79
  AND latest_inbound_seq = 82;
```

Result: one row affected. Post-reset Eva cursor was `82/82`, with global open
conversation count `0`.

Manual recovery notice attempts:

- without context token: failed with `context_token_required`;
- with latest context token: failed with `wechat_not_connected`;
- connector state showed Eva session
  `2e5c4cd8c9f34624abb19d49e590e715` as `expired`.

## Code Fix

Runtime guardrails now converge current input-window failures through
`recovered` close decisions rather than audit-only `failed` rows. Covered paths:

- inbound pipeline unavailable;
- inbound pipeline runtime exception;
- inbound pipeline close-result runtime error;
- async completion timeout after a pending reply;
- async timeout without a task id;
- invalid output protocol on a fallback/access-denied path with current input.

Commits:

- `dba40e2b33cc3e0fcb192032da967ad48417e233`
  `test(turn): close eager-execute review gaps`
- `add9cab196c42402bf3b056d991a00b0d3725b09`
  `docs: record eva open-window convergence`

## Local Verification

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -v
```

Result: `11 passed`.

```bash
.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/conversation_runtime -v
```

Result: `212 passed, 1 skipped`. Skip:
`COKE_TEST_DATABASE_URL is not set`.

```bash
.venv/bin/python -m pytest tests/unit/coke -q
```

Result: `927 passed, 1 skipped`. Skip:
`COKE_TEST_DATABASE_URL is not set`.

```bash
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
zsh scripts/check
zsh scripts/verify-surface clean-rebuild-docs repo-os-docs
git diff --check
```

Result: all passed.

Diff-aware routing:

```bash
zsh scripts/suggest-verification --base HEAD
zsh scripts/review-trigger --base HEAD
```

Result: suggested docs, repo-OS docs, and web because unrelated dirty WeChat
channel UI files were present in the worktree. The web files were not part of
this incident fix and were not committed here.

## Production Deploy

Command:

```bash
scripts/deploy-compose-to-gcp.sh
```

Result:

- deployed SHA marker: `add9cab196c42402bf3b056d991a00b0d3725b09`;
- previous marker: `c906bcd90d2782a4d647be7d4e7eb6f10c07a99e`;
- deploy tier: `backend`;
- migration ran `20260612_0001`;
- `alembic check`: no new upgrade operations detected;
- recreated `coke-api`, `coke-worker`, `coke-scheduler`, and
  `coke-outbox-relay`;
- deploy script health checks passed.

Post-deploy production checks:

```text
marker=add9cab196c42402bf3b056d991a00b0d3725b09
health={"ok":true}
```

Compose status:

```text
coke-clean-coke-api-1            Up (healthy)
coke-clean-coke-worker-1         Up
coke-clean-coke-scheduler-1      Up
coke-clean-coke-outbox-relay-1   Up
coke-clean-postgres-1            Up (healthy)
coke-clean-redis-1               Up (healthy)
```

Eva DB state after deploy:

```text
last_closed_inbound_seq=82
latest_inbound_seq=82
open_lag=0
open_conversations=0
```

Recent Eva failed rows remain as historical audit:

```text
26792778-95df-44ea-a2c6-f8da30cd391e 80..82 failed needs_past_time_confirmation
491eef9a-8e89-43a4-abbe-c7f67ec11e8b 80..82 failed duplicate_staged_command_idempotency
f4bed67a-5aa0-439e-8ca7-dd9854478921 80..82 failed duplicate_staged_command_idempotency
```

Connector status:

```text
connector_health={"connected":true,"connected_session_count":3,"ok":true,"status":"connected"}
eva_session status=expired
```

The runtime stuck-window fix is deployed. Eva's ability to receive proactive
manual notification still depends on re-establishing Eva's expired personal
WeChat connector session.
