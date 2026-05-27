# Test Evidence Contract

This document defines how Coke treats tests as evidence. Tests are part of the
runtime contract only when they protect current behavior at the correct layer.

## Core Rule

Delete or rewrite tests that make stale behavior look required.

Passing tests are useful evidence, but they are not a product goal. A test that
protects a legacy shim, alias route, fallback parser, synthetic route key, or
mock-only success path must either point to a current canonical contract or be
removed with the code path it protects.

## Evidence Classes

- Contract tests prove a typed boundary, schema, adapter, or runtime guard.
- Unit tests prove focused in-process behavior. They must state which
  production path they represent when fakes replace storage, providers, or LLMs.
- Eval or smoke tests prove user-visible behavior through a corpus or real
  path. They are required when prompt, model, delivery, or reminder behavior is
  the claim.
- Structure tests prove repository shape only. They must not be cited as
  runtime evidence.

## Deletion Criteria

Remove or rewrite a test when it:

- expects compatibility behavior that is not listed in a current canonical doc
- asserts a fallback path that can create a durable write with missing delivery,
  lock, session, owner, or route semantics
- uses mocks to claim user-visible success without a matching eval, smoke, or
  user-path check
- duplicates another test at the same layer without protecting a distinct
  contract or risk
- exists only to keep a retired implementation branch from being deleted

## Rewrite Criteria

Rewrite instead of delete when the scenario is still real but the asserted
contract is wrong. The rewritten test should fail closed at the right layer and
avoid proving a permissive fallback.

For example, a bridge reminder test may prove that a missing explicit
conversation returns `conversation_required`; it must not prove that the
adapter silently uses an unrelated latest conversation. A bridge reminder test
may prove that a durable delivery route key is required before creating a
visible reminder; it must not prove that `route_key=None` is a valid new
visible reminder target.

## Reporting Rule

When reporting test results, name the evidence class. Do not say that unit
tests or structure checks prove a user-visible path. If no eval, smoke, or
user-path check was run for a user-facing claim, state that gap directly.
