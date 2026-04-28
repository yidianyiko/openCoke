# Task: Disable Generic Gateway Route

- Status: Implemented
- Owner: Codex
- Date: 2026-04-28

## Goal

Disable the unauthenticated generic public gateway route so only platform-specific webhook routes remain exposed.

## Scope

- In scope:
  - Remove `POST /gateway/:channelId` from the gateway API router.
  - Keep token/signature-backed platform webhook routes working.
  - Update stale route guidance that points admins to the generic route.
- Out of scope:
  - New webhook signing schemes for existing platform-specific routes.
  - Runtime prompt or reminder behavior.

## Touched Surfaces

- gateway-api
- repo-os

## Acceptance Criteria

- Public `POST /gateway/:channelId` no longer routes into `routeInboundMessage`.
- `POST /gateway/evolution/whatsapp/:channelId/:token` remains intact.
- Related positive generic route coverage is removed or absent.

## Verification

- Command: `pnpm --dir gateway/packages/api test -- src/gateway/message-router.test.ts`
- Expected evidence: PASS, with the generic route unavailable and the tokenized Evolution route still covered.
- Result: PASS on 2026-04-28. The package Vitest config exercised 58 API test files / 419 tests.

## Notes

This task follows production black-box testing that showed the generic route could inject synthetic WhatsApp users into the real agent path.
