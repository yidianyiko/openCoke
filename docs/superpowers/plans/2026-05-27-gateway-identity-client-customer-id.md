# 2026-05-27 Gateway Identity Client Customer ID Cleanup

status: completed

## Goal

Align the Python gateway identity binding client with the current
`/api/internal/coke-bindings` contract. The route requires `customer_id`;
`account_id` and `coke_account_id` are retired HTTP aliases for this route.

## Surfaces

- `bridge`: Python client for gateway identity binding
- `repo-os`: cleanup plan and evidence

## Changes

1. `GatewayIdentityClient.bind_identity` now requires `customer_id`.
2. The `bind` convenience method forwards only `customer_id`.
3. Blank `customer_id` fails before an HTTP request is sent.
4. Unit tests no longer prove successful `account_id` alias binding.

## Non-goals

- Do not change `/bridge/inbound` normalization, where `coke_account_id` and
  `customer_id` remain current bridge ingress fields.
- Do not change `/api/internal/coke-users/provision`, where `coke_account_id`
  remains active for synthetic smoke provisioning.
