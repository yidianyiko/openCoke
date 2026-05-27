# 2026-05-27 Late Reply Smoke Customer ID Cleanup

status: completed

## Goal

Make late-reply smoke polling follow the current push-output identifier
contract. Bridge-dispatched push output rows use top-level `customer_id`; a
retired top-level `account_id` row should not count as proof that the current
late-push path worked.

## Surfaces

- `repo-os`: verification helper semantics
- `bridge`: late reply smoke evidence for bridge-dispatched push outputs

## Changes

1. `poll_late_reply_text` now searches late push rows by `customer_id`.
2. The same helper still accepts `to_user` rows for synchronous/direct reply
   records.
3. The unit test now proves `account_id` is not part of the late reply polling
   selector.

## Non-goals

- Do not change production bridge delivery behavior.
- Do not claim production smoke coverage from this unit-level helper change.
