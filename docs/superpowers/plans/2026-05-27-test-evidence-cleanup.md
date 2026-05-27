# 2026-05-27 Test Evidence Cleanup

status: completed

## Goal

Reduce tests that make weak or stale evidence look like valid runtime proof.
The first slice targets tests that protect fallback behavior around reminder
delivery routes, because recent smoke evidence showed route-key gaps can create
visible reminders that later cannot be delivered.

## Surfaces

- `repo-os`: durable test-evidence rules and verification routing language
- `bridge`: bridge reminder management adapter and route error mapping

## First Slice

1. Add a durable test-evidence contract that separates structure, unit,
   contract, eval, and smoke evidence.
2. Rewrite bridge reminder management tests that currently prove unsafe
   fallbacks:
   - explicit business conversation hints must fail closed when unresolved
   - new visible reminders created through bridge management require a durable
     delivery route key
3. Update the adapter implementation to match the rewritten contract.
4. Run targeted bridge tests plus repo-OS verification.

## Non-goals

- Do not delete large test directories mechanically.
- Do not weaken tests to get a green result.
- Do not claim reminder user-path coverage from this slice; this is a bridge
  contract cleanup, not an eval or production smoke run.
