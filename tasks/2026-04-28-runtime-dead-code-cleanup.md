# Task: Runtime Dead Code Cleanup

- Status: Verified
- Owner: Codex
- Date: 2026-04-28

## Goal

Clean up the remaining dead-code/problem surfaces identified after the retired
platform API removal, while keeping active runtime behavior intact.

## Scope

- In scope:
  - Move active AI backend runtime descriptors out of the deleted shared
    compatibility API surface and into the API package
  - Remove Knip-reported unused dependencies, unused runtime exports, duplicate
    exports, and unused exported type surfaces
  - Remove Vulture-reported Python DAO stub false positives
- Out of scope:
  - The item 4 workflow delegated to another owner
  - Product behavior changes to active channel, customer auth, or AI routing
    flows

## Touched Surfaces

- gateway-api
- gateway-web
- gateway-shared
- worker
- repo-os

## Acceptance Criteria

- AI backend route compatibility types are gone from shared while active API
  runtime descriptors continue to build
- `pnpm dlx knip --reporter compact` has no findings
- Vulture no longer reports the DAO stub parameter findings
- Gateway API, web, and shared verification pass
- Repo-OS structure checks pass

## Verification

- Command: `pnpm --dir gateway/packages/api build`
- Expected evidence: API TypeScript/declaration build passes after localizing
  active AI backend runtime types
- Evidence: passed
- Command: `pnpm --dir gateway/packages/shared build`
- Expected evidence: shared package still builds after removing retired shared
  compatibility types
- Evidence: passed
- Command: `pnpm --dir gateway/packages/api test`
- Expected evidence: gateway API Vitest suite passes
- Evidence: passed, 58 files / 418 tests
- Command: `pnpm --dir gateway/packages/web test`
- Expected evidence: gateway web Vitest suite passes
- Evidence: passed, 37 files / 141 tests
- Command: `pnpm --dir gateway/packages/web build`
- Expected evidence: Next production build passes
- Evidence: passed
- Command: `pnpm dlx knip --reporter compact`
- Expected evidence: no unused files, dependencies, exports, or exported types
- Evidence: passed with no findings
- Command: `.venv/bin/python -m vulture agent connector dao util framework entity conf --min-confidence 80`
- Expected evidence: no Vulture findings for the touched Python surfaces
- Evidence: passed with no findings
- Command: `zsh scripts/check`
- Expected evidence: repo-OS checks pass with this task file present
- Evidence: passed
