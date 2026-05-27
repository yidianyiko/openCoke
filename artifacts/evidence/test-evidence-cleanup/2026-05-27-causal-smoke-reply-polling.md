# 2026-05-27 Causal Smoke Reply Polling Evidence

## Change Under Test

The bridge smoke helper no longer treats a recent output to the same recipient
as proof that the current `causal_inbound_event_id` produced a reply.

## Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/tools/test_bridge_client_late_poll.py -q
```

Result: 6 passed.

```bash
git diff --check
```

Result: passed.

## Evidence Class

This is unit evidence for smoke-helper causality. It is intentionally stricter
than the old helper and may expose real smoke failures where output rows are
not bound to the current causal event.
