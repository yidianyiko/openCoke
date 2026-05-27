# 2026-05-27 Late Reply Smoke Customer ID Evidence

## Change Under Test

Late-reply smoke polling now treats top-level `customer_id` as the current
bridge-dispatched push-output identifier and no longer includes retired
top-level `account_id` rows in the selector.

## Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/tools/test_bridge_client_late_poll.py -q
```

Result: 4 passed.

```bash
git diff --check
```

Result: passed.

## Evidence Class

This is unit evidence for the smoke helper's Mongo selector. It is not a live
late-reply delivery smoke.
