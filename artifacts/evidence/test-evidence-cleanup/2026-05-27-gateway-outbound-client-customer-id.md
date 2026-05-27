# 2026-05-27 Gateway Outbound Client Customer ID Evidence

## Change Under Test

The bridge's Python gateway outbound client no longer accepts `account_id` as a
successful request alias. It posts the current `customer_id` field required by
`/api/outbound`.

## Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py -q
```

Result: 18 passed.

```bash
git diff --check
```

Result: passed.

## Evidence Class

This is unit and client-contract evidence for bridge-to-gateway outbound
payload construction. It is not live outbound delivery smoke.
