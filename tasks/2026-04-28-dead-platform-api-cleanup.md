# Task: Dead Platform API Cleanup

- Status: Verified
- Owner: Codex
- Date: 2026-04-28

## Goal

Remove retired platform API compatibility routes and zero-reference migration
scripts that are no longer part of the current Coke product runtime.

## Scope

- In scope:
  - Remove retired `/api/workflows`, `/api/conversations`, and
    `/api/ai-backends` 410 compatibility route modules and mount points
  - Remove the obsolete workflow shared type export
  - Remove Knip-reported zero-reference migration scripts
  - Verify the gateway API/shared build and dead-code scan
- Out of scope:
  - Removing active AI backend runtime types still used by route-message and
    bridge WebSocket delivery
  - Removing current shared-channel or personal WeChat runtime surfaces
  - Editing historical design plans that describe the original migrations

## Touched Surfaces

- gateway-api
- repo-os

## Acceptance Criteria

- Retired route modules are gone and no longer mounted from the API entrypoint
- Zero-reference migration scripts are removed
- Gateway package checks do not fail from stale imports
- Repository structure checks pass

## Verification

- Command: `pnpm --dir gateway/packages/api test`
- Expected evidence: gateway API Vitest suite passes
- Evidence: passed, 57 files / 416 tests
- Command: `pnpm --dir gateway/packages/api build`
- Expected evidence: API TypeScript build passes
- Evidence: passed
- Command: `pnpm --dir gateway/packages/shared build`
- Expected evidence: shared package TypeScript build passes
- Evidence: passed
- Command: `pnpm dlx knip --reporter compact`
- Expected evidence: removed files no longer appear as unused files
- Evidence: command still reports pre-existing unused deps/exports, but the
  removed `audit-stranded-models.ts`, `audit-wire-identifier-compat.ts`, and
  `backfill-route-bindings.ts` unused-file findings are gone
- Command: `zsh scripts/check`
- Expected evidence: repo-OS checks pass with this task file present
- Evidence: passed
