# 2026-05-27 Gateway Outbound Client Customer ID Cleanup

status: completed

## Goal

Align the Python bridge outbound client with the current `/api/outbound`
contract. The gateway edge requires `customer_id`; `account_id` is not an
accepted request alias.

## Surfaces

- `bridge`: Python client used by the output dispatcher
- `repo-os`: cleanup plan and evidence

## Changes

1. `GatewayOutboundClient.post_output` now requires `customer_id`.
2. Blank `customer_id` fails locally before posting.
3. Unit tests no longer prove successful `account_id` alias posting.

## Non-goals

- Do not change gateway `/api/outbound`.
- Do not remove inbound or identity compatibility aliases that are still named
  by the interface contract.
