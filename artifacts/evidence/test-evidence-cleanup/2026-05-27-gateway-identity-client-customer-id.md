# 2026-05-27 Gateway Identity Client Customer ID Evidence

## Change Under Test

The bridge's Python gateway identity binding client no longer accepts
`account_id` or `coke_account_id` as successful request aliases for
`/api/internal/coke-bindings`.

## Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py -q
```

Result: 5 passed.

```bash
git diff --check
```

Result: passed.

## Evidence Class

This is unit and client-contract evidence for gateway identity binding payload
construction. It is not live route-binding smoke.
