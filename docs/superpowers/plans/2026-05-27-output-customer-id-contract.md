# 2026-05-27 Output Customer ID Contract Cleanup

status: completed

## Goal

Remove the test and dispatcher behavior that treated `account_id` as an active
push-output dispatch selector. `/api/outbound` and the bridge/gateway outbound
path use `customer_id`; tests should not preserve the retired field as a
successful dispatch path.

## Surfaces

- `worker-runtime`: proactive reminder output document creation
- `bridge`: ClawScale output dispatcher claim and outbound payload building
- `repo-os`: architecture note for the outbound identifier contract

## Changes

1. Proactive ClawScale output documents created from runtime context now write
   top-level `customer_id`.
2. `ClawScaleOutputDispatcher` only claims output rows with top-level
   `customer_id`.
3. Dispatcher tests now prove account-id-only rows are not selected instead of
   proving a compatibility window.
4. Architecture docs state that `account_id` is not an active outbound dispatch
   selector.

## Non-goals

- Do not change gateway identity/provision compatibility contracts.
- Do not make a production delivery claim without a smoke path.
