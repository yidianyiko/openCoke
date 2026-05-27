# 2026-05-27 Output Customer ID Contract Evidence

## Change Under Test

Bridge-dispatched push output rows now use top-level `customer_id`. The bridge
output dispatcher no longer claims or sends account-id-only output rows.

## Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py \
  tests/unit/agent/test_message_util_clawscale_routing.py \
  tests/unit/runner/test_reminder_message_source.py -q
```

Result: 31 passed.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/ \
  tests/unit/agent/test_message_util_clawscale_routing.py -q
```

Result: 177 passed.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/runner/test_reminder_message_source.py -q
```

Result: 3 passed.

```bash
git diff --check
```

Result: passed.

## Evidence Class

These are unit and contract-path checks for the bridge output dispatcher and
runtime output document builder. They are not production smoke evidence that a
real user received a push message.
