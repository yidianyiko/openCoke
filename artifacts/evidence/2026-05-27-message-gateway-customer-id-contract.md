# Message Gateway Customer ID Contract Verification

Date: 2026-05-27

Change under verification:

- Removed the generic ClawScale bridge `resolve_customer_id` helper.
- Required `CokeMessageGateway` to receive normalized `customer_id` in the
  enqueue payload instead of accepting `account_id` or `coke_account_id` as
  internal aliases.
- Kept `/bridge/inbound` edge normalization intact; that edge still accepts the
  active payload compatibility documented for inbound ClawScale messages.

Commands run from `/data/projects/coke/.worktrees/test-evidence-cleanup-7`
using `/data/projects/coke/.venv/bin/python`:

```sh
PYTHONPATH=/data/projects/coke/.worktrees/test-evidence-cleanup-7 \
  /data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_message_gateway.py -q
```

Result: 15 passed.

```sh
PYTHONPATH=/data/projects/coke/.worktrees/test-evidence-cleanup-7 \
  /data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py -q
```

Result: 69 passed.

```sh
PYTHONPATH=/data/projects/coke/.worktrees/test-evidence-cleanup-7 \
  /data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/ -v
```

Result: 166 passed.

```sh
PYTHONPATH=/data/projects/coke/.worktrees/test-evidence-cleanup-7 \
  /data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Result: 14 passed.

```sh
git diff --check
zsh scripts/suggest-verification --base HEAD
zsh scripts/review-trigger --base HEAD
```

Results:

- `git diff --check`: passed.
- `suggest-verification`: suggested `zsh scripts/verify-surface bridge`.
- `review-trigger`: non-blocking `evidence_gap` before this artifact existed.
