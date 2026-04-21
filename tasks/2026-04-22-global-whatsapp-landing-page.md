# Task: Global WhatsApp Landing Page

- Status: Complete
- Owner: Codex
- Date: 2026-04-22

## Goal

Add a new `/global` public landing page that targets overseas traffic and funnels all primary CTA interactions into a WhatsApp chat with Coke.

## Scope

- In scope:
- Add a dedicated `/global` route in the web app.
- Build a pure-English landing page aligned with the current Coke homepage voice, without multi-channel messaging.
- Route all primary CTAs to the WhatsApp chat for `+86 19917902815`.
- Add targeted web tests for the new route/component behavior.
- Out of scope:
- Changing the existing `/` homepage.
- User account binding, auth flows, or QR-based onboarding.
- Backend channel configuration changes.

## Touched Surfaces

- gateway-web

## Acceptance Criteria

- `/global` renders a dedicated public landing page in English.
- All primary CTAs on `/global` open WhatsApp chat for `+86 19917902815`.
- The page does not surface login/register as primary conversion paths.
- Existing `/` homepage behavior remains unchanged.

## Verification

- Command: `pnpm --dir gateway/packages/web test`
- Expected evidence: the full web Vitest suite passes with `/global` landing page coverage included.

## Notes

- The page should feel closer to an overseas consumer landing page while staying within the existing Coke brand system.
